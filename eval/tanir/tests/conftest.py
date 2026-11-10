import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from ag_koruma import ag_korumasi, pytest_configure, pytest_unconfigure, sifreleme_saglayici_yalitimi, girisde_baslatma_yalitimi  # noqa: E402,F401
