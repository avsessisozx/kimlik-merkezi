"""Çekirdek hata sınıfları (INTERFACES §8)."""
from __future__ import annotations


class KimlikError(Exception):
    """Tüm çekirdek hatalarının tabanı."""


class HubLockedError(KimlikError):
    """Veri klasöründe başka bir yazan süreç var (hub.lock)."""


class PermissionDenied(KimlikError):
    """Erişim izni yok (server katmanı kullanır)."""


class FormatError(KimlikError, ValueError):
    """Girdi ya da dosya biçimi geçersiz."""


class SchemaTooNew(KimlikError):
    """Veritabanı bu çekirdekten daha yeni bir şema sürümünde."""


class SchemaTooOld(KimlikError):
    """Veritabanı eski sürümde; yazan süreç açıp göç ettirmeli (salt okunur açılamaz)."""


class HubNotFoundError(KimlikError, FileNotFoundError):
    """Veri klasöründe kimlik.db yok."""


class HubReadOnlyError(KimlikError):
    """Salt okunur açılmış hub'a yazma denendi."""


class HubNotEmptyError(KimlikError):
    """ice-aktar yalnız boş hub'a yapılır."""


class NotFoundError(KimlikError, LookupError):
    """İstenen kaynak/olay yok."""
