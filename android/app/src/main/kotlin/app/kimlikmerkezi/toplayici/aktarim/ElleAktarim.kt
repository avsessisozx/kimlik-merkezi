package app.kimlikmerkezi.toplayici.aktarim

import app.kimlikmerkezi.toplayici.giden.GidenKutusu
import java.io.OutputStream
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

/** AKTARIM §5: kapatılmış dosyalar çözülmüş `.jsonl` olarak tek zip içine (ŞİFRESİZ). Silme ayrı ve onaylıdır. */
object ElleAktarim {
    /** Yazılan dosya kimlikleri. Dosya silinmez. */
    fun zipYaz(kutu: GidenKutusu, cikti: OutputStream): List<String> {
        kutu.acikDosyayiKapat()
        val idler = ArrayList<String>()
        ZipOutputStream(cikti).use { z ->
            for (d in kutu.kapatilmisDosyalar().sortedBy { it.acilis }) {
                z.putNextEntry(ZipEntry("${d.dosyaId}.jsonl"))
                kutu.dosyayiOku(d.dosyaId).use { it.copyTo(z) }
                z.closeEntry()
                idler.add(d.dosyaId)
            }
        }
        return idler
    }

    /** Kullanıcı "PC'ye alındı" dedikten sonra, yalnız bu zip'e giren dosyalar silinir. */
    fun sil(kutu: GidenKutusu, idler: List<String>) = idler.forEach { kutu.dosyayiSil(it) }
}
