"""Kullanıcının yerel saat dilimi (araç çıktılarında UTC yerine/yanında yerel saat).

Çözümleme sırası (ilk bulunan):
1. Kurucuya verilen ad (`ad=`; ör. test ya da uygulama ayarı),
2. `KIMLIK_SAAT_DILIMI` ortam değişkeni: IANA adı (`Europe/Istanbul`) ya da sabit fark
   (`UTC+03:00`, `+03:00`, `+3`),
3. sunucunun yerel saati (`TZ` ortam değişkeni, `/etc/timezone`, `/etc/localtime`; hiçbiri adı
   vermezse sistemin sabit farkı).
Windows uygulamasının ayarlarında (ayarlar.json) şu an saat dilimi alanı YOKTUR; MCP süreci
yapay zekâ uygulaması tarafından başlatıldığı için ortam değişkeniyle yapılandırılır.
Windows'ta IANA adları için `tzdata` paketi gerekir; yoksa ad çözülemez, sistem saatine düşülür
ve çıktıdaki `uyari` alanı bunu söyler (sessizce UTC denmez).
Depolanan zamanlar her zaman UTC kalır; burası yalnızca gösterimdir.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ENV_ADI = "KIMLIK_SAAT_DILIMI"
_SABIT = re.compile(r"^(?:UTC|GMT)?\s*([+-])(\d{1,2})(?::?(\d{2}))?$", re.IGNORECASE)


def _fark_metni(td: timedelta) -> str:
    dk = int(td.total_seconds() // 60)
    isaret = "+" if dk >= 0 else "-"
    dk = abs(dk)
    return f"{isaret}{dk // 60:02d}:{dk % 60:02d}"


def _sabit_fark(metin: str) -> timezone | None:
    s = metin.strip()
    if s.upper() in ("UTC", "Z", "GMT"):
        return timezone.utc
    m = _SABIT.match(s)
    if not m:
        return None
    sa, dk = int(m.group(2)), int(m.group(3) or 0)
    if sa > 14 or dk > 59:
        return None
    td = timedelta(hours=sa, minutes=dk)
    return timezone(td if m.group(1) == "+" else -td)


def _sistem_adi() -> str | None:
    tz = os.environ.get("TZ", "").strip().lstrip(":")
    adaylar = [tz] if tz else []
    try:
        adaylar.append(Path("/etc/timezone").read_text(encoding="utf-8").strip())
    except OSError:
        pass
    try:
        hedef = os.path.realpath("/etc/localtime")
        if "zoneinfo/" in hedef:
            adaylar.append(hedef.split("zoneinfo/", 1)[1])
    except OSError:
        pass
    for a in adaylar:
        if a:
            try:
                ZoneInfo(a)
                return a
            except (ZoneInfoNotFoundError, ValueError, OSError):
                continue
    return None


@dataclass(frozen=True)
class YerelSaat:
    ad: str            # "Europe/Istanbul" ya da "UTC+03:00"
    tz: tzinfo
    kaynak: str        # kullanıcıya gösterilen çözümleme kaynağı
    uyari: str | None = None

    # ------------------------------------------------------------ çözümleme
    @classmethod
    def cozumle(cls, ad: str | None = None, ortam: dict[str, str] | None = None) -> "YerelSaat":
        ortam = os.environ if ortam is None else ortam
        istenen, kaynak = (ad, "ayar") if ad else (ortam.get(ENV_ADI, "").strip() or None,
                                                   f"{ENV_ADI} ayarı")
        uyari = None
        if istenen:
            sabit = _sabit_fark(istenen)
            if sabit is not None:
                return cls(_fark_etiketi(sabit), sabit, kaynak)
            try:
                return cls(istenen, ZoneInfo(istenen), kaynak)
            except (ZoneInfoNotFoundError, ValueError, OSError):
                uyari = (f"'{istenen}' saat dilimi çözülemedi (IANA adı ya da UTC+03:00 biçimi "
                         "bekleniyor; Windows'ta tzdata gerekebilir); sunucunun yerel saati "
                         "kullanıldı.")
        sistem = _sistem_adi()
        if sistem:
            return cls(sistem, ZoneInfo(sistem), "sunucu yerel saati", uyari)
        fark = datetime.now().astimezone().utcoffset() or timedelta(0)
        sabit = timezone(fark)
        ad_ = "UTC" if fark == timedelta(0) else _fark_etiketi(sabit)
        return cls(ad_, sabit, "sunucu yerel saati (sistem adı bulunamadı; sabit fark)", uyari)

    # ------------------------------------------------------------ dönüşüm
    def farki(self, an: datetime) -> timedelta:
        return an.astimezone(self.tz).utcoffset() or timedelta(0)

    def yerel(self, ts_utc: str | None) -> str | None:
        """`2026-11-09T05:30:00Z` -> `2026-11-09T08:30:00+03:00`."""
        if not ts_utc:
            return None
        dt = datetime.fromisoformat(ts_utc.replace("Z", "+00:00")).astimezone(self.tz)
        return dt.isoformat(timespec="seconds")

    def yerel_dt(self, ts_utc: str) -> datetime:
        return datetime.fromisoformat(ts_utc.replace("Z", "+00:00")).astimezone(self.tz)

    def sorgu_zamani(self, deger: str | None) -> str | None:
        """Araç girdisi (baslangic/bitis) -> UTC ISO metni. Saat dilimi yazılmamışsa YEREL saat
        sayılır (UTC değil); 'Z' ya da +hh:mm varsa olduğu gibi."""
        if deger is None or str(deger).strip() == "":
            return None
        try:
            dt = datetime.fromisoformat(str(deger).strip().replace("Z", "+00:00"))
        except ValueError:
            return str(deger)  # bozuk biçim: çekirdek FormatError üretir
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=self.tz)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def bilgi(self, an: datetime | None = None) -> dict:
        an = an or datetime.now(timezone.utc)
        d = {"ad": self.ad, "utc_farki": _fark_metni(self.farki(an)), "kaynak": self.kaynak,
             "aciklama": ("'yerel_zaman' ve saat/gün dağılımları bu dilimdedir; 'zaman' alanları "
                          "UTC'dir (sonu Z). Saat içeren her cevapta hangisini kastettiğinizi "
                          "belirtin.")}
        if self.uyari:
            d["uyari"] = self.uyari
        return d


def _fark_etiketi(tz: timezone) -> str:
    fark = tz.utcoffset(None) or timedelta(0)
    return "UTC" if fark == timedelta(0) else f"UTC{_fark_metni(fark)}"


UTC = YerelSaat("UTC", timezone.utc, "ayar")
