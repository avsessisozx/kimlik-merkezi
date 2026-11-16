package app.kimlikmerkezi.toplayici

/** Süreci öldürebilecek deneyler: CI'de ayrı koşulur (asıl koşudan hariç). */
@Retention(AnnotationRetention.RUNTIME)
@Target(AnnotationTarget.FUNCTION, AnnotationTarget.CLASS)
annotation class Deney
