"""Sorgu servisi: MCP araçlarının iş mantığı (MCP kütüphanesinden bağımsız).

Her çağrı: Hub'ı `mode=ro` aç -> anahtarı doğrula -> izinleri yeniden oku -> sorgula ->
erişim kaydına yaz -> döndür. Kayıt yazılamazsa veri DÖNMEZ (`ServiceError`).
Hiçbir şey önbelleğe alınmaz.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kimlikcore import (
    AnahtarGerekli,
    SifrelemeHatasi,
    Category,
    Event,
    FormatError,
    Hub,
    HubNotFoundError,
    KimlikError,
    PermissionDenied,
    SchemaTooNew,
    SchemaTooOld,
)

from kimlikcore import norm_ts
from kimlikcore.turkish import build_fts_query, tokens

from . import esanlam, kart as kartmod
from .alinti import ALINTI_UZUNLUGU, alinti
from ._db import Clock, utc_now
from .access import (AccessLog, AccessLogError, Authorizer, categories_label, konu_izinli_mi,
                     konu_kosulu, list_topics)
from .kart import OZET_KATEGORILERI
from .oneri import (MAX_ONERI_CAGRI, OneriKuyrugu, OneriYazilamadi, dogrula_onerme)
from .persona import CATEGORY_TITLES, FACT_CATEGORIES, PersonaReader, son_dogrulama
from .toplulastir import TUM_ALANLAR, Toplulastirici
from .yerelsaat import YerelSaat

log = logging.getLogger("kimlikserver")  # kayıt içeriği asla günlüğe yazılmaz

# Veri uyarısı artık cevaplarda tekrar edilmez; MCP `instructions` ve araç açıklamalarındadır
# (mcp/server.py). Kayıt metinleri `veri` alanlarında ve `say` satırlarında döner.
DEFAULT_SEARCH_LIMIT = 10
DEFAULT_TIMELINE_LIMIT = 20
MAX_LIMIT = 200
KAYIT_PARCA = 4000          # kayit_getir varsayılan parça uzunluğu (karakter)
KAYIT_PARCA_UST = 20000
_KAYIT_RET = "Kayıt bulunamadı ya da bu anahtarla okunamaz."   # yok/gizli/izinsiz: aynı ileti
_ZAMANSIZ_NOT = ("'zaman_gercek: false' kayıtların zamanı kaynak dosya tarihidir; gerçek olay "
                 "zamanı değildir.")
ZAMANSIZ_UST = 20          # zaman_cizelgesi sonunda gösterilen zamansız kayıt (abonelik/kütüphane) sayısı
_GERCEK_ZAMAN = "COALESCE(json_extract(payload, '$.zaman_kaynagi'), '') <> 'dosya_tarihi'"
ROLLER = ("kullanici", "asistan")   # sohbet mesajı rolü (payload.rol)
_ROL = "json_extract(payload, '$.rol')"
_DUSUK_ONEM_RET = ("Kanıtlar yalnız düşük önemli kayıtlar (beğeni/takip gibi); kullanıcının kendi "
                   "yazdığı bir kayıt gerekli. Hiçbir öneri eklenmedi.")
_GPS_KEYS = frozenset({"gps", "lat", "lon", "lng", "latitude", "longitude", "enlem", "boylam",
                       "koordinat", "koordinatlar", "coordinates", "geo", "geolocation"})


class ServiceError(Exception):
    """Kullanıcıya/yapay zekâya gösterilebilir (içerik sızdırmayan) Türkçe hata."""


def _has_gps(obj: Any, depth: int = 0) -> bool:
    if depth > 6:
        return False
    if isinstance(obj, dict):
        return any(str(k).lower() in _GPS_KEYS or _has_gps(v, depth + 1) for k, v in obj.items())
    if isinstance(obj, (list, tuple)):
        return any(_has_gps(v, depth + 1) for v in obj)
    return False


def _rol_dogrula(rol: str | None) -> str | None:
    if rol is None:
        return None
    if not isinstance(rol, str) or rol not in ROLLER:
        raise ServiceError("Geçersiz rol. Geçerli değerler: " + ", ".join(ROLLER) + ".")
    return rol


def _sql_ara(hub: Hub, sorgu: str, cats: list[str], rol: str | None, lim: int,
             konular: Iterable[str]) -> list[Event]:
    """Servis içi FTS araması: `Hub.search` ile aynı FTS/katlama; sıra FTS sırası, eşitlikte önem
    (yüksek önce), sonra zaman. Rol ve hassas konu süzgeçleri SQL'de (limit doğru dolar)."""
    match = build_fts_query(sorgu)
    if match is None or not cats:
        return []
    kk, ka = konu_kosulu(konular, "e.hassas_konu")
    rol_k, rol_a = ("", []) if rol is None else (" AND json_extract(e.payload, '$.rol') = ?", [rol])
    rows = hub.query(
        "SELECT e.event_id FROM events_fts f JOIN events e ON e.seq = f.rowid "
        "WHERE events_fts MATCH ? AND e.hidden = 0 "
        f"AND e.category IN ({','.join('?' * len(cats))}){rol_k} AND {kk} "
        "ORDER BY f.rank, e.onem DESC, e.ts DESC, e.seq DESC LIMIT ?",
        [match, *cats, *rol_a, *ka, int(lim)])
    return [hub.get_event(r[0]) for r in rows]


def _limit(value: int | None, default: int) -> int:
    if value is None:
        return default
    try:
        v = int(value)
    except (TypeError, ValueError) as e:
        raise ServiceError("limit sayı olmalı.") from e
    return max(1, min(v, MAX_LIMIT))


@dataclass
class _Result:
    data: dict[str, Any]
    count: int
    category: str | None
    # Erişim kaydı yazıldıktan SONRA çalışır (kayıtsız yazma olmasın); sonucu `data`yı değiştirir.
    commit: Callable[[], dict[str, Any]] | None = None


class QueryService:
    def __init__(self, root: Path | str, key: str | None, *, clock: Clock = utc_now,
                 access_log: AccessLog | None = None,
                 hub_opener: Callable[[Path], Hub] | None = None,
                 saat_dilimi: YerelSaat | str | None = None):
        self.root = Path(root)
        self.tz = saat_dilimi if isinstance(saat_dilimi, YerelSaat) else YerelSaat.cozumle(saat_dilimi)
        self._key = key
        self._clock = clock
        self._log = access_log or AccessLog(self.root, clock=clock)
        self._open = hub_opener or (lambda r: Hub.open(r, write=False))

    # ------------------------------------------------------------------ ortak akış
    def _run(self, tool: str, requested: str | None,
             fn: Callable[[Hub, Authorizer, dict[str, str | None]], _Result]) -> dict[str, Any]:
        app_id = "bilinmeyen"
        cat_label = requested
        try:
            hub = self._open(self.root)
            try:
                auth = Authorizer(hub, clock=self._clock)
                ident = auth.authenticate(self._key)
                app_id = ident.app_id
                auth.ident = ident
                auth.konular = auth.allowed_topics(app_id)   # her sorguda yeniden okunur
                res = fn(hub, auth, auth.allowed_categories(app_id))
                cat_label = res.category
            finally:
                hub.close()
        except PermissionDenied as e:
            self._log_best_effort(app_id, tool, cat_label, 0, "reddedildi")
            raise ServiceError(f"reddedildi: {e}") from None
        except SchemaTooOld:
            self._log_best_effort(app_id, tool, cat_label, 0, "hata")
            raise ServiceError("Veritabanı eski biçimde. Önce Kimlik Merkezi uygulamasını bir kez "
                               "açın, sonra yeniden deneyin.") from None
        except SchemaTooNew:
            self._log_best_effort(app_id, tool, cat_label, 0, "hata")
            raise ServiceError("Bu bağlantı eski sürümle çalışıyor. Yapay zekâ uygulamasını "
                               "(ör. Claude Desktop) tamamen kapatıp yeniden başlatın.") from None
        except AnahtarGerekli:
            self._log_best_effort(app_id, tool, cat_label, 0, "hata")
            raise ServiceError("Veri şifreli ve anahtar açılamadı. Parolalı klasörü MCP kendiliğinden "
                               "açamaz (bilinçli güvenlik kararı); Claude erişimi için Kimlik Merkezi > "
                               "Güvenlik'ten parolayı kaldırın. İleri düzey: KIMLIK_PAROLA ortam değişkeni "
                               "çalışır ama parolayı düz metin yapılandırmaya koymak korumayı azaltır. "
                               "Windows hesabı farklıysa kurtarma ifadesiyle yeniden bağlayın."
                               ) from None
        except SifrelemeHatasi:
            self._log_best_effort(app_id, tool, cat_label, 0, "hata")
            raise ServiceError("Şifreli veri okunamadı (dosya bozuk olabilir).") from None
        except HubNotFoundError:
            self._log_best_effort(app_id, tool, cat_label, 0, "hata")
            raise ServiceError("Veri klasöründe veritabanı yok. Önce Kimlik Merkezi uygulamasını "
                               "bir kez açın.") from None
        except (FormatError, ServiceError) as e:
            self._log_best_effort(app_id, tool, cat_label, 0, "hata")
            raise ServiceError(str(e)) from None
        except Exception as e:  # beklenmeyen: ayrıntı (kayıt içeriği olabilir) istemciye gitmez
            log.error("%s: beklenmeyen hata: %s", tool, type(e).__name__)
            self._log_best_effort(app_id, tool, cat_label, 0, "hata")
            raise ServiceError("Beklenmeyen bir hata oluştu; ayrıntı günlüktedir.") from None
        try:
            self._log.record(app_id, tool, res.category, res.count, "ok")
        except AccessLogError:
            log.error("%s: erişim kaydı yazılamadı; sorgu reddedildi", tool)
            raise ServiceError("reddedildi: erişim kaydı yazılamadığı için sorgu "
                               "yanıtlanmadı.") from None
        if res.commit is not None:
            try:
                return res.commit()
            except OneriYazilamadi:
                log.error("%s: öneri kuyruğu yazılamadı", tool)
                self._log_best_effort(app_id, tool, res.category, 0, "hata")
                raise ServiceError("reddedildi: öneri kuyruğu yazılamadı; hiçbir şey eklenmedi.") \
                    from None
        return res.data

    def _log_best_effort(self, app_id: str, tool: str, category: str | None, count: int,
                         outcome: str) -> None:
        try:
            self._log.record(app_id, tool, category, count, outcome)
        except AccessLogError:
            log.error("%s: ret/hata kaydı da yazılamadı", tool)

    @staticmethod
    def _categories(allowed: dict[str, str | None], requested: str | None) -> list[str]:
        if requested is not None:
            if requested not in Category.ALL:
                raise ServiceError("Bilinmeyen kategori.")
            if requested not in allowed:
                raise PermissionDenied(f"'{requested}' kategorisi için izin yok.")
            return [requested]
        if not allowed:
            raise PermissionDenied("Bu anahtara hiçbir kategori için izin verilmemiş.")
        return sorted(allowed)

    @staticmethod
    def _need_persona(allowed: dict[str, str | None]) -> None:
        if Category.PERSONA not in allowed:
            raise PermissionDenied("'persona' kategorisi için izin yok.")

    def _records(self, events: Iterable[Event], allowed: dict[str, str | None], *,
                 kisalt: bool = True, terimler: list[str] | None = None) -> list[dict[str, Any]]:
        """Sadeleşmiş kayıt sözlüğü: id, zaman (YEREL, ofsetli), tur, kategori, veri, (rol),
        (kisaltildi + uzunluk). `kisalt`: veri en çok ALINTI_UZUNLUGU karakter; `terimler`
        (katlanmış sözcükler) verilirse alıntı ilk eşleşmenin çevresinden alınır."""
        out = []
        for e in events:
            # Savunma katmanı: içe aktarıcı GPS'i ayırmayı unutmuşsa, konum izni yoksa dönmez.
            if e.category != Category.KONUM and _has_gps(e.payload) \
                    and Category.KONUM not in allowed:
                continue
            r: dict[str, Any] = {"id": e.event_id, "zaman": self.tz.yerel(e.ts), "tur": e.kind,
                                 "kategori": e.category}
            metin = e.text or ""
            if kisalt and len(metin) > ALINTI_UZUNLUGU:
                r["veri"] = alinti(metin, terimler)
                r["kisaltildi"] = True
                r["uzunluk"] = len(metin)
            else:
                r["veri"] = metin
            if e.payload.get("rol") is not None:
                r["rol"] = e.payload["rol"]   # yalnız sohbet kayıtlarında vardır
            if e.onem == 0:
                r["dusuk"] = True             # beğeni/takip gibi; onem değeri token için yazılmaz
            if e.payload.get("zaman_kaynagi") == "dosya_tarihi":
                r["zaman_gercek"] = False     # abonelik/kütüphane: zaman dosya tarihidir
            out.append(r)
        return out

    def _aralik(self, baslangic: str | None, bitis: str | None) -> tuple[str | None, str | None]:
        """Girdi -> UTC ISO. Saat dilimi yazılmamış değer YEREL saat sayılır."""
        b, e = self.tz.sorgu_zamani(baslangic), self.tz.sorgu_zamani(bitis)
        return (norm_ts(b, assume_utc=True) if b else None,
                norm_ts(e, assume_utc=True) if e else None)

    def _zaman_bilgisi(self) -> dict[str, Any]:
        """Tam saat dilimi bloğu: yalnız `kategorileri_listele` cevabında."""
        return self.tz.bilgi(self._clock())

    def _sd(self) -> dict[str, Any]:
        """Diğer cevaplarda yalnız kısa alan: `sd` (UTC farkı) ve varsa `sd_uyari`."""
        return self.tz.kisa(self._clock())

    # ------------------------------------------------------------------ araçlar
    def kategorileri_listele(self) -> dict[str, Any]:
        def fn(hub, auth, allowed):
            items = [{"kategori": k, "bitis": v} for k, v in sorted(allowed.items())]
            bilinen = set(list_topics(self.root))
            konu = {"acik": sorted(auth.konular & bilinen),
                    "kapali": sorted(bilinen - auth.konular)}
            return _Result({"kategoriler": items, "hassas_konular": konu,
                            "bitis_saat_dilimi": "UTC",
                            "saat_dilimi": self._zaman_bilgisi(),
                            "kullanim": ("Kayıtlarda 'veri' kısa alıntıdır (en çok "
                                         f"{ALINTI_UZUNLUGU} karakter); 'kisaltildi: true' ise tam "
                                         "metin için kayit_getir(id) kullanın. 'zaman' yerel "
                                         "saattir, diğer cevaplarda 'sd' UTC farkıdır. Sayım için "
                                         "'say' kullanın.")}, len(items), None)
        return self._run("kategorileri_listele", None, fn)

    def ara(self, sorgu: str, kategori: str | None = None, limit: int | None = None,
            genislet: bool = True, rol: str | None = None) -> dict[str, Any]:
        """Türkçe katlamalı arama. `genislet` (varsayılan açık): sözlükteki eşanlamlı/ilişkili
        terimlerle de aranır; kayıtlarda `eslesme` ('dogrudan'|'ilgili') ve `eslesen_terim` yazar.
        `rol` (kullanici|asistan): yalnız payload.rol'ü o değer olan kayıtlar (rolsüzler dönmez)."""
        def fn(hub, auth, allowed):
            rl = _rol_dogrula(rol)
            lim = _limit(limit, DEFAULT_SEARCH_LIMIT)
            cats = self._categories(allowed, kategori)

            def ara_(q: str) -> list[Event]:
                return _sql_ara(hub, q, cats, rl, lim, auth.konular)
            dogrudan = ara_(sorgu)
            iliskili: list[tuple[Event, esanlam.Varyant]] = []
            ozet: list[dict[str, Any]] = []
            if genislet:
                sozluk = esanlam.yukle(self.root)
                gorulen = {e.event_id for e in dogrudan}
                listeler: list[tuple[esanlam.Varyant, list[Event]]] = []
                for v in esanlam.varyantlar(sorgu, sozluk):
                    evs = [e for e in ara_(v.sorgu) if e.event_id not in gorulen]
                    listeler.append((v, evs))
                    ozet_satir = next((o for o in ozet if o["terim"] == v.asil_terim), None)
                    if ozet_satir is None:
                        ozet_satir = {"terim": v.asil_terim, "iliskili": []}
                        ozet.append(ozet_satir)
                    ozet_satir["iliskili"].append({"terim": v.eslesen_terim, "kayit": len(evs)})
                # Kısıt: doğrudan sonuçlar dolduysa bile ilişkili sonuçlara limit/3 yer ayrılır.
                if any(evs for _, evs in listeler):
                    yer = max(1, lim // 3) if len(dogrudan) >= lim else lim - len(dogrudan)
                    sira = 0
                    while len(iliskili) < yer and any(evs for _, evs in listeler):
                        v, evs = listeler[sira % len(listeler)]
                        sira += 1
                        while evs and evs[0].event_id in gorulen:
                            evs.pop(0)
                        if evs:
                            e = evs.pop(0)
                            gorulen.add(e.event_id)
                            iliskili.append((e, v))
                    dogrudan = dogrudan[:max(0, lim - len(iliskili))]
            recs = self._records(dogrudan, allowed, terimler=tokens(sorgu))
            for e, v in iliskili:
                for r in self._records([e], allowed, terimler=tokens(v.eslesen_terim)):
                    r["eslesme"] = "ilgili"          # doğrudan kayıtlarda bu iki alan yazılmaz
                    r["eslesen_terim"] = v.eslesen_terim
                    recs.append(r)
            data: dict[str, Any] = {**self._sd(), "kayitlar": recs}
            if ozet:
                data["genisletilen_terimler"] = ozet
                data["genisletme_notu"] = ("'eslesme: ilgili' kayıtlar sorgudaki sözcüğü değil "
                                           "'eslesen_terim'i içerir; tam eşleşme için "
                                           "genislet=false verin.")
            if any(r.get("zaman_gercek") is False for r in recs):
                data["not"] = _ZAMANSIZ_NOT
            return _Result(data, len(recs), categories_label(cats))
        return self._run("ara", kategori, fn)

    def zaman_cizelgesi(self, kategori: str | None = None, baslangic: str | None = None,
                        bitis: str | None = None, limit: int | None = None,
                        rol: str | None = None) -> dict[str, Any]:
        """Gerçek zamanı olan kayıtlar yeniden eskiye (`kayitlar`). Zamanı dosya tarihinden gelen
        kayıtlar (abonelik/kütüphane) çizelgeyi kirletmesin diye `zamansiz_kayitlar`da AYRI ve
        sonda verilir (aralık verildiyse hiç verilmez). Not: yalnız son `limit` kayıttır;
        SAYIM için `say` aracını kullanın. `rol` süzgeci verilirse rolsüz kayıtlar dönmez."""
        def fn(hub, auth, allowed):
            rl = _rol_dogrula(rol)
            lim = _limit(limit, DEFAULT_TIMELINE_LIMIT)
            cats = self._categories(allowed, kategori)
            since, until = self._aralik(baslangic, bitis)
            w = "hidden = 0 AND category IN (%s)" % ",".join("?" * len(cats))
            a: list[Any] = list(cats)
            if since:
                w += " AND ts >= ?"
                a.append(since)
            if until:
                w += " AND ts <= ?"
                a.append(until)
            if rl is not None:
                w += f" AND {_ROL} = ?"
                a.append(rl)
            kk, ka = konu_kosulu(auth.konular, "events.hassas_konu")
            w += f" AND {kk}"
            a += ka
            ids = [r[0] for r in hub.query(
                f"SELECT event_id FROM events WHERE {w} AND ({_GERCEK_ZAMAN}) "
                "ORDER BY ts DESC, seq DESC LIMIT ?", [*a, lim])]
            recs = self._records([hub.get_event(i) for i in ids], allowed)
            data: dict[str, Any] = {**self._sd()}
            if since or until:
                data["aralik_utc"] = {"baslangic": since, "bitis": until}
            data["kayitlar"] = recs
            zam_toplam = hub.query(
                f"SELECT COUNT(*) FROM events WHERE {w} AND NOT ({_GERCEK_ZAMAN})", a)[0][0]
            data["zamansiz_toplam"] = zam_toplam
            zam: list[dict[str, Any]] = []
            if zam_toplam and since is None and until is None:
                zids = [r[0] for r in hub.query(
                    f"SELECT event_id FROM events WHERE {w} AND NOT ({_GERCEK_ZAMAN}) "
                    "ORDER BY ts DESC, seq DESC LIMIT ?", [*a, min(lim, ZAMANSIZ_UST)])]
                zam = self._records([hub.get_event(i) for i in zids], allowed)
            data["zamansiz_kayitlar"] = zam
            if zam_toplam:
                data["not"] = (
                    f"{zam_toplam} kayıt zamansızdır (zamanı dosya tarihi: abonelik/kütüphane gibi); "
                    "çizelge sırasına dahil değildir, liste yalnız örnektir"
                    + ("; zaman aralığı verildiği için gösterilmedi." if since or until else "."))
            return _Result(data, len(recs) + len(zam), categories_label(cats))
        return self._run("zaman_cizelgesi", kategori, fn)

    def say(self, alan: str, kategori: str | None = None, tur: str | None = None,
            kaynak: str | None = None, baslangic: str | None = None, bitis: str | None = None,
            en_cok: int | None = None, rol: str | None = None) -> dict[str, Any]:
        """Toplulaştırma: `alan` değerlerine göre sayım ve en çok (top-N). Zaman alanları (ay,
        saat, gun) yerel saat dilimindedir. İzinli kategorilerle sınırlıdır."""
        def fn(hub, auth, allowed):
            if not isinstance(alan, str) or alan not in TUM_ALANLAR:
                raise ServiceError("Bilinmeyen alan. Geçerli alanlar: " + ", ".join(TUM_ALANLAR) + ".")
            rl = _rol_dogrula(rol)
            cats = self._categories(allowed, kategori)
            since, until = self._aralik(baslangic, bitis)
            veri = Toplulastirici(hub, self.tz).say(alan, kategoriler=cats, tur=tur, kaynak=kaynak,
                                                    since=since, until=until, en_cok=en_cok,
                                                    rol=rl, konular=auth.konular)
            veri.update(self._sd())
            filtre = {k: v for k, v in (("tur", tur), ("kaynak", kaynak), ("rol", rl),
                                        ("baslangic_utc", since), ("bitis_utc", until)) if v}
            if filtre:
                veri["filtre"] = filtre
            return _Result(veri, len(veri["satirlar"]), categories_label(cats))
        return self._run("say", kategori, fn)

    def persona_getir(self, kategori: str | None = None) -> dict[str, Any]:
        def fn(hub, auth, allowed):
            self._need_persona(allowed)
            if kategori is not None and kategori not in FACT_CATEGORIES:
                raise ServiceError("Bilinmeyen persona kategorisi.")
            pr = PersonaReader(hub, clock=self._clock)
            facts = pr.list_facts([kategori] if kategori else None)
            recs = []
            for f in facts:
                r = {"kategori": f.category, "kategori_basligi": CATEGORY_TITLES[f.category],
                     "durum": f.status,
                     "son_dogrulama": son_dogrulama(f), "veri": f.statement}
                if f.status == "dosyadan_alinan":
                    r["kaynak"] = pr.source_label(f.source_id)
                recs.append(r)
            return _Result({"kayitlar": recs}, len(recs), Category.PERSONA)
        return self._run("persona_getir", Category.PERSONA, fn)

    def kimlik_karti(self, kategoriler: list[str] | None = None, ozet: bool = True,
                     kisa: bool = True) -> dict[str, Any]:
        """Beyanlar + (izinli, hassas olmayan kategorilerden) veri özeti + bilinmeyenler.
        `ozet=false`: yalnız persona bölümleri. `kisa` (varsayılan açık): en çok
        KISA_KART_UST_SINIR karakterlik özet kart; `kisa=false` tam kart."""
        def fn(hub, auth, allowed):
            self._need_persona(allowed)
            if kategoriler is not None and any(k not in FACT_CATEGORIES for k in kategoriler):
                raise ServiceError("Bilinmeyen persona kategorisi.")
            pr = PersonaReader(hub, clock=self._clock)
            ozet_kat = [c for c in OZET_KATEGORILERI
                        if ozet and c in allowed and c not in Category.SENSITIVE]
            if kisa:
                cats = list(FACT_CATEGORIES) if kategoriler is None else list(kategoriler)
                md = kartmod.uret_kisa(pr, cats, veri_kategorileri=ozet_kat, saat_dilimi=self.tz)
            else:
                md = pr.export_identity_card(kategoriler, veri_kategorileri=ozet_kat,
                                             saat_dilimi=self.tz)
            n = len(pr.list_facts(kategoriler))
            return _Result({**self._sd(), "veri": md, "ozet_kategorileri": ozet_kat},
                           n, categories_label([Category.PERSONA, *ozet_kat]))
        return self._run("kimlik_karti", Category.PERSONA, fn)

    def ornekle(self, kategori: str, n: int | None = None, sorgu: str | None = None,
                rol: str | None = None, dusuk_onem: bool = False) -> dict[str, Any]:
        """İzinli bir kategoriden örnek kayıtlar (persona çıkarımı için tarama). `sorgu` verilirse
        eşleşenlerden, verilmezse rastgele örneklenir (zamana göre sıralı döner).
        Sohbet kategorisinde `rol` verilmezse yalnız `kullanici` mesajları örneklenir (asistan
        cevapları persona kanıtı olmasın); asistan için açıkça rol="asistan" verilir.
        Sorgusuz yolda önem kovaları: önce önem 2, yetmezse 1, eksik kalan 0'dan (her kovada
        rastgele); `dusuk_onem=True` önem ayrımı yapmadan rastgele örnekler."""
        def fn(hub, auth, allowed):
            if kategori is None:
                raise ServiceError("kategori gerekli.")
            rl = _rol_dogrula(rol)
            cats = self._categories(allowed, kategori)
            if rl is None and cats[0] == Category.SOHBET:
                rl = "kullanici"
            lim = _limit(n, 20)
            if sorgu:
                evs = _sql_ara(hub, sorgu, cats, rl, lim, auth.konular)
            else:
                kosul, arg = ("", []) if rl is None else (f" AND {_ROL} = ?", [rl])
                kk, ka = konu_kosulu(auth.konular, "events.hassas_konu")
                sira = "random()" if dusuk_onem else "onem DESC, random()"
                ids = [r[0] for r in hub.query(
                    f"SELECT event_id FROM events WHERE hidden = 0 AND category = ?{kosul} "
                    f"AND {kk} ORDER BY {sira} LIMIT ?", [cats[0], *arg, *ka, lim])]
                evs = sorted((hub.get_event(i) for i in ids), key=lambda e: e.ts)
            recs = self._records(evs, allowed)
            for r in recs:                      # tek kategori: kayıt başına tekrar edilmez
                r.pop("kategori", None)
            data: dict[str, Any] = {**self._sd(), "kategori": cats[0], "kayitlar": recs}
            if any(r.get("zaman_gercek") is False for r in recs):
                data["not"] = _ZAMANSIZ_NOT
            return _Result(data, len(recs), categories_label(cats))
        return self._run("ornekle", kategori, fn)

    def kayit_getir(self, id: str, baslangic: int | None = 0, uzunluk: int | None = None
                    ) -> dict[str, Any]:
        """Tek kaydın TAM metni, parça parça (`baslangic`, `uzunluk`; en çok KAYIT_PARCA_UST).
        Yok, gizli, izinsiz kategori ve GPS savunması aynı tek iletiyle reddedilir (varlık sızmaz)."""
        def fn(hub, auth, allowed):
            if not isinstance(id, str) or not id.strip():
                raise ServiceError("id gerekli.")
            try:
                b = 0 if baslangic is None else int(baslangic)
                u = KAYIT_PARCA if uzunluk is None else int(uzunluk)
            except (TypeError, ValueError):
                raise ServiceError("baslangic ve uzunluk sayı olmalı.") from None
            b, u = max(0, b), max(1, min(u, KAYIT_PARCA_UST))
            satir = hub.query("SELECT category, hassas_konu FROM events "
                              "WHERE event_id = ? AND hidden = 0", [id.strip()])
            if not satir or satir[0][0] not in allowed \
                    or not konu_izinli_mi(satir[0][1], auth.konular):
                raise PermissionDenied(_KAYIT_RET)
            e = hub.get_event(id.strip())
            kayit = self._records([e], allowed, kisalt=False)
            if not kayit:                       # GPS savunması elemiş
                raise PermissionDenied(_KAYIT_RET)
            r = kayit[0]
            tam = r["veri"]
            r["veri"] = tam[b:b + u]
            r["uzunluk"] = len(tam)
            if b + u < len(tam):
                r["devam"] = b + u
            return _Result({**self._sd(), **r}, 1, e.category)
        return self._run("kayit_getir", None, fn)

    def persona_oner(self, onermeler: list[dict[str, Any]]) -> dict[str, Any]:
        """Persona önerilerini YALNIZ öneri kuyruğuna (ana veritabanındaki `oneriler`; yazım gelen kutusu üzerinden) ekler; `facts` değişmez.
        Her önerinin kanıt olay kimlikleri geçerli olmalı ve kategorileri için okuma izni olmalı."""
        def fn(hub, auth, allowed):
            if not isinstance(onermeler, list) or not onermeler:
                raise ServiceError("'onermeler' en az bir öneri içeren liste olmalı.")
            if len(onermeler) > MAX_ONERI_CAGRI:
                raise ServiceError(f"Bir çağrıda en çok {MAX_ONERI_CAGRI} öneri gönderilebilir.")
            norm = [dogrula_onerme(o) for o in onermeler]
            ids = sorted({k for o in norm for k in o["kanit"]})
            bulunan: dict[str, str] = {}
            roller: dict[str, str | None] = {}
            onemler: dict[str, int] = {}
            for i in range(0, len(ids), 200):
                parca = ids[i:i + 200]
                for eid, cat, rl, on, hk in hub.query(
                        f"SELECT event_id, category, {_ROL}, onem, hassas_konu FROM events "
                        f"WHERE hidden = 0 AND event_id IN ({','.join('?' * len(parca))})", parca):
                    if not konu_izinli_mi(hk, auth.konular):
                        continue                # izinsiz konulu kanıt: "yok" gibi
                    bulunan[eid] = cat
                    roller[eid] = rl
                    onemler[eid] = on
            # Yok, gizli ve izinsiz kategori aynı iletiyle reddedilir (varlık sızmasın).
            if any(k not in bulunan or bulunan[k] not in allowed for k in ids):
                raise PermissionDenied("Kanıt olay kimliği geçersiz ya da kategorisi için "
                                       "okuma izni yok; hiçbir öneri eklenmedi.")
            if any(roller.get(k) == "asistan" for k in ids):
                raise PermissionDenied("Kanıt yapay zekânın cevabı, kullanıcının kendi mesajı "
                                       "değil; yalnız kullanıcının kendi kayıtları kanıt olabilir. "
                                       "Hiçbir öneri eklenmedi.")
            if any(all(onemler[k] == 0 for k in o["kanit"]) for o in norm):
                raise PermissionDenied(_DUSUK_ONEM_RET)
            kuyruk = OneriKuyrugu(self.root, clock=self._clock)
            durum, _ = kuyruk.on_kontrol(norm, hub)
            planli = sum(1 for d in durum if d is None)
            app_id = auth.ident.app_id
            etiket = categories_label({bulunan[k] for k in ids})

            def commit():
                sonuc = kuyruk.ekle(app_id, norm)
                return {"bilgi": "Öneriler kuyruğa eklendi; kullanıcı onaylamadan persona "
                                 "değişmez.",
                        "eklenen": sum(1 for r in sonuc if r["sonuc"] == "eklendi"),
                        "sonuclar": [{"sira": i, **r} for i, r in enumerate(sonuc)]}
            return _Result({}, planli, etiket, commit)
        return self._run("persona_oner", None, fn)
