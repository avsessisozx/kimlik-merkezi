"""Claude Desktop ayar dosyasına MCP girişi ekleme ("Claude'a ekle" düğmesi mantığı).

DOĞRULANMADI: ayar dosyasının yeri resmî belgeden okunamadı (modelcontextprotocol.io bu oturumda
erişime kapalıydı). Aşağıdaki adaylar bilinen/yaygın konumlardır; dosya bulunamazsa hiçbir şeye
dokunulmaz ve kopyalanabilir ayar metni verilir. Yalnızca VAR OLAN ve geçerli JSON olan dosya değiştirilir.
Sıra: önce yedek, sonra (anahtar üretimi `anahtar_uret` geri çağrısıyla, doğrulamadan sonra) yazma.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

DOSYA_AD = "claude_desktop_config.json"
GIRIS_AD = "kimlik-merkezi"


def adaylar(env: dict[str, str] | None = None) -> list[Path]:
    env = os.environ if env is None else env
    out: list[Path] = []
    appdata = env.get("APPDATA")
    if appdata:
        out.append(Path(appdata) / "Claude" / DOSYA_AD)
    local = env.get("LOCALAPPDATA")
    if local:  # mağaza/MSIX tipi paketlenmiş kurulumlarda yol sanallaştırılabilir (doğrulanmadı)
        for p in sorted(glob.glob(str(Path(local) / "Packages" / "Claude_*" / "LocalCache" / "Roaming" / "Claude" / DOSYA_AD))):
            out.append(Path(p))
    return out


def arama_yerleri(env: dict[str, str] | None = None) -> list[str]:
    """Kullanıcıya gösterilecek: `bul`un baktığı yerler (adaylar() ile aynı kalıplar). Ortam değişkeni
    tanımlıysa gerçek yol, değilse %DEĞİŞKEN% kalıbı yazılır; menü/arayüz adı UYDURULMAZ."""
    env = os.environ if env is None else env
    appdata, local = env.get("APPDATA"), env.get("LOCALAPPDATA")
    return [str(Path(appdata) / "Claude" / DOSYA_AD) if appdata else "%APPDATA%\\Claude\\" + DOSYA_AD,
            (str(Path(local) / "Packages" / "Claude_*" / "LocalCache" / "Roaming" / "Claude" / DOSYA_AD) if local
             else "%LOCALAPPDATA%\\Packages\\Claude_*\\LocalCache\\Roaming\\Claude\\" + DOSYA_AD)]


def bul(env: dict[str, str] | None = None) -> Path | None:
    for p in adaylar(env):
        if p.is_file():
            return p
    return None


def mcp_komutu() -> tuple[str, list[str]]:
    """MCP sunucusunu başlatan komut. Kurulu sürümde pencere açmayan konsol exe'si yanındadır."""
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).with_name("kimlikmerkezi-mcp.exe")), []
    return sys.executable, ["-m", "kimlikserver.mcp"]


def giris_olustur(veri_klasoru: str | Path, anahtar: str) -> dict:
    komut, argumanlar = mcp_komutu()
    return {"command": komut, "args": argumanlar,
            "env": {"KIMLIK_VERI": str(veri_klasoru), "KIMLIK_ANAHTAR": anahtar}}


def ayar_metni(giris: dict, ad: str = GIRIS_AD) -> str:
    """Elle yapıştırılabilir ayar metni (`mcpServers` bloğu)."""
    return json.dumps({"mcpServers": {ad: giris}}, ensure_ascii=False, indent=2)


@dataclass
class Sonuc:
    durum: str                       # eklendi | guncellendi | bulunamadi | bozuk | hata
    mesaj: str
    dosya: str | None = None
    yedek: str | None = None
    metin: str | None = None         # eklenemediyse: kopyalanabilir ayar
    app_id: str | None = None
    uyari: list[str] = field(default_factory=list)
    aranan: list[str] = field(default_factory=list)   # eklenemediyse: bakılan dosya yolları

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _oku(yol: Path) -> dict:
    ham = yol.read_bytes().decode("utf-8-sig")
    if not ham.strip():
        return {}
    veri = json.loads(ham)
    if not isinstance(veri, dict):
        raise ValueError("Ayar dosyasının en üstü bir nesne değil.")
    if "mcpServers" in veri and not isinstance(veri["mcpServers"], dict):
        raise ValueError("'mcpServers' bir nesne değil.")
    return veri


def ekle(yol: Path | None, anahtar_uret: Callable[[], tuple[str, str]],
         veri_klasoru: str | Path, *, ad: str = GIRIS_AD,
         simdi: Callable[[], datetime] = datetime.now) -> Sonuc:
    """`anahtar_uret() -> (app_id, düz_anahtar)` yalnızca dosya doğrulandıktan sonra çağrılır;
    böylece başarısız bir ekleme arkada boşta anahtar bırakmaz."""
    if yol is None or not Path(yol).is_file():
        app_id, anahtar = anahtar_uret()
        return Sonuc("bulunamadi",
                     "Claude Desktop ayar dosyası bulunamadı (konum doğrulanmadı). Aşağıdaki metni "
                     "Claude Desktop'un ayar dosyasındaki 'mcpServers' bölümüne kendiniz ekleyin.",
                     metin=ayar_metni(giris_olustur(veri_klasoru, anahtar), ad), app_id=app_id)
    yol = Path(yol)
    try:
        mevcut = _oku(yol)
    except (ValueError, UnicodeDecodeError) as e:
        app_id, anahtar = anahtar_uret()
        return Sonuc("bozuk", f"Ayar dosyası okunamadı ({type(e).__name__}); dosyaya DOKUNULMADI. "
                     "Aşağıdaki metni elle ekleyebilirsiniz.", dosya=str(yol),
                     metin=ayar_metni(giris_olustur(veri_klasoru, anahtar), ad), app_id=app_id)
    except OSError as e:
        return Sonuc("hata", f"Ayar dosyası okunamadı: {e.strerror or e}", dosya=str(yol))

    yedek = yol.with_name(f"{yol.name}.kimlik-yedek-{simdi():%Y%m%d-%H%M%S}")
    n = 1
    while yedek.exists():
        yedek = yol.with_name(f"{yol.name}.kimlik-yedek-{simdi():%Y%m%d-%H%M%S}-{n}")
        n += 1
    try:
        shutil.copy2(yol, yedek)
    except OSError as e:
        return Sonuc("hata", f"Yedek alınamadı, dosyaya dokunulmadı: {e.strerror or e}", dosya=str(yol))

    app_id, anahtar = anahtar_uret()
    giris = giris_olustur(veri_klasoru, anahtar)
    var_idi = ad in mevcut.get("mcpServers", {})
    mevcut.setdefault("mcpServers", {})[ad] = giris
    gecici = yol.with_name(yol.name + ".kimlik-tmp")
    try:
        gecici.write_text(json.dumps(mevcut, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(gecici, yol)
        if _oku(yol)["mcpServers"][ad] != giris:  # geri okuma doğrulaması
            raise OSError("yazılan dosya doğrulanamadı")
    except (OSError, ValueError, KeyError) as e:
        try:
            shutil.copy2(yedek, yol)
        except OSError:
            pass
        try:
            gecici.unlink()
        except OSError:
            pass
        return Sonuc("hata", f"Yazılamadı, eski dosya geri konuldu: {e}", dosya=str(yol), yedek=str(yedek),
                     metin=ayar_metni(giris, ad), app_id=app_id)
    mesaj = ("Mevcut 'kimlik-merkezi' girişi yeni anahtarla güncellendi. " if var_idi else "Giriş eklendi. ")
    return Sonuc("guncellendi" if var_idi else "eklendi",
                 mesaj + "Değişikliğin görünmesi için Claude Desktop'u yeniden başlatın.",
                 dosya=str(yol), yedek=str(yedek), app_id=app_id)
