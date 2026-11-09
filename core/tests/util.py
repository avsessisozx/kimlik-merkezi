"""Test yardımcıları: sentetik kayıtlar (gerçek kişisel veri yok)."""
from kimlikcore import EventIn

SEHIRLER = ["İstanbul", "Ankara", "İzmir", "Şanlıurfa", "Çanakkale", "Eskişehir", "Diyarbakır",
            "Gümüşhane", "Muğla", "Kırşehir"]


def known_events(n=20, kind="sentetik.not"):
    """Her kayıtta benzersiz bir sözcük (bulgu_<i>) bulunur."""
    out = []
    for i in range(n):
        out.append(EventIn(
            event_key=f"bilinen-{i}", ts=f"2026-03-{1 + i % 28:02d}T10:{i:02d}:00Z", kind=kind,
            category="notlar", payload={"i": i, "sehir": SEHIRLER[i % len(SEHIRLER)]},
            text=f"Sentetik not {i}: bulgu{i:03d}zz {SEHIRLER[i % len(SEHIRLER)]} gezisi",
        ))
    return out
