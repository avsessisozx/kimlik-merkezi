# PyInstaller: iki exe, tek klasör.
#   KimlikMerkezi.exe       pencereli (konsolsuz): tepsi + yerel web arayüzü
#   kimlikmerkezi-mcp.exe   konsol: MCP stdio (pencere/tepsi açmaz), ayrıca `saglik` ve `surum`
# Derleme: windows/paket klasöründen `python -m PyInstaller --noconfirm kimlikmerkezi.spec`
import os
from importlib import metadata

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

gizli = (collect_submodules("mcp", filter=lambda n: not n.startswith("mcp.cli"))
         + collect_submodules("mcp_types")
         + collect_submodules("ijson")            # C uzantısı (yajl2_c) dahil
         + ["cryptography.hazmat.primitives.ciphers.aead"]   # şifreleme (docs/SIFRELEME.md)
         + collect_submodules("kimlikcore") + collect_submodules("kimlikserver")
         + collect_submodules("kimlikimport") + collect_submodules("kimlikwin"))
veri = collect_data_files("mcp") + collect_data_files("kimlikwin")
# Lisans metinleri kurulu pakete girer (_internal/lisanslar/...): MIT/LGPL vb. ikili dağıtımda metin ister.
kok = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
lisans_dosyalari = [(os.path.join(kok, "LICENSE"), "lisanslar"),
                    (os.path.join(kok, "THIRD-PARTY-NOTICES.md"), "lisanslar")]
lisans_dosyalari += [(str(f.locate()), "lisanslar/pystray")
                     for f in (metadata.distribution("pystray").files or []) if f.name.startswith("COPYING")]
disla = ["unittest", "pydoc", "test"]

a = Analysis(["giris_pencereli.py"], pathex=["."], hiddenimports=gizli, datas=veri + lisans_dosyalari, excludes=disla,
             noarchive=True)   # Python modülleri exe içindeki arşivde değil, ayrı .pyc dosyaları (LGPL: pystray değiştirilebilir)
b = Analysis(["giris_konsol.py"], pathex=["."], hiddenimports=gizli, datas=veri,
             excludes=disla + ["PIL", "pystray", "tkinter"], noarchive=True)
MERGE((a, "giris_pencereli", "KimlikMerkezi"), (b, "giris_konsol", "kimlikmerkezi-mcp"))
pa, pb = PYZ(a.pure), PYZ(b.pure)
ea = EXE(pa, a.scripts, [], exclude_binaries=True, name="KimlikMerkezi", console=False, icon="app.ico")
eb = EXE(pb, b.scripts, [], exclude_binaries=True, name="kimlikmerkezi-mcp", console=True, icon="app.ico")
COLLECT(ea, a.binaries, a.datas, eb, b.binaries, b.datas, name="KimlikMerkezi")
