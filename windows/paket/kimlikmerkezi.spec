# PyInstaller: iki exe, tek klasör.
#   KimlikMerkezi.exe       pencereli (konsolsuz): tepsi + yerel web arayüzü
#   kimlikmerkezi-mcp.exe   konsol: MCP stdio (pencere/tepsi açmaz), ayrıca `saglik` ve `surum`
# Derleme: windows/paket klasöründen `python -m PyInstaller --noconfirm kimlikmerkezi.spec`
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

gizli = (collect_submodules("mcp", filter=lambda n: not n.startswith("mcp.cli"))
         + collect_submodules("mcp_types")
         + collect_submodules("ijson")            # C uzantısı (yajl2_c) dahil
         + collect_submodules("kimlikcore") + collect_submodules("kimlikserver")
         + collect_submodules("kimlikimport") + collect_submodules("kimlikwin"))
veri = collect_data_files("mcp") + collect_data_files("kimlikwin")
disla = ["unittest", "pydoc", "test"]

a = Analysis(["giris_pencereli.py"], pathex=["."], hiddenimports=gizli, datas=veri, excludes=disla)
b = Analysis(["giris_konsol.py"], pathex=["."], hiddenimports=gizli, datas=veri,
             excludes=disla + ["PIL", "pystray", "tkinter"])
MERGE((a, "giris_pencereli", "KimlikMerkezi"), (b, "giris_konsol", "kimlikmerkezi-mcp"))
pa, pb = PYZ(a.pure), PYZ(b.pure)
ea = EXE(pa, a.scripts, [], exclude_binaries=True, name="KimlikMerkezi", console=False, icon="app.ico")
eb = EXE(pb, b.scripts, [], exclude_binaries=True, name="kimlikmerkezi-mcp", console=True, icon="app.ico")
COLLECT(ea, a.binaries, a.datas, eb, b.binaries, b.datas, name="KimlikMerkezi")
