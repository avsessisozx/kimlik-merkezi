"""kimlikcore: Kimlik Merkezi çekirdeği. MCP/REST/arayüz/yapay zekâ kütüphanesi içe aktarmaz."""
from .erisim import connect_erisim, init_erisim_db
from .errors import (
    FormatError,
    HubLockedError,
    HubNotEmptyError,
    HubNotFoundError,
    HubReadOnlyError,
    KimlikError,
    NotFoundError,
    PermissionDenied,
    SchemaTooNew,
    SchemaTooOld,
)
from .hub import Hub, norm_ts
from .models import (
    AddResult,
    Category,
    Event,
    EventIn,
    ExportResult,
    FactStatus,
    ImportResult,
    PurgedInfo,
    PurgeResult,
    RawFile,
    Source,
)
from .schema import SCHEMA_VERSION
from .streaming import sha256_file
from .turkish import fold

__version__ = "0.1.0"

__all__ = [
    "Hub", "Category", "FactStatus", "EventIn", "Event", "RawFile", "Source", "AddResult",
    "PurgeResult", "PurgedInfo", "ExportResult", "ImportResult", "SCHEMA_VERSION",
    "KimlikError", "HubLockedError", "PermissionDenied", "FormatError", "SchemaTooNew",
    "SchemaTooOld", "HubNotFoundError", "HubReadOnlyError", "HubNotEmptyError", "NotFoundError",
    "init_erisim_db", "connect_erisim", "sha256_file", "fold", "norm_ts", "__version__",
]
