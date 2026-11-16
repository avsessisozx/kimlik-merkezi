package app.kimlikmerkezi.toplayici.aktarim

import com.google.zxing.BinaryBitmap
import com.google.zxing.DecodeHintType
import com.google.zxing.PlanarYUVLuminanceSource
import com.google.zxing.ReaderException
import com.google.zxing.common.HybridBinarizer
import com.google.zxing.qrcode.QRCodeReader

/** zxing-core (Apache-2.0), çevrimdışı. Girdi: Y (parlaklık) düzlemi. */
object QrCozucu {
    fun coz(y: ByteArray, genislik: Int, yukseklik: Int, satirAdimi: Int = genislik): String? = try {
        val kaynak = PlanarYUVLuminanceSource(y, satirAdimi, yukseklik, 0, 0, genislik, yukseklik, false)
        QRCodeReader().decode(BinaryBitmap(HybridBinarizer(kaynak)), mapOf(DecodeHintType.TRY_HARDER to true)).text
    } catch (e: ReaderException) {
        null
    }
}
