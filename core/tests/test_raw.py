import hashlib
import os
import stat

from kimlikcore import sha256_file


def test_ham_arsiv_sha256_ve_degismezlik(hub, tmp_path):
    src = tmp_path / "ornek dosya.json"
    data = os.urandom(3 * 1024 * 1024 + 17)
    src.write_bytes(data)
    expect = hashlib.sha256(data).hexdigest()
    assert sha256_file(src) == expect
    sid = hub.add_source("test", "1", expect)
    raw = hub.store_raw(sid, src)
    assert raw.sha256 == expect and raw.size == len(data)
    p = hub.root / raw.path
    assert raw.path == f"arsiv/{expect}/ornek dosya.json"
    assert p.read_bytes() == data
    assert src.read_bytes() == data  # orijinale dokunulmadı
    assert not (p.stat().st_mode & stat.S_IWUSR)  # arşiv kopyası salt okunur
    assert hub.verify_archive() == []
    # aynı dosyayı yeniden saklamak yeni satır/kopya üretmez
    again = hub.store_raw(sid, src)
    assert again.raw_id == raw.raw_id and len(hub.raw_files()) == 1
    assert not [x for x in (hub.root / "arsiv").iterdir() if x.name.startswith(".gecici")]


def test_bozulma_yakalanir(hub, tmp_path):
    src = tmp_path / "a.bin"
    src.write_bytes(b"merhaba")
    sid = hub.add_source("test", "1", None)
    raw = hub.store_raw(sid, src)
    p = hub.root / raw.path
    os.chmod(p, 0o644)
    p.write_bytes(b"degisti!")
    assert any("hash uyuşmuyor" in x for x in hub.verify_archive())
    p.unlink()
    assert any("eksik" in x for x in hub.verify_archive())


def test_kaynak_hash_store_raw_ile_dolar(hub, tmp_path):
    src = tmp_path / "b.bin"
    src.write_bytes(b"xyz")
    sid = hub.add_source("test", "1", None)
    raw = hub.store_raw(sid, src)
    assert hub.sources()[0].file_sha256 == raw.sha256


def test_tehlikeli_dosya_adi(hub, tmp_path):
    src = tmp_path / "..hos"
    src.write_bytes(b"1")
    sid = hub.add_source("test", "1", None)
    raw = hub.store_raw(sid, src)
    assert (hub.root / raw.path).resolve().is_relative_to((hub.root / "arsiv").resolve())
