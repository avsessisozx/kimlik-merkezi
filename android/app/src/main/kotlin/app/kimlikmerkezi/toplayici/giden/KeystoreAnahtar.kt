package app.kimlikmerkezi.toplayici.giden

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.security.KeyStore
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey

/** Android Keystore'da duran, dışarı çıkarılamayan AES-256 anahtarı. */
object KeystoreAnahtar {
    const val TAKMA_AD = "km_giden_kutusu_v1"

    fun al(takmaAd: String = TAKMA_AD): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey(takmaAd, null) as? SecretKey)?.let { return it }
        val uretec = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        uretec.init(
            KeyGenParameterSpec.Builder(
                takmaAd,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build(),
        )
        return uretec.generateKey()
    }

    fun sifreleyici(): Sifreleyici = AesGcmSifreleyici(al())
}
