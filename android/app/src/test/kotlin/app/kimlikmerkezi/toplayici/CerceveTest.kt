package app.kimlikmerkezi.toplayici

import app.kimlikmerkezi.toplayici.giden.AesGcmSifreleyici
import app.kimlikmerkezi.toplayici.giden.BozukCerceveException
import app.kimlikmerkezi.toplayici.giden.Cerceve
import java.nio.ByteBuffer
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class CerceveTest {
    private val s = AesGcmSifreleyici(TestYardim.ANAHTAR)
    private val id = "b7d1e4a2-93c5-4f08-a1b6-2d8e5c3f7a90"

    @Test
    fun gidisDonus() {
        val metinler = listOf("bir\n", "iki ğüşiöç\n", "x".repeat(100_000) + "\n")
        val disk = metinler.mapIndexed { i, m -> Cerceve.yaz(s, id, i.toLong(), m.toByteArray()) }.reduce { a, b -> a + b }
        val o = Cerceve.oku(s, id, disk)
        assertFalse(o.bozuk); assertFalse(o.yarimUc)
        assertEquals(disk.size, o.gecerliBayt)
        assertEquals(metinler, o.icerikler.map { String(it) })
    }

    @Test
    fun cerceveBicimi() {
        val duz = "merhaba\n".toByteArray()
        val c = Cerceve.yaz(s, id, 0, duz)
        // uzunluk öneki = nonce(12) + şifreli metin + etiket(16); big-endian
        assertEquals(12 + duz.size + 16, ByteBuffer.wrap(c, 0, 4).int)
        assertEquals(4 + 12 + duz.size + 16, c.size)
        assertFalse(String(c, Charsets.ISO_8859_1).contains("merhaba"))
        // her çerçeve farklı nonce
        val c2 = Cerceve.yaz(s, id, 0, duz)
        assertFalse(c.copyOfRange(4, 16).contentEquals(c2.copyOfRange(4, 16)))
    }

    @Test
    fun bozukCerceveReddedilir() {
        val c = Cerceve.yaz(s, id, 0, "gizli\n".toByteArray())
        for (konum in listOf(4, 12, 16, c.size - 1)) { // nonce, şifreli metin, etiket
            val b = c.copyOf(); b[konum] = (b[konum].toInt() xor 0x80).toByte()
            val o = Cerceve.oku(s, id, b)
            assertTrue(o.bozuk, "bayt $konum"); assertTrue(o.icerikler.isEmpty())
        }
        // uzunluk alanı bozuk
        val u = c.copyOf(); u[0] = 0x7f
        assertTrue(Cerceve.oku(s, id, u).bozuk)
    }

    @Test
    fun yanlisDosyaVeSiraReddedilir() {
        val c = Cerceve.yaz(s, id, 0, "a\n".toByteArray())
        assertTrue(Cerceve.oku(s, "baska-dosya", c).bozuk)
        val c1 = Cerceve.yaz(s, id, 1, "a\n".toByteArray())
        assertTrue(Cerceve.oku(s, id, c1).bozuk) // sıra 0 bekleniyor
    }

    @Test
    fun yanlisAnahtarReddedilir() {
        val c = Cerceve.yaz(s, id, 0, "a\n".toByteArray())
        val baska = AesGcmSifreleyici(javax.crypto.KeyGenerator.getInstance("AES").apply { init(256) }.generateKey())
        assertTrue(Cerceve.oku(baska, id, c).bozuk)
        assertFailsWith<BozukCerceveException> { baska.coz(c.copyOfRange(4, c.size), Cerceve.aad(id, 0)) }
    }

    @Test
    fun yarimUcTespitEdilir() {
        val a = Cerceve.yaz(s, id, 0, "a\n".toByteArray())
        val b = Cerceve.yaz(s, id, 1, "b\n".toByteArray())
        for (kesilen in listOf(1, 3, 5, b.size - 1)) {
            val o = Cerceve.oku(s, id, a + b.copyOf(b.size - kesilen))
            assertTrue(o.yarimUc, "kesilen $kesilen"); assertFalse(o.bozuk)
            assertEquals(a.size, o.gecerliBayt)
            assertEquals(1, o.icerikler.size)
        }
        assertContentEquals("a\n".toByteArray(), Cerceve.oku(s, id, a).icerikler[0])
    }
}
