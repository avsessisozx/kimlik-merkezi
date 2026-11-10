"""Persona öneri kuyruğu (`kimlik.db` içindeki `oneriler`/`bastirilan` tabloları) ve onay işlemleri.

Yapay zekâ (MCP `persona_oner`) YALNIZ öneri kuyruğuna yazar; `facts` tablosuna dokunamaz.
Kullanıcı onaylayınca (Windows uygulaması `OneriYonetici` çağırır) öneri `facts`'e
`beyan_edilen` olarak düşer. Onaylanmamış öneri hiçbir çıktıda (persona_getir, kimlik kartı)
görünmez, çünkü o çıktılar yalnız `facts` okur.

Depolama (şema v4): kuyruk artık ayrı, şifresiz `oneri.db` DEĞİL; şifreli ana veritabanındadır.
MCP süreçleri ana veritabanına doğrudan yazamaz (tek yazan süreç kuralı, şifreli kapsayıcı), bu yüzden
`ekle` her öneriyi `gelen/` altında kendi (şifreli) dosyasına bırakır (kimlikcore.gelen); yazan Hub
(Windows uygulaması / `baslat`) bunları `oneriler` tablosuna işler. Birden çok süreç aynı anda yazsa da
hiçbiri bir diğerinin dosyasına dokunmaz: kayıp ve kilit çakışması yoktur. Okuyucular (`listele`,
`on_kontrol`) tablo + henüz işlenmemiş gelen dosyalarını birlikte görür.

Bastırma: ifade; Türkçe katlama + noktalama/boşluk normalleşmesinden sonra (kategoriyle birlikte)
SHA-256 ile özetlenir. Aynı özetli bir öneri kuyrukta bekliyorsa, daha önce onaylandı/düzeltildi/
reddedildiyse ya da `bastirilan`daysa ("hiç doğru değil") yeniden kuyruğa girmez. Sınır: yalnız
normalleşmiş AYNI ifade yakalanır; anlamca benzer ama farklı sözcüklü ifade yakalanmaz. Yazma anındaki
denetim, tam aynı anda gelen iki süreç için kesin değildir: ikisi de "eklendi" görebilir; yazan Hub
birleştirirken ikincisini yinelenen olarak atar (kayıp değil, çift kayıt önlenir).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kimlikcore import FormatError, Hub, HubNotFoundError, KimlikError, NotFoundError
from kimlikcore.gelen import GelenKutusu
from kimlikcore.turkish import tokens

from ._db import Clock, iso, utc_now
from .persona import FACT_CATEGORIES, MAX_STATEMENT, Persona

MAX_BEKLEYEN = 500          # kuyruk dolarsa yeni öneri alınmaz (taşırma/spam koruması)
MAX_ONERI_CAGRI = 20        # bir çağrıdaki öneri sayısı
MAX_KANIT = 20              # bir önerideki kanıt sayısı
DURUMLAR = ("bekliyor", "onaylandi", "duzeltildi", "reddedildi", "hic_dogru_degil")


class OneriYazilamadi(KimlikError):
    """Öneri kuyruğuna (gelen kutusu) yazılamadı."""


def ifade_ozeti(statement: str, category: str) -> str:
    norm = " ".join(tokens(statement))  # Türkçe katlama, noktalama atılır, boşluklar tekleşir
    return hashlib.sha256(f"{category}\n{norm}".encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class Oneri:
    oneri_id: str
    ts: str
    app_id: str
    statement: str
    category: str
    fact_key: str | None
    kanit_event_ids: list[str]
    guven: float
    durum: str
    karar_ts: str | None
    duzeltilmis_ifade: str | None
    fact_id: str | None


_COLS = ("oneri_id, ts, app_id, statement, category, fact_key, kanit_event_ids, guven, durum, "
         "karar_ts, duzeltilmis_ifade, fact_id")


def _oneri(r: tuple) -> Oneri:
    return Oneri(r[0], r[1], r[2], r[3], r[4], r[5], json.loads(r[6]), r[7], r[8], r[9], r[10], r[11])


def dogrula_onerme(o: Any) -> dict[str, Any]:
    """Tek öneriyi doğrular/normalleştirir: {ifade, kategori, kanit, guven, anahtar}."""
    if not isinstance(o, dict):
        raise FormatError("Her öneri nesne olmalı.")
    ifade = o.get("ifade")
    if not isinstance(ifade, str) or not ifade.strip():
        raise FormatError("Önerinin 'ifade' alanı boş olamaz.")
    ifade = ifade.strip()
    if len(ifade) > MAX_STATEMENT:
        raise FormatError(f"'ifade' en çok {MAX_STATEMENT} karakter olabilir.")
    kat = o.get("kategori")
    if kat not in FACT_CATEGORIES:
        raise FormatError("Geçersiz persona kategorisi: " + ", ".join(FACT_CATEGORIES)
                          + " değerlerinden biri olmalı.")
    kanit = o.get("kanit")
    if not isinstance(kanit, list) or not kanit or not all(isinstance(k, str) and k for k in kanit):
        raise FormatError("'kanit' en az bir olay kimliği (metin) içeren liste olmalı.")
    if len(kanit) > MAX_KANIT:
        raise FormatError(f"'kanit' en çok {MAX_KANIT} olay kimliği içerebilir.")
    guven = o.get("guven")
    if isinstance(guven, bool) or not isinstance(guven, (int, float)) or not 0 <= guven <= 1:
        raise FormatError("'guven' 0 ile 1 arasında sayı olmalı.")
    anahtar = o.get("anahtar")
    if anahtar is not None and not isinstance(anahtar, str):
        raise FormatError("'anahtar' metin olmalı.")
    return {"ifade": ifade, "kategori": kat, "kanit": list(dict.fromkeys(kanit)),
            "guven": float(guven), "anahtar": (anahtar or "").strip() or None}


def _gelen_oneri(k: dict[str, Any]) -> Oneri:
    return Oneri(k["oneri_id"], k["ts"], k["app_id"], k["statement"], k["category"], k.get("fact_key"),
                 list(k["kanit_event_ids"]), float(k["guven"]), "bekliyor", None, None, None)


class OneriKuyrugu:
    """Öneri kuyruğu okuma/ekleme (MCP süreçleri ve Windows uygulaması)."""

    def __init__(self, root: Path | str, *, clock: Clock = utc_now,
                 gelen: Callable[[Path], GelenKutusu] = GelenKutusu.ac):
        self.root = Path(root)
        self._clock = clock
        self._gelen = gelen

    @contextmanager
    def _okuyucu(self, hub: Hub | None):
        """Verilen Hub'ı kullanır; yoksa salt okunur açıp kapatır (klasör yoksa None verir)."""
        if hub is not None:
            yield hub
            return
        try:
            h = Hub.open(self.root, write=False)
        except HubNotFoundError:
            yield None
            return
        try:
            yield h
        finally:
            h.close()

    @staticmethod
    def _durum_kontrol(hub: Hub | None, bekleyenler: set[str], h: str) -> str | None:
        """None: eklenebilir; aksi halde neden kodu. `bekleyenler`: henüz işlenmemiş gelen dosyaları."""
        if h in bekleyenler:
            return "zaten_kuyrukta"
        if hub is None:
            return None
        if hub.query_one("SELECT 1 FROM bastirilan WHERE ifade_hash = ?", (h,)):
            return "bastirilmis"
        r = hub.query_one("SELECT durum FROM oneriler WHERE ifade_hash = ? ORDER BY ts DESC LIMIT 1", (h,))
        if r is None:
            return None
        return {"bekliyor": "zaten_kuyrukta", "onaylandi": "zaten_onayli",
                "duzeltildi": "zaten_onayli", "reddedildi": "reddedilmis",
                "hic_dogru_degil": "bastirilmis"}[r[0]]

    def _bekleyen_gelen(self) -> list[dict[str, Any]]:
        kayitlar, _bozuk = self._gelen(self.root).listele("oneri")
        return [k for _ad, k in kayitlar]

    def on_kontrol(self, onermeler: list[dict[str, Any]], hub: Hub | None = None
                   ) -> tuple[list[str | None], int]:
        """Her öneri için (eklenebilir ise None | neden kodu) ve kuyruktaki bekleyen sayısı."""
        gelen = self._bekleyen_gelen()
        bekleyenler = {k["ifade_hash"] for k in gelen}
        with self._okuyucu(hub) as h:
            sonuc = []
            gorulen: set[str] = set()
            for o in onermeler:
                ho = ifade_ozeti(o["ifade"], o["kategori"])
                s = "zaten_kuyrukta" if ho in gorulen else self._durum_kontrol(h, bekleyenler, ho)
                gorulen.add(ho)
                sonuc.append(s)
            bekleyen = len(gelen) + (0 if h is None else h.query_one(
                "SELECT COUNT(*) FROM oneriler WHERE durum = 'bekliyor'")[0])
            return sonuc, bekleyen

    # ---- yazma
    def ekle(self, app_id: str, onermeler: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Doğrulanmış önerileri (dogrula_onerme çıktısı) kuyruğa ekler. Her biri için
        {"sonuc": "eklendi"|<neden kodu>, "oneri_id"?}. Hata olursa bu çağrıda yazılanlar geri
        silinir (hiçbiri eklenmez). Her öneri kendi şifreli gelen dosyasına yazılır."""
        now = iso(self._clock())
        yazilan: list[str] = []
        kutu = None
        try:
            kutu = self._gelen(self.root)
            bekleyenler = {k["ifade_hash"] for k in self._bekleyen_gelen()}
            gelen_sayisi = len(bekleyenler)
            with self._okuyucu(None) as h:
                bekleyen = gelen_sayisi + (0 if h is None else h.query_one(
                    "SELECT COUNT(*) FROM oneriler WHERE durum = 'bekliyor'")[0])
                out = []
                for o in onermeler:
                    ho = ifade_ozeti(o["ifade"], o["kategori"])
                    neden = self._durum_kontrol(h, bekleyenler, ho)
                    if neden is None and bekleyen >= MAX_BEKLEYEN:
                        neden = "kuyruk_dolu"
                    if neden is not None:
                        out.append({"sonuc": neden})
                        continue
                    oid = str(uuid.uuid4())
                    yazilan.append(kutu.yaz("oneri", {
                        "oneri_id": oid, "ts": now, "app_id": app_id, "statement": o["ifade"],
                        "category": o["kategori"], "fact_key": o["anahtar"],
                        "kanit_event_ids": o["kanit"], "guven": o["guven"], "ifade_hash": ho}))
                    bekleyenler.add(ho)
                    bekleyen += 1
                    out.append({"sonuc": "eklendi", "oneri_id": oid})
                return out
        except (KimlikError, sqlite3.Error, OSError) as e:
            for ad in yazilan:
                try:
                    kutu.sil(ad)
                except OSError:
                    pass
            raise OneriYazilamadi("Öneri kuyruğu yazılamadı.") from e

    def listele(self, durum: str | None = "bekliyor", *, limit: int = 500, hub: Hub | None = None
                ) -> list[Oneri]:
        """Tablodaki öneriler + (durum `bekliyor`/None ise) henüz işlenmemiş gelen önerileri."""
        if durum is not None and durum not in DURUMLAR:
            raise FormatError(f"Bilinmeyen durum: {durum}")
        out: list[Oneri] = []
        with self._okuyucu(hub) as h:
            if h is not None:
                sql = f"SELECT {_COLS} FROM oneriler"
                args: list[Any] = []
                if durum is not None:
                    sql += " WHERE durum = ?"
                    args.append(durum)
                sql += " ORDER BY ts, oneri_id LIMIT ?"
                out = [_oneri(r) for r in h.query(sql, [*args, int(limit)])]
        if durum in (None, "bekliyor"):
            var = {o.oneri_id for o in out}
            out += [o for o in map(_gelen_oneri, self._bekleyen_gelen()) if o.oneri_id not in var]
            out.sort(key=lambda o: (o.ts, o.oneri_id))
        return out[: int(limit)]


class OneriYonetici:
    """Kullanıcı kararları (Windows uygulaması çağırır; yazan Hub gerekir)."""

    def __init__(self, hub: Hub, root: Path | str | None = None, *, clock: Clock = utc_now,
                 persona: Persona | None = None):
        self.hub = hub
        self.root = Path(root) if root is not None else hub.root
        self._clock = clock
        self.persona = persona or Persona(hub, clock=clock)
        self.kuyruk = OneriKuyrugu(self.root, clock=clock)

    def kuyruk_listele(self, durum: str | None = "bekliyor") -> list[Oneri]:
        self.hub.gelen_birlestir()
        return self.kuyruk.listele(durum, hub=self.hub)

    def _bekleyen(self, c: sqlite3.Connection, oneri_id: str) -> Oneri:
        r = c.execute(f"SELECT {_COLS} FROM oneriler WHERE oneri_id = ?", (oneri_id,)).fetchone()
        if r is None:
            raise NotFoundError(f"Öneri yok: {oneri_id}")
        o = _oneri(r)
        if o.durum != "bekliyor":
            raise FormatError(f"Öneri zaten karara bağlanmış ({o.durum}).")
        return o

    def _karar(self, oneri_id: str, durum: str, *, fact_id: str | None = None,
               duzeltilmis: str | None = None, bastir: bool = False) -> None:
        now = iso(self._clock())
        self.hub.gelen_birlestir()
        with self.hub.transaction() as c:
            o = self._bekleyen(c, oneri_id)
            c.execute("UPDATE oneriler SET durum = ?, karar_ts = ?, fact_id = ?, "
                      "duzeltilmis_ifade = ? WHERE oneri_id = ?",
                      (durum, now, fact_id, duzeltilmis, oneri_id))
            if bastir:
                c.execute("INSERT OR IGNORE INTO bastirilan(ifade_hash, ts, category) "
                          "VALUES (?, ?, ?)",
                          (ifade_ozeti(o.statement, o.category), now, o.category))

    def _bekleyen_oku(self, oneri_id: str) -> Oneri:
        self.hub.gelen_birlestir()
        with self.hub.transaction() as c:
            return self._bekleyen(c, oneri_id)

    def onayla(self, oneri_id: str) -> str:
        """Öneriyi `facts`'e `beyan_edilen` olarak ekler (çelişki varsa mevcut çelişki
        yönetimi çalışır). fact_id döner. Önce fact yazılır; aynı metin yeniden eklenirse
        `add_fact` yineleme yapmaz, bu yüzden yarım kalan onay güvenle tekrarlanabilir."""
        o = self._bekleyen_oku(oneri_id)
        fid = self.persona.add_fact(o.statement, o.category, fact_key=o.fact_key)
        self._karar(oneri_id, "onaylandi", fact_id=fid)
        return fid

    def duzelt(self, oneri_id: str, yeni_ifade: str) -> str:
        """Kullanıcı ifadeyi düzeltir; düzeltilmiş metin `beyan_edilen` olarak eklenir."""
        o = self._bekleyen_oku(oneri_id)
        fid = self.persona.add_fact(yeni_ifade, o.category, fact_key=o.fact_key)
        self._karar(oneri_id, "duzeltildi", fact_id=fid, duzeltilmis=yeni_ifade.strip())
        return fid

    def reddet(self, oneri_id: str) -> None:
        self._karar(oneri_id, "reddedildi")

    def hic_dogru_degil(self, oneri_id: str) -> None:
        """Reddeder ve benzer (aynı normalleşmiş ifade) önerinin bir daha kuyruğa girmesini engeller."""
        self._karar(oneri_id, "hic_dogru_degil", bastir=True)

    def toplu_reddet(self, oneri_idleri: Iterable[str] | None = None) -> int:
        """Verilen (ya da `None`: tüm bekleyen) önerileri reddeder; sayıyı döner."""
        now = iso(self._clock())
        self.hub.gelen_birlestir()
        with self.hub.transaction() as c:
            if oneri_idleri is None:
                return c.execute("UPDATE oneriler SET durum = 'reddedildi', karar_ts = ? "
                                 "WHERE durum = 'bekliyor'", (now,)).rowcount
            n = 0
            for oid in dict.fromkeys(oneri_idleri):
                n += c.execute("UPDATE oneriler SET durum = 'reddedildi', karar_ts = ? "
                               "WHERE oneri_id = ? AND durum = 'bekliyor'", (now, oid)).rowcount
            return n
