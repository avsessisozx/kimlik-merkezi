"""Genel SQL erişimi: Hub.transaction() / Hub.query() (server katmanı özel üyeler yerine bunu kullanır)."""
import sqlite3
import threading

import pytest

from kimlikcore import Hub, HubReadOnlyError

INS = "INSERT INTO devices(device_id, name, platform, created) VALUES (?, ?, 'android', '2026-01-01T00:00:00Z')"


def test_transaction_kesinlesir(hub):
    with hub.transaction() as c:
        c.execute(INS, ("d1", "Telefon"))
        c.execute(INS, ("d2", "Tablet"))
    assert hub.query("SELECT device_id FROM devices ORDER BY 1") == [("d1",), ("d2",)]
    assert not hub._conn.in_transaction


def test_transaction_istisnada_geri_alinir(hub):
    with pytest.raises(RuntimeError):
        with hub.transaction() as c:
            c.execute(INS, ("d1", "Telefon"))
            raise RuntimeError("patladı")
    assert hub.query("SELECT count(*) FROM devices") == [(0,)]
    with pytest.raises(sqlite3.IntegrityError):
        with hub.transaction() as c:
            c.execute(INS, ("d1", "A"))
            c.execute(INS, ("d1", "B"))  # birincil anahtar çakışması
    assert hub.query("SELECT count(*) FROM devices") == [(0,)]
    with hub.transaction() as c:  # hata sonrası hub kullanılabilir
        c.execute(INS, ("d9", "Z"))
    assert hub.query_one("SELECT name FROM devices") == ("Z",)


def test_transaction_salt_okunurda_reddedilir(root):
    with Hub.open(root, write=True):
        pass
    with Hub.open(root, write=False) as r:
        with pytest.raises(HubReadOnlyError):
            with r.transaction():
                pass


def test_query_parametreli_ve_bos(hub):
    with hub.transaction() as c:
        c.execute(INS, ("d1", "Telefon"))
    assert hub.query("SELECT name FROM devices WHERE device_id = ?", ("d1",)) == [("Telefon",)]
    assert hub.query("SELECT name FROM devices WHERE device_id = :i", {"i": "yok"}) == []
    assert hub.query_one("SELECT name FROM devices WHERE device_id = ?", ("yok",)) is None


def test_query_yazamaz_ve_sonra_yazma_calisir(hub):
    for sql in (INS.replace("?", "'x'"), "DELETE FROM devices", "CREATE TABLE x (a)",
                "UPDATE sources SET kind = 'z'"):
        with pytest.raises(sqlite3.OperationalError):
            hub.query(sql)
    with pytest.raises((sqlite3.Warning, sqlite3.ProgrammingError, sqlite3.OperationalError)):
        hub.query("SELECT 1; DELETE FROM devices")  # çok ifade kabul edilmez
    with hub.transaction() as c:  # query_only kapalı geri döndü
        c.execute(INS, ("d1", "T"))
    assert hub.query("SELECT count(*) FROM devices") == [(1,)]


def test_query_acik_islemin_yazdigini_gorur(hub):
    with hub.transaction() as c:
        c.execute(INS, ("d1", "T"))
        assert hub.query("SELECT count(*) FROM devices") == [(1,)]  # aynı bağlantı, aynı iş parçacığı
        c.execute(INS, ("d2", "T2"))  # query sonrası yazma hâlâ açık
    assert hub.query("SELECT count(*) FROM devices") == [(2,)]


def test_query_salt_okunur_hubda(root):
    with Hub.open(root, write=True) as w:
        with w.transaction() as c:
            c.execute(INS, ("d1", "T"))
    with Hub.open(root, write=False) as r:
        assert r.query("SELECT device_id FROM devices") == [("d1",)]
        with pytest.raises(sqlite3.OperationalError):
            r.query("DELETE FROM devices")


def test_baska_is_parcacigi_islem_bitene_kadar_bekler(hub):
    seen = []
    started = threading.Event()

    def reader():
        started.wait()
        seen.append(hub.query("SELECT count(*) FROM devices"))

    t = threading.Thread(target=reader)
    t.start()
    with hub.transaction() as c:
        c.execute(INS, ("d1", "T"))
        started.set()
        t.join(0.3)
        assert t.is_alive()  # kilit tutuluyor
    t.join(5)
    assert seen == [[(1,)]]
