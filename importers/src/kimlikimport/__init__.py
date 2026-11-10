"""kimlikimport: Kimlik Merkezi içe aktarıcıları (INTERFACES §4).

Çalıştırıcı `kimlikimport.run.run(...)` olarak çağrılır (çekirdek CLI `from kimlikimport import run`
ile modülü alıp `run.run` kullanır); bu yüzden pakette `run` adı modül olarak kalır.
"""
from .base import DetectResult, FormatReport, Importer, ImportFormatError
from .run import RunResult

__version__ = "0.1.0"
__all__ = ["DetectResult", "FormatReport", "ImportFormatError", "Importer", "RunResult", "__version__"]
