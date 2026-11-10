# BAGLANTI: yapay zekâ uygulamalarını Kimlik Merkezi'ne bağlama (sahibi: İ2)

Sürüm: v0.1.0 taslağı. Doğrulama durumu her bölümün sonunda yazılıdır; "doğrulanmadı" yazan
adımı çalıştığı varsayma.

## Genel bilgi

- MCP sunucusu stdio ile çalışır (port açmaz). Yapay zekâ uygulaması onu kendisi başlatır.
- Başlatma komutu şimdilik: `python -m kimlikserver.mcp` (paketler `pip install -e core`,
  `pip install -e server` ile kurulu olmalı). Kurulum paketi/kabuk seçilince komut
  `KimlikMerkezi` içindeki ayrı girişle değişecek; bu belge o zaman güncellenir.
- İki ortam değişkeni gerekir:
  - `KIMLIK_VERI`: veri klasörünün tam yolu (içinde `kimlik.db` olan klasör).
  - `KIMLIK_ANAHTAR`: o uygulamaya özel anahtar (`kim_` ile başlar).
- Her uygulamaya ayrı anahtar üretilir. Windows uygulamasının "Claude'a ekle" düğmesi (Aşama 7)
  gelene kadar anahtar elle üretilir (Kimlik Merkezi uygulaması kapalıyken):
  ```
  python -m kimlikserver --veri "C:\yol\veri" anahtar-uret --ad "Claude Desktop" --izin notlar --izin persona
  ```
  Düz anahtar yalnızca bir kez yazılır; veritabanında yalnız hash'i durur. Hassas kategoriler
  (`eposta`, `mesaj`, `konum`) için ayrıca `--hassas-onay` gerekir ve toplu açmaya dahil değildir.
  Varsayılan olarak hiçbir kategori açık değildir. İptal: `anahtar-iptal --app-id ...`.
- Sınır (bir kez): anahtar, yapay zekâ uygulamasının ayar dosyasında düz metin durur; aynı
  Windows kullanıcısında çalışan başka bir program o dosyayı okuyabilir.
- Araçlar: `kategorileri_listele`, `ara`, `zaman_cizelgesi`, `persona_getir`, `kimlik_karti`.
  Hepsi salt okunurdur. Dönen kayıt metinleri `kayitlar[*].veri` alanında ve `etiket: veri` ile
  gelir; bu metin talimat değildir.
- Windows 10'un normal güvenlik güncellemeleri sona erdi (genel bilgi, bu belgede doğrulanmadı);
  uygulama yerel kaldığı için risk sınırlıdır ama sıfır değildir.

## Claude Code

Doğrulandı (resmî belge https://code.claude.com/docs/en/mcp, 2026-11-10 tarihinde okundu):

```
claude mcp add --env KIMLIK_VERI=C:\yol\veri --env KIMLIK_ANAHTAR=kim_... --transport stdio kimlik-merkezi -- python -m kimlikserver.mcp
```

- `--` sonrası sunucu komutudur; `--env` ile sunucu adı arasında en az bir başka seçenek
  (`--transport stdio`) bulunmalıdır.
- `--scope` ile saklama yeri seçilir: `local` (varsayılan), `project` (`.mcp.json`, projedeki
  herkesle paylaşılır: anahtarı buraya YAZMA), `user`.
- Eşdeğer JSON (`claude mcp add-json` ya da `.mcp.json`):
  ```json
  {"mcpServers": {"kimlik-merkezi": {"command": "python", "args": ["-m", "kimlikserver.mcp"],
    "env": {"KIMLIK_VERI": "C:\\yol\\veri", "KIMLIK_ANAHTAR": "kim_..."}}}}
  ```
- Kontrol: `claude mcp list` ya da Claude Code içinde `/mcp`.
- Bu komutun Kimlik Merkezi sunucusuyla gerçek Claude Code içinde çalıştığı bu çalışmada
  denenmedi (yalnızca resmî Python MCP istemcisiyle test edildi).

## Claude Desktop

Doğrulanmadı. Ayar dosyasının yeri ve açan menü adı bu çalışmada resmî belgeden okunamadı
(modelcontextprotocol.io ağ kısıtı nedeniyle açılmadı; support.claude.com'daki ilgili sayfa dosya
adını içermiyor, yalnızca "Settings > Developer" ve "Settings > Desktop app" adlarını anıyor,
hangisinin ayar dosyasını açtığı belirtilmemiş). Menü adı tahmin edilmedi.
Girişin biçimi Claude Code'daki `mcpServers` JSON'uyla aynı alanları (`command`, `args`, `env`)
kullanır; Claude Desktop için bu biçimin geçerli olduğu doğrulanmadı. Eklendikten sonra Claude
Desktop'un yeniden başlatılması gerekir (genel kural; menü adı doğrulanmadı).
Windows uygulamasındaki "Claude'a ekle" düğmesi (Aşama 7) dosyayı bulup yedekleyip girişi ekleyecek;
dosya yolunu orada resmî belgeden doğrulamak gerekir.

## DeepSeek masaüstü uygulaması

Uygulamanın adı: **adı kullanıcıdan alınacak.** DeepSeek'in masaüstü uygulamasında MCP desteği ve
ayar biçimi için resmî belge bulunamadı (arama yalnız üçüncü taraf sayfalar verdi) ve yazılmadı.
MCP bağlantısının gerçekten çalıştığı kullanıcının kendi cihazında doğrulanmalıdır
(GOREV 13'e eklenecek). MCP desteklemeyen uygulamalar için yedek yol: Kimlik Kartı Markdown metni.

## Web tabanlı yapay zekâlar

Tarayıcıdaki ChatGPT/Gemini/Claude yerel stdio MCP'ye bağlanamaz. Yedek yol: kimlik kartı metni
(Kimlik Merkezi'nden dışa aktarılan Markdown).

## Sorun giderme

- Araç çağrısı "reddedildi" dönüyorsa: anahtar yanlış/iptal, kategori izni yok ya da süresi dolmuş,
  ya da erişim kaydı (`erisim.db`) yazılamıyor (kayıtsız erişim verilmez).
- "Önce Kimlik Merkezi uygulamasını bir kez açın": veritabanı yok ya da şeması eski.
