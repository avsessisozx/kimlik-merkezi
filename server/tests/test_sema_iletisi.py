"""Madde 13: eski/yeni şema için ayrı, eyleme dönük iletiler (kayıt dönmez)."""
import sqlite3

import pytest

from kimlikserver.service import QueryService, ServiceError


def _surum(root, n):
    c = sqlite3.connect(root / "kimlik.db")
    c.execute(f"PRAGMA user_version = {n}")
    c.commit()
    c.close()


def test_eski_sema_iletisi(world):
    _surum(world["root"], 4)
    s = QueryService(world["root"], world["a_key"])
    with pytest.raises(ServiceError) as e:
        s.ara("kahve")
    assert str(e.value) == ("Veritabanı eski biçimde. Önce Kimlik Merkezi uygulamasını bir kez "
                            "açın, sonra yeniden deneyin.")


def test_yeni_sema_iletisi(world):
    _surum(world["root"], 99)
    s = QueryService(world["root"], world["a_key"])
    with pytest.raises(ServiceError) as e:
        s.ara("kahve")
    assert str(e.value) == ("Bu bağlantı eski sürümle çalışıyor. Yapay zekâ uygulamasını "
                            "(ör. Claude Desktop) tamamen kapatıp yeniden başlatın.")
