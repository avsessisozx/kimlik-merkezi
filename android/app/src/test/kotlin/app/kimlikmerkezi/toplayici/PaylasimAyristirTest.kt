package app.kimlikmerkezi.toplayici

import app.kimlikmerkezi.toplayici.paylasim.PaylasimAyristir
import kotlinx.serialization.json.jsonPrimitive
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class PaylasimAyristirTest {
    @Test
    fun yalnizUrlLinktir() {
        val s = PaylasimAyristir.ayristir("https://ornek.test/a?b=1#c", "Başlık", "com.ornek.app")
        assertEquals("paylasim.link", s.tur)
        assertEquals("https://ornek.test/a?b=1#c", s.yuk["url"]!!.jsonPrimitive.content)
        assertEquals("Başlık", s.yuk["baslik"]!!.jsonPrimitive.content)
        assertEquals("com.ornek.app", s.yuk["kaynak_uygulama"]!!.jsonPrimitive.content)
    }

    @Test
    fun metinIcindekiUrlLinktirSondakiNoktalamaAtilir() {
        val s = PaylasimAyristir.ayristir("Bak şuna: (http://ornek.test/x). Güzel.", null, null)
        assertEquals("paylasim.link", s.tur)
        assertEquals("http://ornek.test/x", s.yuk["url"]!!.jsonPrimitive.content)
        assertEquals(setOf("url"), s.yuk.keys)
    }

    @Test
    fun wwwHttpsTamamlanir() {
        assertEquals("https://www.ornek.test", PaylasimAyristir.urlBul("www.ornek.test"))
    }

    @Test
    fun urlYoksaMetindir() {
        val s = PaylasimAyristir.ayristir("  sadece bir cümle, http yok  ", "yoksayılır", null)
        assertEquals("paylasim.metin", s.tur)
        assertEquals("sadece bir cümle, http yok", s.metin)
        assertEquals(emptySet(), s.yuk.keys)
        assertNull(PaylasimAyristir.urlBul("https:// bos"))
        assertNull(PaylasimAyristir.urlBul("ftp://x.y"))
    }

    @Test
    fun baslikAranabilirMetneGirer() {
        val s = PaylasimAyristir.ayristir("https://ornek.test/a", "Güzel yazı", null)
        assertEquals("Güzel yazı\nhttps://ornek.test/a", s.metin)
    }
}
