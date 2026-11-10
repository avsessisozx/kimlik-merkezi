"""Uydurma kişi için sahte dışa aktarma dosyaları üreticisi (tohumlu, deterministik).

Çıktı, gerçek içe aktarıcıların beklediği biçimdedir (importers/fixtures ile aynı şekiller):
  takeout/Takeout/...   Google Takeout (arama, YouTube, Chrome, konum, Gmail mbox)
  reddit/*.csv          Reddit veri isteği
  github/*_000001.json  GitHub dışa aktarma (commit türü GERÇEK dışa aktarmada YOKTUR: bkz. README)
  spotify/Spotify Account Data/*.json
  chatgpt/conversations.json, claude/conversations.json

Kişi gerçekleri kayıtlarda 'şunu seviyorum' diye yazılmaz; dolaylı izlerle (arama, izleme, dinleme,
commit saatleri...) taşınır. Aynı tohum aynı baytları üretir. Büyük veri depoya konmaz: bu betik
çalıştırıldığında `cikti/tanir/ham/` altına yazar.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus

from gercekler import KISI, SEED, SIMDI

UTC = timezone.utc


def sayi(s: str, basamak: int = 22) -> str:
    """Süreçler arası kararlı (PYTHONHASHSEED'den bağımsız) sayısal özet."""
    return str(int(hashlib.sha256(s.encode("utf-8")).hexdigest(), 16))[:basamak].zfill(basamak)


def D(y, m, d, h=12, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=UTC)


def iso(t: datetime, ms: bool = False) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%S") + (".000Z" if ms else "Z")


class Uretec:
    def __init__(self, seed: int = SEED):
        self.rng = random.Random(seed)

    def an(self, bas: datetime, bit: datetime, saat=(7, 23)) -> datetime:
        """[bas, bit] içinde rastgele bir an; yerel saat (UTC+3) aralığı `saat`."""
        gun = (bit - bas).days
        t = bas + timedelta(days=self.rng.randint(0, max(gun, 0)))
        yerel = self.rng.randint(*saat)
        t = t.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
            hours=yerel - 3, minutes=self.rng.randint(0, 59), seconds=self.rng.randint(0, 59))
        return t

    def sec(self, xs):
        return self.rng.choice(xs)


# ---------------------------------------------------------------- kanıt tabloları
# (metin, başlangıç, bitiş, tekrar). Hepsi uydurma; gerçekleri DOLAYLI taşır.
A22, A24, A26 = D(2022, 1, 5), D(2024, 1, 5), D(2026, 11, 8)
S_IZMIR = (D(2022, 1, 5), D(2023, 11, 20))
S_ANKARA = (D(2024, 1, 15), D(2026, 11, 8))

ARAMA_KANIT = [
    # İzmir dönemi (2022-2023), taşınma (Aralık 2023), Ankara dönemi (2024+)
    *[(q, *S_IZMIR, n) for q, n in [
        ("alsancak kordon akşam yürüyüş", 3), ("izmir vapur saatleri karşıyaka", 4),
        ("bornova kiralık daire fiyatları", 2), ("konak izmir en iyi kahvaltı", 2),
        ("izmir hava durumu hafta sonu", 6), ("urla bağ evi günübirlik", 1)]],
    ("izmir ankara nakliyat fiyatları", D(2023, 11, 20), D(2023, 12, 10), 3),
    ("ankara kiralık daire çankaya", D(2023, 11, 25), D(2023, 12, 20), 4),
    ("taşınma kontrol listesi", D(2023, 12, 1), D(2023, 12, 20), 2),
    *[(q, *S_ANKARA, n) for q, n in [
        ("kızılay metro çalışma saatleri", 5), ("ankara hava durumu yarın", 9),
        ("çankaya belediyesi çöp toplama günleri", 2), ("eymir gölü hafta sonu yürüyüş", 3),
        ("ankara kış lastiği değişim fiyat", 2), ("kızılay sessiz çalışılabilecek kafe", 3),
        ("ankara kuzu kulağı pazarı", 1)]],
    # Meslek / dil / editör / işletim sistemi
    *[(q, D(2022, 2, 1), D(2023, 11, 1), n) for q, n in [
        ("vscode python debugger ayarı", 5), ("fastapi bağımlılık enjeksiyonu örnek", 4),
        ("poetry mi pip-tools mu", 2), ("vscode launch json python modül", 3),
        ("python dataclass slots performans", 3)]],
    *[(q, D(2024, 1, 15), D(2025, 6, 1), n) for q, n in [
        ("go goroutine sızıntısı nasıl bulunur", 3), ("go modules replace yönergesi", 2),
        ("python asyncio gather hata yönetimi", 4), ("sqlalchemy 2.0 oturum yönetimi", 3)]],
    ("vscode vim eklentisi neden yavaş", D(2024, 11, 1), D(2025, 1, 20), 2),
    *[(q, D(2025, 1, 20), D(2026, 10, 30), n) for q, n in [
        ("lazy.nvim eklenti yönetimi", 5), ("neovim lsp python pyright ayarı", 5),
        ("telescope nvim dosya arama kısayolu", 3), ("nvim treesitter highlight bozuldu", 3),
        ("neovim yerleşik terminal kısayolları", 2)]],
    *[(q, D(2024, 1, 20), D(2026, 10, 30), n) for q, n in [
        ("fedora dnf kilit hatası", 3), ("fedora 40 nvidia sürücü kurulumu", 3),
        ("flatpak steam fedora", 2), ("fedora 42 güncelleme sonrası wifi kopuyor", 2),
        ("dnf5 eklenti uyumluluğu", 2)]],
    # Kahve
    *[(q, D(2024, 2, 1), D(2026, 10, 1), n) for q, n in [
        ("v60 öğütme inceliği", 5), ("hario v60 02 seramik fiyat", 2), ("filtre kahve 1:16 oran", 4),
        ("el değirmeni burr seçimi", 3), ("v60 su sıcaklığı kaç derece", 3),
        ("hafif kavrum çekirdek ankara", 3)]],
    # Koriander
    *[(q, D(2022, 3, 1), D(2026, 10, 1), n) for q, n in [
        ("yemekte koriander yerine ne konur", 3), ("koriandersiz salsa tarifi", 2),
        ("koriander sabun tadı neden", 2), ("maydanoz ile koriander nasıl ayırt edilir", 2)]],
    # Vejetaryen
    *[(q, D(2022, 3, 1), D(2026, 10, 1), n) for q, n in [
        ("vejetaryen protein kaynakları", 4), ("mercimek köftesi tarifi", 3),
        ("et yemeyenler için b12 takviyesi", 3), ("vejetaryen restoran ankara kızılay", 3),
        ("nohutlu ıspanak yemeği", 2)]],
    # Bisiklet / işe gidiş
    *[(q, D(2024, 2, 1), D(2026, 10, 1), n) for q, n in [
        ("bisikletle işe gidenler için yağmurluk", 3), ("bisiklet zinciri yağlama sıklığı", 3),
        ("bisiklet kask ışık kış", 2), ("ofis için bisiklet park yeri talebi", 1),
        ("çankaya bisiklet yolu haritası", 3)]],
    # Kedi
    *[(q, D(2022, 6, 1), D(2026, 10, 1), n) for q, n in [
        ("britanya kısa tüy kedi tüy dökümü", 4), ("kedi aşı takvimi", 3),
        ("kedi tırmalama tahtası seçimi", 2), ("kedi mama geçişi nasıl yapılır", 2),
        ("kedi veteriner ankara", 2)]],
    # Satranç
    *[(q, D(2023, 1, 1), D(2026, 10, 1), n) for q, n in [
        ("sicilya savunması başlangıç hamleleri", 4), ("satranç taktik bulmaca günlük", 6),
        ("alapin varyantı teori", 2), ("satranç hızlı oyun puan yükseltme", 3)]],
    # Bilimkurgu
    *[(q, D(2024, 1, 1), D(2026, 10, 1), n) for q, n in [
        ("bilimkurgu roman önerileri", 4), ("tuz çağı özet ve yorumlar", 2),
        ("distopya kitap listesi", 2), ("bilimkurgu ödülleri uzun liste", 1)]],
    # Yarı maraton (2026)
    ("yarı maraton antrenman programı 12 hafta", D(2026, 5, 20), D(2026, 6, 5), 3),
    ("koşu ayakkabısı tabanlık seçimi", D(2026, 6, 1), D(2026, 7, 15), 2),
    ("sonbahar yarı maratonu kayıt", D(2026, 6, 1), D(2026, 6, 20), 2),
    ("yarı maraton yarış günü beslenme", D(2026, 9, 25), D(2026, 10, 10), 3),
    ("sonbahar yarı maratonu sonuç sertifika", D(2026, 10, 18), D(2026, 10, 28), 2),
    # Yüksek lisans (2025+)
    *[(q, D(2025, 1, 5), D(2026, 10, 1), n) for q, n in [
        ("yüksek lisans başvuru tarihleri veri bilimi", 2), ("tez danışmanı seçimi nasıl yapılır", 2),
        ("bayes istatistiği ders notu", 4), ("yüksek lisans ders programı güz", 2),
        ("çalışırken yüksek lisans zaman yönetimi", 3), ("pandas groupby transform", 4)]],
    # Lizbon (önce Kasım, sonra Aralık)
    ("lizbon 4 gün gezi planı", D(2026, 8, 18), D(2026, 8, 25), 2),
    ("lizbon uçak bileti 14 kasım", D(2026, 8, 18), D(2026, 8, 22), 3),
    ("lizbon alfama otel", D(2026, 8, 20), D(2026, 8, 25), 3),
    ("uçak bileti değiştirme ücreti", D(2026, 10, 3), D(2026, 10, 6), 2),
    ("lizbon 19 aralık uçak", D(2026, 10, 4), D(2026, 10, 8), 3),
    ("lizbon aralık hava durumu", D(2026, 10, 8), D(2026, 11, 5), 3),
    ("lizbon sintra günübirlik", D(2026, 10, 10), D(2026, 11, 5), 2),
    ("lizbon pastel de nata nerede yenir", D(2026, 10, 10), D(2026, 11, 5), 1),
    # Tiflis (2025 Mayıs)
    ("tiflis eski şehir gezi rotası", D(2025, 4, 10), D(2025, 4, 25), 3),
    ("gürcistan'a kimlikle giriş", D(2025, 4, 8), D(2025, 4, 12), 2),
    ("hacapuri nerede yenir tiflis", D(2025, 4, 20), D(2025, 5, 8), 2),
    ("batum tiflis tren saatleri", D(2025, 4, 20), D(2025, 5, 2), 2),
    # Mekanik klavye
    *[(q, D(2023, 6, 1), D(2026, 9, 1), n) for q, n in [
        ("tactile switch yağlama", 3), ("mekanik klavye stabilizatör sesi", 3),
        ("pbt keycap seti", 3), ("hot-swap klavye kit", 2)]],
    # Masa oyunu
    *[(q, D(2023, 1, 1), D(2026, 10, 1), n) for q, n in [
        ("catan genişletme önerisi", 2), ("4 kişi masa oyunu önerileri", 3),
        ("azul kuralları özet", 2), ("kooperatif masa oyunu", 3), ("masa oyunu kutu kılıfı", 1)]],
    # ALDATICI İZLER (tuzak soruların gerçek cevabı yok)
    ("30 yaş sonrası yüksek lisans mantıklı mı", D(2025, 1, 12), D(2025, 1, 12), 1),
    ("pixel mi iphone mu 2026", D(2026, 6, 2), D(2026, 6, 4), 2),
    ("aidatsız kredi kartı karşılaştırma", D(2025, 11, 3), D(2025, 11, 3), 1),
    ("lizbon iki kişilik oda alfama", D(2026, 8, 21), D(2026, 8, 21), 1),
]

ARAMA_GURULTU = [
    "hava durumu", "döviz kuru", "nöbetçi eczane", "kargo takip", "film önerileri", "ingilizce türkçe sözlük",
    "resmi tatiller 2025", "saat farkı hesaplama", "ütü nasıl temizlenir", "excel dikey ara",
    "pdf birleştir", "internet hız testi", "yemek tarifi pratik akşam", "lastik basıncı kaç olmalı",
    "pasaport randevusu", "elektrik faturası sorgulama", "mutfak dolabı düzenleme", "tatil için ucuz uçak",
    "güncel haberler", "bilet fiyatları", "anlamı nedir", "sinema seansları", "kitap indirimi", "ayakkabı numara tablosu",
    "fotoğraf boyutlandırma", "bulaşık makinesi tuzu", "saç kesimi randevu", "diş macunu içerik", "tren saatleri",
    "yılbaşı hediye fikirleri", "telefon şarj olmuyor", "wifi şifresi nasıl değişir", "kira artış oranı",
]

VIDEO_KANIT = [  # (başlık, kanal, bas, bit, adet)
    ("V60 ile Mükemmel Filtre Kahve: 5 Hata", "Demleme Atölyesi", D(2024, 2, 1), D(2026, 10, 1), 9),
    ("El Değirmeni Ayarı ve Öğütme Boyutları", "Demleme Atölyesi", D(2024, 2, 1), D(2026, 10, 1), 5),
    ("Etsiz Haftalık Yemek Hazırlığı", "Etsiz Mutfak", D(2022, 3, 1), D(2026, 10, 1), 10),
    ("Mercimekten Protein Dolu 5 Tarif", "Etsiz Mutfak", D(2022, 3, 1), D(2026, 10, 1), 6),
    ("Sicilya Savunması: Alapin ile Teoriyi Atla", "Gambit Sokağı", D(2023, 1, 1), D(2026, 10, 1), 10),
    ("Hızlı Oyunda Ortaoyun Planı Kurmak", "Gambit Sokağı", D(2023, 1, 1), D(2026, 10, 1), 7),
    ("Neovim Sıfırdan: lazy.nvim ile Yapılandırma", "Nvim Notları", D(2025, 1, 20), D(2026, 10, 1), 8),
    ("LSP ve Treesitter Nasıl Çalışır", "Nvim Notları", D(2025, 1, 20), D(2026, 10, 1), 5),
    ("Go ile Eşzamanlılık Kalıpları", "Kod Mutfağı", D(2024, 2, 1), D(2025, 9, 1), 5),
    ("FastAPI ile Üretime Hazır Servis", "Kod Mutfağı", D(2022, 2, 1), D(2024, 6, 1), 6),
    ("12 Haftada Yarı Maraton: Plan ve Hatalar", "Koşu Günlüğü", D(2026, 5, 20), D(2026, 9, 1), 7),
    ("Uzun Koşu Beslenmesi", "Koşu Günlüğü", D(2026, 5, 20), D(2026, 10, 10), 4),
    ("Bayes Teoremi Sezgisel Anlatım", "Sentez Üniversitesi", D(2025, 2, 1), D(2026, 10, 1), 8),
    ("Doğrusal Modeller: Ders 7", "Sentez Üniversitesi", D(2025, 2, 1), D(2026, 10, 1), 6),
    ("Tiflis'te 4 Gün: Gezi Rehberi", "Yol Defteri", D(2025, 4, 5), D(2025, 4, 25), 4),
    ("Lizbon'da Yürüyerek Gezilecek Yerler", "Yol Defteri", D(2026, 8, 18), D(2026, 11, 5), 4),
    ("Mekanik Klavye Yağlama Rehberi", "Klavye Atölyesi", D(2023, 6, 1), D(2026, 9, 1), 6),
    ("Stabilizatör Ses Sorunu Çözümü", "Klavye Atölyesi", D(2023, 6, 1), D(2026, 9, 1), 3),
    ("Salı Gecesi Oyunu: Kooperatif Seçkisi", "Masa Başı Oyunlar", D(2023, 1, 1), D(2026, 10, 1), 6),
    ("Britanya Kısa Tüy Bakımı", "Kedi Hali", D(2022, 6, 1), D(2026, 10, 1), 5),
    ("Bisikletle Şehir İçi Güvenli Sürüş", "Pedal Notları", D(2024, 2, 1), D(2026, 10, 1), 6),
    ("Hafif Kavrum mı Orta Kavrum mu", "Demleme Atölyesi", D(2024, 2, 1), D(2026, 10, 1), 3),
    # aldatıcı iz: tek bir derbi özeti
    ("Derbi Maç Özeti: Büyük Gün", "Spor Penceresi", D(2025, 5, 18), D(2025, 5, 18), 1),
]
VIDEO_GURULTU = [
    ("Günün Özeti", "Haber Penceresi"), ("10 Dakikada Osmanlı", "Tarih Kısa"), ("Mutfak Hileleri", "Pratik Evim"),
    ("Uzay Belgeseli: Uzak Yıldızlar", "Evren Sinema"), ("Komik Kedi Derlemesi", "Gülme Odası"),
    ("Ev Yapımı Pizza", "Pratik Evim"), ("Ekonomi Haftalık", "Haber Penceresi"), ("Gece Müziği Karışımı", "Lofi Sokak"),
    ("Yeni Çıkan Oyunlar", "Oyun Köşesi"), ("Fotoğraf Çekim İpuçları", "Kadraj"), ("Dil Öğrenme Yöntemleri", "Dil Atölyesi"),
]
KANALLAR = ["Demleme Atölyesi", "Etsiz Mutfak", "Gambit Sokağı", "Nvim Notları", "Kod Mutfağı", "Koşu Günlüğü",
            "Sentez Üniversitesi", "Yol Defteri", "Klavye Atölyesi", "Masa Başı Oyunlar", "Pedal Notları", "Haber Penceresi"]

VIDEO_ARAMA = [("v60 kahve oranları", D(2024, 3, 1), 2), ("lazy nvim ayarları", D(2025, 2, 1), 2), ("sicilya alapin", D(2024, 1, 1), 2),
               ("lizbon gezi", D(2026, 8, 19), 2), ("yarı maraton antrenman", D(2026, 5, 22), 2), ("etsiz tarif", D(2023, 5, 1), 3)]

CHROME = [  # (başlık, url, bas, bit, adet)
    ("V60 ile Filtre Kahve Demleme Rehberi - Kahve Okulu", "https://kahveokulu.example.test/v60-rehberi", D(2024, 2, 1), D(2026, 9, 1), 3),
    ("Hario V60 02 Seramik Dripper | Kahve Mağazası", "https://kahvemagaza.example.test/v60-02", D(2024, 2, 5), D(2024, 2, 20), 2),
    ("lazy.nvim - Eklenti Yöneticisi Belgeleri", "https://nvim-docs.example.test/lazy", D(2025, 1, 20), D(2026, 9, 1), 4),
    ("Fedora Belgeleri: DNF ile Paket Yönetimi", "https://fedora-docs.example.test/dnf", D(2024, 1, 20), D(2026, 9, 1), 3),
    ("Python 3.13 Yenilikleri - Resmi Belgeler", "https://py-docs.example.test/3.13", D(2024, 10, 1), D(2026, 5, 1), 3),
    ("Go Turu: Kanallar", "https://go-docs.example.test/tour-channels", D(2024, 2, 1), D(2025, 6, 1), 2),
    ("Sonbahar Yarı Maratonu 2026 - Kayıt Onayı", "https://yaris.example.test/sonbahar-2026/kayit", D(2026, 6, 8), D(2026, 6, 10), 1),
    ("Sonbahar Yarı Maratonu 2026 - Sonuçlar", "https://yaris.example.test/sonbahar-2026/sonuclar", D(2026, 10, 19), D(2026, 10, 20), 2),
    ("İstatistiksel Öğrenme Ders Notları - Hafta 6", "https://ders.example.test/istatistik-ogrenme/h6", D(2025, 3, 1), D(2026, 9, 1), 4),
    ("Veri Bilimi Yüksek Lisans Programı - Müfredat", "https://universite.example.test/vb-yl/mufredat", D(2025, 1, 5), D(2025, 2, 1), 2),
    ("Tiflis Gezi Rehberi: Eski Şehir", "https://gezirehberi.example.test/tiflis/eski-sehir", D(2025, 4, 10), D(2025, 4, 28), 3),
    ("Lizbon Alfama Mahallesi Otelleri", "https://otelbul.example.test/lizbon/alfama", D(2026, 8, 20), D(2026, 8, 25), 3),
    ("Mekanik Klavye Yağlama: Adım Adım", "https://klavyekutusu.example.test/yaglama", D(2023, 6, 1), D(2026, 8, 1), 3),
    ("Salı Oyun Gecesi İçin 4 Kişilik Masa Oyunları", "https://masaoyunu.example.test/4-kisilik", D(2023, 1, 1), D(2026, 8, 1), 3),
    ("Etsiz Beslenmede Protein ve B12 Rehberi", "https://saglikli.example.test/etsiz-beslenme", D(2022, 3, 1), D(2026, 8, 1), 3),
    ("Kızılay Çevresinde Bisiklet Yolu Haritası", "https://ulasim.example.test/bisiklet-haritasi", D(2024, 2, 1), D(2026, 8, 1), 2),
    ("Alsancak Kordon Yürüyüş Rotaları", "https://izmirrehberi.example.test/kordon", D(2022, 2, 1), D(2023, 10, 1), 2),
]
CHROME_GURULTU = [("Haber Sitesi - Ana Sayfa", "https://haber.example.test/"), ("Hava Durumu", "https://hava.example.test/"),
                  ("Kargo Takip", "https://kargo.example.test/takip"), ("Sözlük", "https://sozluk.example.test/"),
                  ("Alışveriş Sepeti", "https://alisveris.example.test/sepet"), ("Ekonomi Haberleri", "https://haber.example.test/ekonomi")]


# ---------------------------------------------------------------- Reddit / GitHub / Spotify / sohbet
REDDIT_YORUM = [  # (subreddit, bas, bit, metin) -- gerçekleri dolaylı taşır
    ("izmir", D(2022, 3, 1), D(2023, 10, 30), "Alsancak'ta akşam yürüyüşü için Kordon yerine arka sokakları tercih ederim, daha sakin."),
    ("izmir", D(2022, 5, 1), D(2023, 10, 30), "Karşıyaka'ya vapurla geçmek hâlâ en iyi ulaşım, trafikte kalan pişman olur."),
    ("izmir", D(2023, 6, 1), D(2023, 11, 10), "Bornova'da kira fiyatları da uçtu, bu yaz ev bakarken şaşırdım."),
    ("ankara", D(2024, 2, 1), D(2024, 6, 1), "Kızılay'a metroyla inmek rahat ama bisiklet yolu olmayan caddede sabah işe giderken kamyonlarla yarışmak ayrı bir maharet."),
    ("ankara", D(2024, 6, 1), D(2025, 6, 1), "Eymir'de hafta sonu sabahı çok güzel ama öğleden sonra kalabalık; erkenden gidin."),
    ("ankara", D(2025, 6, 1), D(2026, 9, 1), "Kış gelmeden lastik değişimini yaptırın, geçen sene sıraya girmek için iki saat beklemiştim."),
    ("neovim", D(2025, 2, 1), D(2025, 9, 1), "treesitter'ı güncelleyince highlight bozuldu, lazy lock dosyasını geri alınca düzeldi."),
    ("neovim", D(2025, 9, 1), D(2026, 8, 1), "pyright yerine basedpyright denedim, büyük projede hissedilir şekilde hızlı."),
    ("fedora", D(2025, 3, 1), D(2025, 8, 1), "dnf5'e geçince bazı eklentiler hâlâ eski sürümü bekliyor mu, bende kilit hatası verdi."),
    ("fedora", D(2024, 8, 1), D(2024, 12, 1), "Nvidia sürücüsünü rpmfusion'dan kurunca açılışta siyah ekran kalmadı, güncellemeden sonra bir daha bakın."),
    ("yemek", D(2023, 2, 1), D(2023, 10, 1), "Meksika restoranında siparişe 'koriandersiz' notu yazmayı öğrendim, yoksa tabak zaten gidiyor."),
    ("yemek", D(2024, 3, 1), D(2025, 6, 1), "Mercimek köftesinde nar ekşisini sona bırakın, sosun parlaması değişiyor."),
    ("kedi", D(2023, 2, 1), D(2026, 5, 1), "Benimkinin adı Tarçın, bu sabah yine kahvemi devirdi ve suçu yok sayarak mamasını bekledi."),
    ("kedi", D(2024, 4, 1), D(2025, 4, 1), "Britanya kısa tüylerde tüy dökümü mevsim geçişinde artıyor, tarak haftada iki yeter."),
    ("satranc", D(2023, 3, 1), D(2024, 9, 1), "Sicilya'ya karşı Alapin oynamaya başlayınca teorik yük azaldı, hızlı oyunda iş görüyor."),
    ("satranc", D(2024, 9, 1), D(2026, 6, 1), "Günlük bulmaca dışında bir de oyun sonrası analiz alışkanlığı edinince puanım oynamaya başladı."),
    ("bilimkurgu", D(2025, 3, 1), D(2025, 9, 1), "Tuz Çağı'nın ikinci yarısı ilkinden güçlü, dünya kurgusu sonunda yerine oturuyor."),
    ("bilimkurgu", D(2024, 2, 1), D(2025, 1, 1), "Distopya severlerin ortak derdi: her kitabın sonu aynı karanlığa varıyor, bir tane umutlusunu önerin."),
    ("mekanikklavye", D(2023, 8, 1), D(2025, 2, 1), "Lineer switch'leri yağlayınca tuş sesi yumuşadı ama stabilizatörü ihmal etmeyin, asıl takırtı oradan."),
    ("mekanikklavye", D(2025, 2, 1), D(2026, 4, 1), "Hot-swap kit alıp switch denemek, hazır klavyeden hem ucuz hem öğretici."),
    ("masaoyunlari", D(2023, 4, 1), D(2026, 6, 1), "Bizim grup salı akşamları toplanıyor, Azul'dan sıkıldık, kooperatif bir şey arıyoruz."),
    ("masaoyunlari", D(2024, 1, 1), D(2026, 9, 1), "Dört kişiyle Catan'ın genişletmesi uzun sürüyor, haftaiçi akşamına sığmıyor."),
    ("kosu", D(2026, 8, 1), D(2026, 9, 25), "12. hafta uzun koşu 18 km oldu, ayaklarda su toplamaya karşı çorap değiştirmek işe yaradı."),
    ("kosu", D(2026, 10, 18), D(2026, 10, 25), "Yarış günü ilk 10 km planlıydı, son 3 km bacaklar dağıldı ama bitirdim, sertifikayı da aldım."),
    ("veribilimi", D(2025, 3, 1), D(2026, 9, 1), "Dönem projesinde Bayes yaklaşımını seçtim, hocanın tek şartı sonuçları sade anlatmaktı."),
    ("programlama", D(2022, 4, 1), D(2023, 10, 1), "Ekip içi kod gözden geçirmede vscode ayarlarını depoya koymak onboarding'i kısalttı."),
    ("programlama", D(2024, 4, 1), D(2025, 11, 1), "Go'ya geçince kanalları öğrenmek zaman aldı ama Python tarafında asyncio karmaşasından sonra rahatlatıcı geldi."),
    ("seyahat", D(2025, 5, 5), D(2025, 6, 10), "Tiflis'te hacapuriyi mutlaka Acara usulü deneyin, eski şehirde akşam yürüyüşü de bedava eğlence."),
    ("seyahat", D(2026, 10, 20), D(2026, 11, 8), "Aralık sonu Lizbon'u düşünüyorum; pastel de nata dışında yürüyerek gezilecek bir şey önerin."),
]
REDDIT_GURULTU = ["Katılıyorum.", "Kaynak var mı?", "Bu konuda iki farklı görüş var, ikisi de savunulabilir.", "Teşekkürler, işime yaradı.",
                  "Bence abartılıyor.", "Aynı sorunu ben de yaşadım, çözüm bulamadım.", "İlginç bir bakış açısı.", "Sonucu merak ettim, güncelleme gelir mi?"]
REDDIT_ABONE = ["izmir", "ankara", "neovim", "fedora", "yemek", "kedi", "satranc", "bilimkurgu", "mekanikklavye", "masaoyunlari",
                "kosu", "veribilimi", "programlama", "seyahat", "turkce"]
REDDIT_GONDERI = [
    ("ankara", D(2024, 3, 10), "Kızılay çevresinde sessiz çalışılabilecek kafe önerisi", "Dizüstüyle çalışabileceğim, priz ve wifi sorunu olmayan yerler arıyorum."),
    ("neovim", D(2025, 4, 6), "Python projesinde LSP başlangıcı yavaş", "pyright başlangıcı büyük projede 6 sn sürüyor, benzer yaşayan var mı?"),
    ("kosu", D(2026, 6, 14), "Yarı maraton için ilk kez 12 haftalık plan: öneri", "Haftada 4 gün koşabiliyorum, uzun koşu pazar. Plan mantıklı mı?"),
    ("izmir", D(2023, 11, 14), "Ankara'ya taşınanlar: ilk ay tavsiye", "Ev eşyalarını nakliyeci ile götürmek mi yeni almak mı?"),
    ("kitap", D(2025, 8, 2), "Bilimkurguda dünya kurgusu güçlü kitaplar", "Tuz Çağı sonrası benzer yoğunlukta ne okunur?"),
]


def reddit_yaz(u: Uretec, kok: Path) -> dict:
    kok.mkdir(parents=True, exist_ok=True)
    rng = u.rng
    yorum, n = [], 0
    for sr, b, e, metin in REDDIT_YORUM:
        for _ in range(rng.randint(1, 2)):
            n += 1
            yorum.append((u.an(b, e), sr, metin))
    for i in range(18):
        sr = u.sec(REDDIT_ABONE)
        yorum.append((u.an(D(2022, 3, 1), D(2026, 10, 1)), sr, u.sec(REDDIT_GURULTU)))
    yorum.sort()

    def tarih(t):
        return t.strftime("%Y-%m-%d %H:%M:%S UTC")

    with open(kok / "comments.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "permalink", "date", "ip", "subreddit", "gildings", "link", "parent", "body", "media"])
        for i, (t, sr, m) in enumerate(yorum):
            w.writerow([f"c{i:04d}", f"/r/{sr}/comments/p{i:04d}/_/c{i:04d}/", tarih(t), "0.0.0.0", sr, 0,
                        f"/r/{sr}/comments/p{i:04d}/", "", m, ""])
    with open(kok / "posts.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "permalink", "date", "ip", "subreddit", "gildings", "title", "url", "body"])
        for i, (sr, t, baslik, govde) in enumerate(REDDIT_GONDERI):
            w.writerow([f"p{i:04d}", f"/r/{sr}/comments/p{i:04d}/", tarih(t), "0.0.0.0", sr, 0, baslik, "", govde])
    with open(kok / "subscribed_subreddits.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["subreddit"])
        for sr in REDDIT_ABONE:
            w.writerow([sr])
    # Özel mesajlar (kategori 'mesaj', HASSAS): kardeşin adı yalnız burada geçer.
    with open(kok / "messages.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "permalink", "thread_id", "date", "ip", "from", "to", "subject", "body"])
        w.writerow(["m1", "/message/messages/m1", "t1", tarih(D(2025, 9, 3, 15)), "0.0.0.0", KISI["reddit"], "kitap_takasi",
                    "Tuz Çağı ikinci cilt", "Merhaba, ikinci cilt hâlâ duruyor mu? Kardeşim Deniz de aynı seriyi arıyordu, ayırırsan ikimiz de alırız."])
        w.writerow(["m2", "/message/messages/m2", "t1", tarih(D(2025, 9, 3, 18)), "0.0.0.0", "kitap_takasi", KISI["reddit"],
                    "Re: Tuz Çağı ikinci cilt", "Duruyor, cumartesi elden verebilirim."])
    return {"yorum": len(yorum), "gonderi": len(REDDIT_GONDERI)}


COMMIT_MESAJ = {
    "mahalle-takvimi": [
        "etkinlik listesini sayfalama ile döndür", "semt filtresi için sorgu parametresi ekle", "takvim dışa aktarma (ics) düzeltmesi",
        "kaynak toplayıcıda zaman aşımı yönetimi", "pytest: etkinlik tekrarlama kuralı testleri", "fastapi: bağımlılıkları sadeleştir",
        "readme: kurulum adımlarını güncelle", "veritabanı göçü: semt tablosu", "hata: gece yarısı etkinlikleri iki kez listeleniyor",
        "toplayıcı: yeni belediye kaynağı ekle", "tip ipuçlarını tamamla", "Tarçın klavyenin üstüne yürüdü, yarım kalan commit"],
    "dotfiles": [
        "nvim: lsp yapılandırmasını ayır", "nvim: lazy.nvim eklenti kilidini güncelle", "nvim: telescope kısayolları", "nvim: treesitter dil listesi",
        "fedora: dnf yapılandırması", "kitty: renk şeması"],
    "go-sayac": ["kanal tabanlı sayaç", "goroutine sızıntısı düzeltildi", "benchmark ekle", "go.mod güncelle"],
    "vscode-ayarlar": ["vscode launch.json ekle", "python debugger ayarı", "çalışma alanı önerileri", "ayarlar.json sadeleştirme"],
}


def github_yaz(u: Uretec, kok: Path) -> dict:
    kok.mkdir(parents=True, exist_ok=True)
    rng = u.rng
    L = KISI["github"]
    base = f"https://github.com/{L}"
    repos = [
        ("mahalle-takvimi", "Semt etkinliklerini toplayan açık kaynak takvim uygulaması", "Python", D(2024, 3, 3)),
        ("dotfiles", "Kişisel yapılandırma dosyaları (nvim, kitty)", "Lua", D(2022, 2, 10)),
        ("go-sayac", "Eşzamanlılık denemeleri", "Go", D(2024, 5, 1)),
        ("vscode-ayarlar", "Eski editör ayarları", "JSON", D(2022, 2, 1)),
    ]
    json_yaz(kok / "repositories_000001.json", [
        {"type": "repository", "url": f"{base}/{ad}", "name": ad, "description": ac, "private": False, "language": dil,
         "created_at": iso(t), "owner": base} for ad, ac, dil, t in repos])
    yildiz = [("nvim-lazy-ornek", "Eklenti yöneticisi örneği"), ("treesitter-ornek", "Sözdizimi ağacı"), ("satranc-motoru-ornek", "Küçük bir satranç motoru"),
              ("hot-swap-klavye-ornek", "Klavye yazılım deposu"), ("fastapi-sablon-ornek", "FastAPI proje şablonu")]
    json_yaz(kok / "stars_000001.json", [
        {"type": "star", "repository": f"https://github.com/baska/{ad}", "name": f"baska/{ad}", "description": ac,
         "created_at": iso(u.an(D(2023, 1, 1), D(2026, 9, 1)))} for ad, ac in yildiz])
    commits = []
    # mahalle-takvimi: 2024-03 ->; sabahları 05:30-07:45 yerel (UTC 02:30-04:45) %85
    plan = [("mahalle-takvimi", D(2024, 3, 3), D(2026, 11, 5), 70), ("dotfiles", D(2022, 2, 10), D(2026, 10, 1), 22),
            ("go-sayac", D(2024, 5, 1), D(2025, 9, 1), 8), ("vscode-ayarlar", D(2022, 2, 1), D(2023, 10, 1), 10)]
    for repo, b, e, n in plan:
        msgs = COMMIT_MESAJ[repo]
        if repo == "dotfiles":  # 2022-23: vscode dönemi, nvim kayıtları 2025'ten
            pass
        for i in range(n):
            if repo == "dotfiles":
                m = u.sec(msgs)
                t = u.an(D(2025, 1, 25), e)
            else:
                m = u.sec(msgs)
                t = u.an(b, e)
            if rng.random() < 0.85:
                h, mi = rng.randint(5, 7), rng.randint(0, 59)
                if (h, mi) < (5, 30):
                    mi = 30 + mi % 30
                if h == 7 and mi > 45:
                    mi = 45
            else:
                h, mi = rng.randint(19, 22), rng.randint(0, 59)
            t = t.replace(hour=0, minute=0, second=0) + timedelta(hours=h - 3, minutes=mi, seconds=rng.randint(0, 59))
            commits.append({"type": "commit", "url": f"{base}/{repo}/commit/{rng.getrandbits(40):010x}",
                            "repository": f"{base}/{repo}", "message": m, "created_at": iso(t)})
    commits.sort(key=lambda c: c["created_at"])
    json_yaz(kok / "commits_000001.json", commits)
    json_yaz(kok / "issues_000001.json", [
        {"type": "issue", "url": f"{base}/mahalle-takvimi/issues/{i}", "repository": f"{base}/mahalle-takvimi", "title": t, "body": b,
         "state": s, "created_at": iso(u.an(D(2024, 4, 1), D(2026, 10, 1), (7, 9)))}
        for i, (t, b, s) in enumerate([
            ("Gece yarısı etkinlikleri çift görünüyor", "Saat dilimi dönüşümünde tekrar oluşuyor.", "closed"),
            ("Semt bazlı bildirim", "Kullanıcı semt seçince yeni etkinlikte haber alsın.", "open"),
            ("Belediye takviminden otomatik içe aktarma", "ics kaynaklarını toplayıcıya ekleyelim.", "open")], 1)])
    json_yaz(kok / "pull_requests_000001.json", [
        {"type": "pull_request", "url": f"{base}/mahalle-takvimi/pull/{i}", "title": t, "body": b, "state": "merged",
         "created_at": iso(u.an(D(2024, 6, 1), D(2026, 10, 1), (6, 8)))}
        for i, (t, b) in enumerate([("Sayfalama ve semt filtresi", "Liste uç noktasına sayfalama."),
                                    ("ics dışa aktarma", "Takvim uygulamalarına aktarım."),
                                    ("Toplayıcı yeniden deneme", "Zaman aşımında üstel bekleme.")], 1)])
    return {"commit": len(commits)}


def json_yaz(yol: Path, obj) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


SANATCI = {  # sanatçı -> (ağırlık, şarkılar). Hepsi uydurma.
    "Mavi Dalga": (30, ["Sisli Sahil", "Yankı Odası", "Gece Treni", "Kırık Ayna", "Soluk Mavi"]),
    "Gece Vardiyası": (14, ["Kırmızı Işık", "Boş Otobüs", "Son Durak"]),
    "Kuzey Rüzgârı Kolektifi": (12, ["Dağ Yolu", "Kar Tanesi", "Uzun Kış", "Yayla"]),
    "Pembe Radyo": (10, ["Eski Kaset", "Dalga Boyu", "Yaz Akşamı"]),
    "Tempo 160": (8, ["Koşu Temposu I", "Koşu Temposu II", "Son Kilometre"]),
    "Lale Devri Trio": (8, ["Bahçe Kapısı", "Sabah Çayı", "Süzülüş"]),
    "Sessiz Harita": (6, ["Kuzey", "Güney", "Pusula"]),
    "Neon Çarşı": (6, ["Gece Pazarı", "Camlar", "Vitrin"]),
    "Kalın Duvar": (6, ["Beton", "Çatı"]),
}
PODCAST = [("Kod ve Kahve", "Bölüm: Yarım kalan proje"), ("Bilim Sohbetleri", "Bölüm: Belirsizlik"), ("Satranç Sohbetleri", "Bölüm: Açılış repertuvarı")]


def spotify_yaz(u: Uretec, kok: Path) -> dict:
    d = kok / "Spotify Account Data"
    d.mkdir(parents=True, exist_ok=True)
    rng = u.rng
    adlar = list(SANATCI)
    agirlik = [SANATCI[a][0] for a in adlar]
    kayit, gorulen = [], set()
    for _ in range(900):
        a = rng.choices(adlar, agirlik)[0]
        s = rng.choice(SANATCI[a][1])
        t = u.an(D(2023, 1, 1), D(2026, 11, 8), (6, 23))
        if a == "Tempo 160":   # koşu listesi: yalnız 2026 yazı/sonbaharı sabahları
            t = u.an(D(2026, 5, 25), D(2026, 10, 15), (6, 8))
        k = (t.strftime("%Y-%m-%d %H:%M"), s)
        if k in gorulen:
            continue
        gorulen.add(k)
        kayit.append({"endTime": k[0], "artistName": a, "trackName": s, "msPlayed": rng.randint(60000, 260000)})
    kayit.sort(key=lambda r: r["endTime"])
    json_yaz(d / "StreamingHistory_music_0.json", kayit)
    pod = []
    for _ in range(45):
        p, b = rng.choice(PODCAST)
        pod.append({"endTime": u.an(D(2023, 6, 1), D(2026, 10, 30), (7, 22)).strftime("%Y-%m-%d %H:%M"),
                    "podcastName": p, "episodeName": b, "msPlayed": rng.randint(600000, 2400000)})
    pod.sort(key=lambda r: r["endTime"])
    json_yaz(d / "StreamingHistory_podcast_0.json", pod)
    json_yaz(d / "Playlist1.json", {"playlists": [
        {"name": n, "lastModifiedDate": dt, "description": None, "numberOfFollowers": 0, "items": [
            {"track": {"trackName": s, "artistName": a, "albumName": "Albüm", "trackUri": f"spotify:track:{sayi(s, 8)}"},
             "episode": None, "localTrack": None, "addedDate": dt} for a, s in it]}
        for n, dt, it in [
            ("Koşu Temposu 160", "2026-05-24", [("Tempo 160", s) for s in SANATCI["Tempo 160"][1]]),
            ("Sabah Shoegaze", "2025-03-02", [("Mavi Dalga", s) for s in SANATCI["Mavi Dalga"][1][:4]]),
            ("Derin Çalışma", "2025-06-10", [("Sessiz Harita", s) for s in SANATCI["Sessiz Harita"][1]])]]})
    json_yaz(d / "YourLibrary.json", {"tracks": [{"artist": "Mavi Dalga", "album": "Sisli Sahil", "track": "Sisli Sahil", "uri": "spotify:track:00000001"}],
                                      "albums": [], "shows": [], "episodes": [], "bannedTracks": [],
                                      "artists": [{"name": "Mavi Dalga", "uri": "spotify:artist:00000001"}]})
    json_yaz(d / "SearchQueries.json", [{"platform": "ANDROID", "searchTime": iso(u.an(D(2025, 1, 1), D(2026, 10, 1)), True),
                                         "searchQuery": q, "searchInteractionURIs": []} for q in ("mavi dalga yeni albüm", "shoegaze sabah listesi", "koşu bpm 160")])
    return {"muzik": len(kayit), "podcast": len(pod)}


# ---------------------------------------------------------------- sohbet dışa aktarmaları (HASSAS kategori)
def chatgpt_konusma(cid, baslik, t0: datetime, turlar):
    mapping = {"root": {"id": "root", "parent": None, "children": ["n1"], "message": None}}
    onceki, t = "root", t0.timestamp()
    for i, (rol, metin) in enumerate(turlar, 1):
        nid = f"n{i}"
        t += 25
        mapping[onceki]["children"] = [nid]
        mapping[nid] = {"id": nid, "parent": onceki, "children": [], "message": {
            "id": nid, "author": {"role": rol, "metadata": {}}, "create_time": t,
            "content": {"content_type": "text", "parts": [metin]}, "status": "finished_successfully", "end_turn": True,
            "weight": 1.0, "metadata": ({"model_slug": "gpt-4o"} if rol == "assistant" else {}), "recipient": "all"}}
        onceki = nid
    return {"title": baslik, "create_time": t0.timestamp(), "update_time": t, "mapping": mapping, "current_node": onceki,
            "conversation_id": cid, "id": cid}


def claude_konusma(cid, baslik, t0: datetime, turlar):
    msgs, t = [], t0
    for i, (rol, metin) in enumerate(turlar, 1):
        t = t + timedelta(seconds=30)
        msgs.append({"uuid": f"{cid}-m{i}", "text": metin, "content": [{"type": "text", "text": metin}],
                     "sender": "human" if rol == "user" else "assistant", "created_at": iso(t) .replace("Z", ".000000Z"),
                     "updated_at": iso(t).replace("Z", ".000000Z"), "attachments": [], "files": []})
    return {"uuid": cid, "name": baslik, "created_at": iso(t0).replace("Z", ".000000Z"), "updated_at": iso(t).replace("Z", ".000000Z"),
            "account": {"uuid": "hesap-uydurma"}, "chat_messages": msgs}


def sohbet_yaz(u: Uretec, kok: Path) -> dict:
    gpt = [
        chatgpt_konusma("g1", "Ukulele akor geçişleri", D(2025, 3, 8, 17), [
            ("user", "Ukulele için C ile Am7 arasındaki geçişleri çalışıyorum, akşamları 20 dakika yeter mi?"),
            ("assistant", "Evet, 20 dakika düzenli çalışma yeterli. Geçişleri metronomla yavaştan başlatın.")]),
        chatgpt_konusma("g2", "Lizbon 4 günlük plan", D(2026, 9, 14, 18), [
            ("user", "19-23 Aralık arasında Lizbon'da dört gün için yürüyerek gezilebilir bir plan çıkar."),
            ("assistant", "1. gün Alfama ve Baixa, 2. gün Belém, 3. gün Sintra, 4. gün Lx Factory ve alışveriş.")]),
        chatgpt_konusma("g3", "SQL pencere fonksiyonları", D(2025, 11, 2, 12), [
            ("user", "Pencere fonksiyonlarında ROWS ile RANGE farkı nedir?"),
            ("assistant", "ROWS fiziksel satırları, RANGE aynı değere sahip satır gruplarını esas alır.")]),
        chatgpt_konusma("g4", "Python asyncio hatası", D(2024, 9, 5, 7), [
            ("user", "asyncio.gather içinde bir görev hata verince diğerleri iptal oluyor mu?"),
            ("assistant", "Varsayılan olarak hayır; return_exceptions=True ile hataları toplayabilirsiniz.")]),
    ]
    json_yaz(kok / "chatgpt" / "conversations.json", gpt)
    cl = [
        claude_konusma("cl-1", "İş teklifi değerlendirme", D(2026, 10, 25, 20), [
            ("user", "Bulutiz'den kıdemli backend teklifi aldım. Maaş yüzde 35 artıyor ama ekip küçük ve proje yolu belirsiz. Nasıl değerlendirmeliyim?"),
            ("assistant", "Maaş dışında büyüme alanı, ekip kalitesi ve finansman durumunu karşılaştırın; tekliften önce üç soru sorun.")]),
        claude_konusma("cl-2", "V60 tarifi", D(2025, 6, 1, 6), [
            ("user", "V60 için 15 g kahveye kaç ml su, öğütme ne kadar ince olmalı?"),
            ("assistant", "Yaklaşık 1:16 oran, yani 240 ml; orta-ince öğütme, 2:45 civarı toplam süre hedefleyin.")]),
        claude_konusma("cl-3", "mahalle-takvimi mimarisi", D(2024, 7, 3, 6), [
            ("user", "Etkinlik toplayıcıyı zamanlanmış görev mi yoksa kuyruk mu yapmalıyım?"),
            ("assistant", "Küçük ölçekte zamanlanmış görev yeterli; kaynak sayısı artarsa kuyruğa geçin.")]),
    ]
    json_yaz(kok / "claude" / "conversations.json", cl)
    return {"chatgpt": len(gpt), "claude": len(cl)}


# ---------------------------------------------------------------- Google Takeout
def takeout_yaz(u: Uretec, kok: Path) -> dict:
    rng = u.rng
    T = kok / "Takeout"
    # --- arama
    arama = []
    for q, b, e, n in ARAMA_KANIT:
        for _ in range(n):
            arama.append((u.an(b, e), q))
    for _ in range(420):
        q = u.sec(ARAMA_GURULTU)
        t = u.an(D(2022, 1, 5), D(2026, 11, 8))
        if q == "hava durumu":
            q += " izmir" if t < D(2024, 1, 1) else " ankara"
        arama.append((t, q))
    arama.sort()
    json_yaz(T / "Etkinliklerim" / "Arama" / "Etkinliklerim.json", [
        {"header": "Search", "title": f"Searched for {q}", "titleUrl": f"https://www.google.com/search?q={quote_plus(q)}",
         "time": iso(t, True), "products": ["Search"], "activityControls": ["Web & App Activity"]} for t, q in arama])
    # --- YouTube izleme
    izle = []
    for baslik, kanal, b, e, n in VIDEO_KANIT:
        for _ in range(n):
            izle.append((u.an(b, e, (8, 23)), baslik, kanal))
    for _ in range(170):
        baslik, kanal = u.sec(VIDEO_GURULTU)
        izle.append((u.an(D(2022, 1, 5), D(2026, 11, 8), (8, 23)), baslik, kanal))
    izle.sort()
    yt = T / "YouTube ve YouTube Music"
    json_yaz(yt / "geçmiş" / "izleme geçmişi.json", [
        {"header": "YouTube", "title": f"Watched {bs}", "titleUrl": "https://www.youtube.com/watch?v=" + f"{rng.getrandbits(44):011x}",
         "subtitles": [{"name": k, "url": f"https://www.youtube.com/channel/UC{sayi(k)}"}],
         "time": iso(t, True), "products": ["YouTube"], "activityControls": ["YouTube watch history"]} for t, bs, k in izle])
    json_yaz(yt / "geçmiş" / "arama geçmişi.json", [
        {"header": "YouTube", "title": f"Searched for {q}", "titleUrl": f"https://www.youtube.com/results?search_query={quote_plus(q)}",
         "time": iso(u.an(b, b + timedelta(days=40)), True), "products": ["YouTube"], "activityControls": ["YouTube search history"]}
        for q, b, n in VIDEO_ARAMA for _ in range(n)])
    (yt / "abonelikler").mkdir(parents=True, exist_ok=True)
    with open(yt / "abonelikler" / "abonelikler.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Kanal Kimliği", "Kanal URL'si", "Kanal başlığı"])
        for k in KANALLAR:
            kid = f"UC{sayi(k)}"
            w.writerow([kid, f"http://www.youtube.com/channel/{kid}", k])
    # --- Chrome
    chrome = []
    for baslik, url, b, e, n in CHROME:
        for _ in range(n):
            chrome.append((u.an(b, e), baslik, url))
    for _ in range(120):
        bs, url = u.sec(CHROME_GURULTU)
        chrome.append((u.an(D(2022, 1, 5), D(2026, 11, 8)), bs, url))
    chrome.sort()
    json_yaz(T / "Chrome" / "History.json", {"Browser History": [
        {"favicon_url": "https://example.test/f.ico", "page_transition": u.sec(["LINK", "TYPED"]), "title": bs, "url": url,
         "client_id": "istemci", "time_usec": int(t.timestamp()) * 1_000_000} for t, bs, url in chrome]})
    # --- konum (HASSAS): hafta içi gündüz Ümitköy; hafta sonu Eymir
    ziyaret, nokta = [], []
    gun = D(2025, 9, 1, 6)
    while gun < D(2026, 10, 30):
        if gun.weekday() < 5 and rng.random() < 0.8:
            bas = gun.replace(hour=6, minute=rng.randint(0, 20))
            ziyaret.append({"placeVisit": {"location": {"latitudeE7": 398000000, "longitudeE7": 327000000, "placeId": "ChIJumitkoyOfis",
                            "address": "Ümitköy Mah., Çankaya, Ankara", "name": "Ümitköy Teknoloji Binası", "semanticType": "TYPE_WORK", "locationConfidence": 90},
                            "duration": {"startTimestamp": iso(bas, True), "endTimestamp": iso(bas + timedelta(hours=9), True)},
                            "placeConfidence": "HIGH_CONFIDENCE", "visitConfidence": 90, "placeVisitType": "SINGLE_PLACE",
                            "placeVisitImportance": "MAIN", "editConfirmationStatus": "NOT_CONFIRMED"}})
            nokta.append({"latitudeE7": 398000000 + rng.randint(-2000, 2000), "longitudeE7": 327000000 + rng.randint(-2000, 2000),
                          "accuracy": 20, "source": "WIFI", "timestamp": iso(bas + timedelta(hours=2), True)})
        elif gun.weekday() == 5 and rng.random() < 0.5:
            bas = gun.replace(hour=5, minute=30)
            ziyaret.append({"placeVisit": {"location": {"latitudeE7": 398300000, "longitudeE7": 327600000, "placeId": "ChIJeymir",
                            "address": "Eymir Gölü, Gölbaşı, Ankara", "name": "Eymir Gölü", "semanticType": "TYPE_UNKNOWN", "locationConfidence": 80},
                            "duration": {"startTimestamp": iso(bas, True), "endTimestamp": iso(bas + timedelta(hours=2), True)},
                            "placeConfidence": "HIGH_CONFIDENCE", "visitConfidence": 85, "placeVisitType": "SINGLE_PLACE",
                            "placeVisitImportance": "MAIN", "editConfirmationStatus": "NOT_CONFIRMED"}})
        gun += timedelta(days=1)
    kg = T / "Konum Geçmişi"
    json_yaz(kg / "Semantic Location History" / "2026" / "2026_EYLUL.json", {"timelineObjects": ziyaret})
    json_yaz(kg / "Records.json", {"locations": nokta})
    # --- Gmail mbox (HASSAS)
    posta = [
        ("Lizbon otel rezervasyonunuz onaylandı", "Otelbul <rezervasyon@otelbul.example.test>", D(2026, 10, 6, 9),
         "Rezervasyon kodunuz: LX7QK2. Giriş 19 Aralık 2026, çıkış 23 Aralık 2026, Alfama."),
        ("Ders kaydı onayı", "Sentez Üniversitesi <ogrenci@universite.example.test>", D(2026, 9, 12, 10),
         "Güz dönemi ders kaydınız tamamlandı: İstatistiksel Öğrenme, Bayes Yöntemleri."),
        ("Sonbahar Yarı Maratonu kayıt onayı", "Yarış <kayit@yaris.example.test>", D(2026, 6, 8, 11),
         "Kaydınız alındı. Yarış günü 18 Ekim 2026, başlangıç 08:30."),
        ("Haftalık bülten", "Bülten <bulten@haber.example.test>", D(2026, 10, 30, 7), "Bu haftanın öne çıkanları."),
    ]
    mb = []
    for konu, kimden, t, govde in posta:
        mb.append(f"From 18000000000000000{len(mb)}@xxx Mon Jan 01 00:00:00 +0000 2026\nX-GM-THRID: 18000000000000000{len(mb)}\n"
                  f"X-Gmail-Labels: Inbox\nDate: {t.strftime('%a, %d %b %Y %H:%M:%S +0000')}\nFrom: {kimden}\nTo: nehir@example.test\n"
                  f"Subject: {konu}\nMessage-ID: <m{len(mb)}@example.test>\nMIME-Version: 1.0\nContent-Type: text/plain; charset=UTF-8\n\n{govde}\n\n")
    (T / "Posta").mkdir(parents=True, exist_ok=True)
    (T / "Posta" / "Tüm posta.mbox").write_text("".join(mb), encoding="utf-8")
    return {"arama": len(arama), "izleme": len(izle), "chrome": len(chrome), "konum_ziyaret": len(ziyaret), "eposta": len(posta)}


def uret(cikti: Path, seed: int = SEED) -> dict:
    """Tüm sahte dışa aktarmaları `cikti/ham/` altına yazar; kaynak başına sayım döner."""
    ham = Path(cikti) / "ham"
    u = Uretec(seed)
    sayim = {"takeout": takeout_yaz(u, ham / "takeout"), "reddit": reddit_yaz(u, ham / "reddit"),
             "github": github_yaz(u, ham / "github"), "spotify": spotify_yaz(u, ham / "spotify"),
             "sohbet": sohbet_yaz(u, ham)}
    # Zamansız kayıtlar (abonelik, kütüphane) dosya tarihini kullanır: tekrarlanabilirlik için sabitle.
    sabit = datetime.fromisoformat(SIMDI.replace("Z", "+00:00")).timestamp()
    for p in ham.rglob("*"):
        os.utime(p, (sabit, sabit))
    return sayim
