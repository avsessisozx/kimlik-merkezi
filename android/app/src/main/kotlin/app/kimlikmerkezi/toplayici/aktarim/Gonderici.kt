package app.kimlikmerkezi.toplayici.aktarim

import app.kimlikmerkezi.toplayici.giden.GidenKutusu
import app.kimlikmerkezi.toplayici.gunluk.Gunluk
import app.kimlikmerkezi.toplayici.topla.Depolama
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import java.io.IOException
import java.io.InputStream
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.NetworkInterface
import java.net.SocketTimeoutException
import java.security.MessageDigest
import java.util.concurrent.atomic.AtomicBoolean

sealed class AktarimDurumu {
    object Bosta : AktarimDurumu()
    object Araniyor : AktarimDurumu()
    data class Gonderiliyor(val dosyaNo: Int, val dosyaSayisi: Int, val bayt: Long, val toplamBayt: Long) : AktarimDurumu()
    data class Tamam(val dosya: Int, val kayit: Int) : AktarimDurumu()
    /** [kod]: eslesme_yok, yetkisiz, sertifika, ulasilamadi, reddedildi, bekle, sunucu, kutu */
    data class Hata(val kod: String) : AktarimDurumu()
}

/** Dosya bayt akışını ikinci kez açan kaynak (çözülmüş içerik). Testte sahte verilebilir. */
fun interface DosyaAcici {
    fun ac(dosyaId: String): InputStream
}

/**
 * AKTARIM §8 sırası: HEAD -> (yok/kismi) <= 1 MiB PUT parçaları -> `var` görülünce dosya silinir.
 * Bir dosya YALNIZ PC `var` dediğinde silinir.
 */
class Gonderici(
    private val kutu: GidenKutusu,
    private val eslesme: EslesmeDeposu,
    private val d: Depolama,
    private val gunluk: Gunluk,
    private val uretici: BaglantiUretici,
    private val cihazId: () -> String,
    private val bekle: (Long) -> Unit = { Thread.sleep(it) },
    private val simdi: () -> Long = { System.currentTimeMillis() },
    private val bulucu: (parmakIzi: String) -> Pair<String, Int>? = { Bulucu.bul(it) },
    private val parcaBayt: Int = PARCA,
    private val denemeSiniri: Int = 4,
) {
    private val _durum = MutableStateFlow<AktarimDurumu>(AktarimDurumu.Bosta)
    val durum: StateFlow<AktarimDurumu> get() = _durum
    private val calisiyor = AtomicBoolean(false)

    private class Dur(val kod: String) : Exception(kod)

    fun reddedilenSayisi(): Int = reddedilen().size
    private fun reddedilen(): Set<String> = d.metin(REDDEDILEN)?.split(',')?.filter { it.isNotBlank() }?.toSet().orEmpty()
    private fun reddet(id: String) = d.yazMetin(REDDEDILEN, (reddedilen() + id).joinToString(","))

    fun sonBasariMs(): Long = d.uzun(SON_BASARI, 0)
    fun sonKod(): String = d.metin(SON_KOD) ?: "-"

    /** Çalışan gönderim varsa null. */
    fun gonder(): AktarimDurumu? {
        if (!calisiyor.compareAndSet(false, true)) return null
        try {
            val s = try {
                calistir()
            } catch (e: Dur) {
                AktarimDurumu.Hata(e.kod)
            } catch (e: Exception) {
                gunluk.hata("gonder", e)
                AktarimDurumu.Hata("sunucu")
            }
            _durum.value = s
            d.yazMetin(SON_KOD, if (s is AktarimDurumu.Hata) s.kod else "tamam")
            if (s is AktarimDurumu.Tamam && s.dosya > 0) d.yazUzun(SON_BASARI, simdi())
            gunluk.bilgi("gonder", "sonuc ${if (s is AktarimDurumu.Hata) s.kod else "tamam"}")
            return s
        } finally {
            calisiyor.set(false)
        }
    }

    private fun calistir(): AktarimDurumu {
        if (!eslesme.eslesmis()) throw Dur("eslesme_yok")
        try {
            kutu.acikDosyayiKapat()
        } catch (e: Exception) {
            gunluk.hata("kapat", e)
            throw Dur("kutu")
        }
        val red = reddedilen()
        val dosyalar = kutu.kapatilmisDosyalar().filter { it.dosyaId !in red }.sortedBy { it.acilis }
        if (dosyalar.isEmpty()) return AktarimDurumu.Tamam(0, 0)
        _durum.value = AktarimDurumu.Araniyor
        val baglanti = baglantiBul()
        val anahtar = eslesme.anahtar() ?: throw Dur("eslesme_yok")
        var gonderilen = 0
        var kayit = 0
        var reddedildi = false
        dosyalar.forEachIndexed { i, f ->
            when (dosyaGonder(baglanti, anahtar, f.dosyaId, i + 1, dosyalar.size)) {
                Sonuc.VAR -> { gonderilen++; kayit += f.kayitSayisi }
                Sonuc.REDDEDILDI -> reddedildi = true
            }
        }
        if (reddedildi) throw Dur("reddedildi")
        return AktarimDurumu.Tamam(gonderilen, kayit)
    }

    private enum class Sonuc { VAR, REDDEDILDI }

    /** Kayıtlı adresler -> UDP bulma. Parmak izi uymazsa hemen "sertifika". */
    private fun baglantiBul(): PcBaglanti {
        val pin = eslesme.parmakIzi() ?: throw Dur("eslesme_yok")
        fun dene(a: String, p: Int): PcBaglanti? {
            if (!AdresSuzgeci.yerelMi(a)) return null
            return try {
                val b = uretici.ac(a, p)
                if (b.durum().kod in 200..299) b else null
            } catch (e: Exception) {
                if (e.sertifikaHatasiMi()) throw Dur("sertifika")
                null
            }
        }
        for (a in eslesme.adresler()) dene(a, eslesme.port())?.let { return it }
        val bulunan = try { bulucu(pin) } catch (e: Exception) { null }
        if (bulunan != null) {
            dene(bulunan.first, bulunan.second)?.let {
                eslesme.adresKaydet(bulunan.first, bulunan.second)
                return it
            }
        }
        throw Dur("ulasilamadi")
    }

    private fun <T> yeniden(is_: () -> T): T {
        var bekleme = 1000L
        var son: Exception? = null
        repeat(denemeSiniri) { n ->
            try {
                return is_()
            } catch (e: IOException) {
                if (e.sertifikaHatasiMi()) throw Dur("sertifika")
                son = e
                if (n < denemeSiniri - 1) { bekle(bekleme); bekleme *= 2 }
            }
        }
        gunluk.hata("ag", son!!)
        throw Dur("ulasilamadi")
    }

    private fun dosyaGonder(b: PcBaglanti, anahtar: String, id: String, no: Int, n: Int): Sonuc {
        val cihaz = cihazId()
        // 1. geçiş: özet ve boyut (çözülmüş akış, diske yazılmaz)
        val md = MessageDigest.getInstance("SHA-256")
        var toplam = 0L
        kutu_ac(id).use { s ->
            val t = ByteArray(64 * 1024)
            while (true) {
                val k = s.read(t)
                if (k < 0) break
                md.update(t, 0, k)
                toplam += k
            }
        }
        val sha = md.digest().joinToString("") { "%02x".format(it) }
        var alinan = 0L
        var hizalama = 0
        var durumKontrol = true
        while (true) {
            if (durumKontrol) {
                val h = yeniden { b.head(cihaz, id, anahtar) }
                yanitIsle(h.kod)?.let { return it }
                if (h.kod !in 200..299) throw Dur("sunucu")
                if (h.baslik("x-durum") == "var") return sil(id)
                alinan = h.baslik("x-alinan")?.toLongOrNull() ?: 0L
                durumKontrol = false
            }
            if (alinan >= toplam) throw Dur("sunucu")
            val parca = kutu_ac(id).use { s ->
                var atla = alinan
                while (atla > 0) { val k = s.skip(atla); if (k <= 0) throw Dur("kutu"); atla -= k }
                s.readNBytes(minOf(parcaBayt.toLong(), toplam - alinan).toInt())
            }
            _durum.value = AktarimDurumu.Gonderiliyor(no, n, alinan, toplam)
            val y = try {
                b.put(cihaz, id, anahtar, alinan, toplam, sha, parca)
            } catch (e: IOException) {
                if (e.sertifikaHatasiMi()) throw Dur("sertifika")
                // bağlantı koptu: bekle, PC'nin gerçek ofsetini HEAD ile öğren, kaldığı yerden sürdür
                yeniden { bekle(0); durumKontrol = true; b.head(cihaz, id, anahtar) }.let { }
                continue
            }
            yanitIsle(y.kod)?.let { return it }
            when {
                y.kod == 409 -> {
                    if (++hizalama > 5) throw Dur("sunucu")
                    alinan = y.baslik("x-alinan")?.toLongOrNull() ?: throw Dur("sunucu")
                }
                y.kod in 200..299 -> {
                    if (y.baslik("x-durum") == "var") return sil(id)
                    alinan = y.baslik("x-alinan")?.toLongOrNull() ?: (alinan + parca.size)
                }
                y.kod == 429 || y.kod == 507 -> { bekle(2000); throw Dur("bekle") }
                y.kod >= 500 -> { bekle(1000); durumKontrol = true }
                else -> throw Dur("sunucu")
            }
        }
    }

    /** Ortak kodlar: 401 tümünü durdurur (dosya silinmez), 422 dosyayı reddedilmiş işaretler. */
    private fun yanitIsle(kod: Int): Sonuc? {
        if (kod == 401) throw Dur("yetkisiz")
        if (kod == 422) return null.also { throw RedEdildi() }
        return null
    }

    private class RedEdildi : Exception()

    private fun kutu_ac(id: String): InputStream = try {
        kutu.dosyayiOku(id)
    } catch (e: Exception) {
        gunluk.hata("oku", e)
        throw Dur("kutu")
    }

    private fun sil(id: String): Sonuc {
        kutu.dosyayiSil(id)
        return Sonuc.VAR
    }

    companion object {
        const val PARCA = 1024 * 1024
        const val REDDEDILEN = "aktarim_reddedilen"
        const val SON_BASARI = "aktarim_son_basari_ms"
        const val SON_KOD = "aktarim_son_kod"
    }
}

/** UDP 47822 yayını ile PC'yi bulur; yanıt veren yerel adres ve port. */
object Bulucu {
    fun bul(parmakIzi: String, bekleMs: Int = 2000): Pair<String, Int>? {
        val istek = Bulma.istek(parmakIzi)
        DatagramSocket().use { s ->
            s.broadcast = true
            s.soTimeout = bekleMs
            for (h in yayinAdresleri()) {
                try { s.send(DatagramPacket(istek, istek.size, h, Bulma.PORT)) } catch (_: Exception) { }
            }
            val son = System.currentTimeMillis() + bekleMs
            val t = ByteArray(64)
            while (System.currentTimeMillis() < son) {
                val p = DatagramPacket(t, t.size)
                try { s.receive(p) } catch (e: SocketTimeoutException) { return null }
                val adres = p.address.hostAddress ?: continue
                val port = Bulma.yanit(p.data, p.length) ?: continue
                if (AdresSuzgeci.yerelMi(adres)) return adres to port
            }
        }
        return null
    }

    private fun yayinAdresleri(): List<InetAddress> {
        val l = ArrayList<InetAddress>()
        l.add(InetAddress.getByName("255.255.255.255"))
        try {
            for (n in NetworkInterface.getNetworkInterfaces().toList()) {
                if (!n.isUp || n.isLoopback) continue
                n.interfaceAddresses.mapNotNullTo(l) { it.broadcast }
            }
        } catch (_: Exception) { }
        return l.distinct()
    }
}
