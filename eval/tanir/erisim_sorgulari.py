"""C koşulu için ERİŞİLEBİLİRLİK analizi: LLM DEĞİL, betikli sorgular.

Her soru için (a) akıllı bir cevaplayıcının KONUYA göre deneyebileceği genel sözcüklerle ('tahmin') ve
(b) gerçek kanıt sözcüğünü bilen ('anahtar') sorgular. Amaç: MCP araçlarının (anahtar sözcüklü `ara`,
`zaman_cizelgesi`, `ornekle`) bu bilgiyi HİÇ döndürüp döndürmediğini görmek. Sorguları yazan benim;
gerçek bir LLM daha akıllı ya da daha kötü sorgular deneyebilir. Sonuç bir üst/alt sınır değil, kaba bir göstergedir.
(araç, argümanlar) biçimindedir.
"""
A = lambda q, k=None, l=None: ("ara", {"sorgu": q, **({"kategori": k} if k else {}), **({"limit": l} if l else {})})  # noqa: E731
Z = lambda k, l=200: ("zaman_cizelgesi", {"kategori": k, "limit": l})  # noqa: E731
O = lambda k, n=20, q=None: ("ornekle", {"kategori": k, "n": n, **({"sorgu": q} if q else {})})  # noqa: E731
PG = ("persona_getir", {})

TAHMIN = {
    "Q01": [PG], "Q02": [PG],
    "Q03": [A("proje"), A("github"), Z("kod", 100)],
    "Q04": [A("işletim sistemi"), A("linux"), A("windows"), A("bilgisayar")],
    "Q05": [PG, A("yaşıyor"), A("şehir"), A("istanbul"), A("ankara")],
    "Q06": [A("taşınma"), A("eski şehir"), A("taşındı"), A("memleket")],
    "Q07": [A("editör"), A("vscode"), A("vim"), Z("kod", 100)],
    "Q08": [A("seyahat"), A("uçak bileti"), A("tatil"), A("otel")],
    "Q09": [Z("kod", 200), A("python")],
    "Q10": [A("kahve"), A("demleme")],
    "Q11": [A("yemek"), A("sevmediği"), A("tarif"), A("malzeme")],
    "Q12": [A("beslenme"), A("diyet"), A("yemek")],
    "Q13": [A("işe"), A("ulaşım"), A("otobüs"), A("yol")],
    "Q14": [A("evcil"), A("köpek"), A("kedi")],
    "Q15": [O("muzik", 20), Z("muzik", 200)],
    "Q16": [Z("kod", 200)],
    "Q17": [A("oyun"), A("hobi"), A("zeka")],
    "Q18": [A("kitap"), A("roman"), A("okuma")],
    "Q19": [A("spor"), A("yarış"), A("koşu")],
    "Q20": [A("eğitim"), A("üniversite"), A("ders"), A("okul")],
    "Q21": [A("seyahat"), A("yurt dışı"), A("vize"), A("gezi")],
    "Q22": [A("donanım"), A("fare"), A("monitör"), A("klavye")],
    "Q23": [A("arkadaş"), A("hafta sonu"), A("buluşma"), A("oyun")],
}
ANAHTAR = {
    "Q03": [A("mahalle-takvimi")], "Q04": [A("fedora")], "Q05": [A("kızılay")], "Q06": [A("alsancak")],
    "Q07": [A("nvim")], "Q08": [A("lizbon")], "Q09": [A("python"), Z("kod", 200)], "Q10": [A("v60")], "Q11": [A("koriander")],
    "Q12": [A("vejetaryen")], "Q13": [A("bisiklet")], "Q14": [A("tarçın")], "Q15": [A("mavi dalga")],
    "Q16": [Z("kod", 200)], "Q17": [A("satranç")], "Q18": [A("bilimkurgu")], "Q19": [A("yarı maraton"), A("sertifika")],
    "Q20": [A("yüksek lisans")], "Q21": [A("tiflis")], "Q22": [A("klavye")], "Q23": [A("masa oyunu")],
}
