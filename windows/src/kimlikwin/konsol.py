"""`kimlikmerkezi-mcp.exe` (konsol exe'si) girişi.

Argümansız: MCP sunucusu (stdio); pencere ve tepsi AÇMAZ. Claude Desktop/Code bunu başlatır.
`saglik`, `surum` gibi komutlar konsolda çıktı verir (CI ve destek için)."""
import sys

from .uygulama import main

if __name__ == "__main__":
    sys.exit(main(["mcp"] if len(sys.argv) == 1 else sys.argv[1:]))
