package app.kimlikmerkezi.toplayici.giden

import java.nio.ByteBuffer

/**
 * Disk çerçevesi (ayrıntı: android/BICIM.md):
 * `uzunluk(4 bayt, big-endian) + nonce(12) + şifreli metin + etiket(16)`, uzunluk = sonraki bayt sayısı.
 * AAD = dosya_id (UTF-8) + 0x00 + çerçeve sırası (8 bayt big-endian).
 */
object Cerceve {
    const val UST_SINIR = 16 * 1024 * 1024
    private const val EN_AZ = AesGcmSifreleyici.NONCE_BAYT + AesGcmSifreleyici.ETIKET_BAYT

    fun aad(dosyaId: String, sira: Long): ByteArray {
        val id = dosyaId.toByteArray(Charsets.UTF_8)
        return ByteBuffer.allocate(id.size + 9).put(id).put(0).putLong(sira).array()
    }

    fun yaz(s: Sifreleyici, dosyaId: String, sira: Long, duz: ByteArray): ByteArray {
        val paket = s.sifrele(duz, aad(dosyaId, sira))
        return ByteBuffer.allocate(4 + paket.size).putInt(paket.size).put(paket).array()
    }

    class Okuma(
        /** Çözülmüş çerçeve içerikleri (sırayla). */
        val icerikler: List<ByteArray>,
        /** Geçerli çerçevelerin kapladığı bayt sayısı (onarım bu noktaya keser). */
        val gecerliBayt: Int,
        /** Sonda yarım çerçeve var: süreç yazım ortasında ölmüş. */
        val yarimUc: Boolean,
        /** Bütün bir çerçeve vardı ama doğrulanamadı: bozulma/kurcalama. Okuma orada durdu. */
        val bozuk: Boolean,
    )

    fun oku(s: Sifreleyici, dosyaId: String, veri: ByteArray): Okuma {
        val cikti = ArrayList<ByteArray>()
        var konum = 0
        var sira = 0L
        while (konum < veri.size) {
            if (veri.size - konum < 4) return Okuma(cikti, konum, yarimUc = true, bozuk = false)
            val n = ByteBuffer.wrap(veri, konum, 4).int
            if (n < EN_AZ || n > UST_SINIR) return Okuma(cikti, konum, yarimUc = false, bozuk = true)
            if (veri.size - konum - 4 < n) return Okuma(cikti, konum, yarimUc = true, bozuk = false)
            val paket = veri.copyOfRange(konum + 4, konum + 4 + n)
            try {
                cikti.add(s.coz(paket, aad(dosyaId, sira)))
            } catch (e: BozukCerceveException) {
                return Okuma(cikti, konum, yarimUc = false, bozuk = true)
            }
            konum += 4 + n
            sira++
        }
        return Okuma(cikti, konum, yarimUc = false, bozuk = false)
    }
}
