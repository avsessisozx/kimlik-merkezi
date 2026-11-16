package app.kimlikmerkezi.toplayici.giden

import app.kimlikmerkezi.toplayici.gunluk.SabitIletili
import java.security.GeneralSecurityException
import javax.crypto.Cipher
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Çerçeve şifreleme arayüzü. Gerçek uygulamada Keystore anahtarı, birim testte sahte anahtar kullanılır. */
interface Sifreleyici {
    /** Dönen bayt dizisi: nonce(12) + şifreli metin + etiket(16). */
    fun sifrele(duz: ByteArray, aad: ByteArray): ByteArray

    /** Doğrulama başarısızsa [BozukCerceveException] fırlatır. */
    fun coz(paket: ByteArray, aad: ByteArray): ByteArray
}

/** İletisi içerik taşımaz. */
class BozukCerceveException(ileti: String) : Exception(ileti), SabitIletili

/** AES-256-GCM. [anahtar] Keystore'daki ya da (testte) bellekteki anahtar olabilir; nonce'u sağlayıcı üretir. */
class AesGcmSifreleyici(private val anahtar: SecretKey) : Sifreleyici {
    override fun sifrele(duz: ByteArray, aad: ByteArray): ByteArray {
        val c = Cipher.getInstance(DONUSUM)
        c.init(Cipher.ENCRYPT_MODE, anahtar)
        c.updateAAD(aad)
        val nonce = c.iv
        check(nonce.size == NONCE_BAYT) { "beklenmeyen nonce boyu" }
        return nonce + c.doFinal(duz)
    }

    override fun coz(paket: ByteArray, aad: ByteArray): ByteArray {
        if (paket.size < NONCE_BAYT + ETIKET_BAYT) throw BozukCerceveException("cerceve cok kisa")
        try {
            val c = Cipher.getInstance(DONUSUM)
            c.init(Cipher.DECRYPT_MODE, anahtar, GCMParameterSpec(ETIKET_BAYT * 8, paket, 0, NONCE_BAYT))
            c.updateAAD(aad)
            return c.doFinal(paket, NONCE_BAYT, paket.size - NONCE_BAYT)
        } catch (e: GeneralSecurityException) {
            throw BozukCerceveException("cerceve dogrulanamadi")
        }
    }

    companion object {
        const val DONUSUM = "AES/GCM/NoPadding"
        const val NONCE_BAYT = 12
        const val ETIKET_BAYT = 16
    }
}
