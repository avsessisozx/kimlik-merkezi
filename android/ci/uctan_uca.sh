#!/bin/sh
# Emülatördeki GERÇEK uygulama -> ana makinedeki GERÇEK PC alıcısı (kimlikserver.aktarim) uçtan uca koşusu.
# Dört senaryo: (1) çevrimdışı biriktirme, (2) bağlanınca eksiksiz aktarım, (3) aktarım ortasında kesinti ve devam,
# (4) iki kez aktarım tekrarsız. Alıcıyı ana makine açar/kapatır/öldürür; aşamalar GercekPcTest yöntemleridir.
# Gerekenler: çalışan emülatör (adb), `python` (kimlikcore/kimlikserver/kimlikimport kurulu), derlenmiş APK'lar
# (yoksa gradlew ile derlenir). Herhangi bir aşama başarısızsa sıfır olmayan çıkış.
set -eu
ANDROID=$(cd "$(dirname "$0")/.." && pwd)
PY=${PY:-python}
ALICI="$PY $ANDROID/ci/pc_alici.py"
C=${CALISMA:-$(mktemp -d)}
PAKET=app.kimlikmerkezi.toplayici
KOSUCU="$PAKET.test/androidx.test.runner.AndroidJUnitRunner"
APK=$ANDROID/app/build/outputs/apk/debug/app-debug.apk
TAPK=$ANDROID/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
export PYTHONUNBUFFERED=1
BASLANGIC=$(date +%s)

zaman() { date +%s; }
sonuc_yaz() { echo "SONUC $1: $2"; }

temizle() {
  kod=$?
  [ "$kod" -eq 0 ] || { echo "--- ana makine baglantilari (47923)"; ss -tan 2>/dev/null | grep 47923 | awk '{print $1}' | sort | uniq -c || true; }
  $ALICI oldur --calisma "$C" >/dev/null 2>&1 || true
  if [ "$kod" -ne 0 ]; then
    echo "=== BASARISIZ (cikis $kod): tanilama ==="
    for f in alici.log ice_alma.log; do echo "--- $f"; tail -n 60 "$C/$f" 2>/dev/null || true; done
    echo "--- telefon gunlugu (icerik yazmaz)"; adb exec-out run-as "$PAKET" tail -n 40 files/gunluk.txt 2>/dev/null || true
    echo "--- telefon son_hata"; adb exec-out run-as "$PAKET" cat files/son_hata.txt 2>/dev/null | head -n 30 || true
    echo "--- logcat (UCTANUCA, AndroidRuntime)"; adb logcat -d -s UCTANUCA:I AndroidRuntime:E 2>/dev/null | tail -n 40 || true
  fi
}
trap temizle EXIT

asama() { # asama <yontem> [anahtar deger]...   Çıktı $C/asama_<yontem>.log; olcum satırlarını yazdırır
  ad=$1; shift
  ekstra=""
  while [ $# -gt 0 ]; do ekstra="$ekstra -e $1 $2"; shift 2; done
  # shellcheck disable=SC2086
  adb shell am instrument -w -r -e gercek_pc 1 -e class "$PAKET.GercekPcTest#$ad" $ekstra "$KOSUCU" >"$C/asama_$ad.log" 2>&1 || true
  grep -h "olcum=" "$C/asama_$ad.log" | sed 's/^INSTRUMENTATION_STATUS: //' || true
  if grep -qE "INSTRUMENTATION_STATUS_CODE: -[1-4]|Process crashed|INSTRUMENTATION_FAILED" "$C/asama_$ad.log" \
     || ! grep -q "INSTRUMENTATION_STATUS_CODE: 0" "$C/asama_$ad.log"; then
    echo "ASAMA BASARISIZ: $ad"; grep -vE "^INSTRUMENTATION_STATUS: (class|current|id|numtests|test)=" "$C/asama_$ad.log" | head -n 40
    return 1
  fi
  return 0
}

echo "== hazirlik: APK'lar, kurulum"
if [ ! -f "$APK" ] || [ ! -f "$TAPK" ]; then (cd "$ANDROID" && ./gradlew assembleDebug assembleDebugAndroidTest --console=plain -q); fi
adb install -r "$APK" >/dev/null
adb install -r -t "$TAPK" >/dev/null
adb shell pm clear "$PAKET" >/dev/null 2>&1 || true   # temiz kurulum; aşamalar arasında BİR DAHA silinmez

echo "== alici: sertifika/kod uretimi icin bir kez acilip kapatilir"
$ALICI baslat --calisma "$C"
KOD1=$(cat "$C/eslestirme_kodu.txt")
$ALICI durdur --calisma "$C"

echo "== SENARYO 1: cevrimdisi biriktirme (alici KAPALI)"
T=$(zaman); asama a1_biriktir km1 "$KOD1"; sonuc_yaz 1 "TAMAM ($(( $(zaman) - T )) sn): 120 kayit/3 dosya birikti, gonder=ulasilamadi, hicbir dosya silinmedi"

echo "== SENARYO 2: alici acik, gercek eslestirme + eksiksiz aktarim"
$ALICI baslat --calisma "$C"
KOD2=$($ALICI kod --calisma "$C")
T=$(zaman); asama a2_eslesGonder km1 "$KOD2"; sonuc_yaz 2 "TAMAM ($(( $(zaman) - T )) sn): eslestirme + 3 dosya var, telefonda bekleyen 0"

echo "== SENARYO 3: aktarim ortasinda alici OLDURULUR, yeniden acilir, kaldigi yerden tamamlanir"
T=$(zaman)
asama a3_kesinti1 > "$C/kesinti1.cikti" 2>&1 &
TELEFON=$!
if ! KISMI_IZLENEN=$($ALICI bekle-kismi --calisma "$C" --en-az 2097152 --sure 120); then
  kill $TELEFON 2>/dev/null || true; wait $TELEFON 2>/dev/null || true; cat "$C/kesinti1.cikti"; exit 1
fi
$ALICI oldur --calisma "$C"
KISMI=$($ALICI bekle-kismi --calisma "$C" --en-az 1 --sure 5)
echo "alici oldurulurken .part boyutu: izlenen=$KISMI_IZLENEN olum_sonrasi=$KISMI bayt"
wait $TELEFON || { cat "$C/kesinti1.cikti"; exit 1; }
cat "$C/kesinti1.cikti"
$ALICI baslat --calisma "$C"
asama a3_kesinti2 kismi "$KISMI"
sonuc_yaz 3 "TAMAM ($(( $(zaman) - T )) sn): kesinti .part=$KISMI bayttan devam, dosya tamamlandi, bekleyen 0"

echo "== SENARYO 4: ikinci aktarim tekrarsiz"
T=$(zaman); asama a4_tekrar
$ALICI durdur --calisma "$C"            # kalan her şey içe alınır, Hub kapanır
adb exec-out run-as "$PAKET" cat files/uctan_uca/beklenen.jsonl > "$C/beklenen.jsonl"
echo "beklenen kayit: $(( $(wc -l < "$C/beklenen.jsonl") - 1 ))"
$ALICI dogrula --calisma "$C" --beklenen "$C/beklenen.jsonl"
if grep -q "'yeni': 0, 'yinelenen': 40" "$C/ice_alma.log"; then
  echo "ayni 40 kayit baska dosya kimligiyle geldi: 0 yeni olay, 40 yinelenen (PC tekilleştirdi)"
else
  echo "HATA: ayni kayitlarin ikinci dosyasi 0 yeni/40 yinelenen olarak icerilmedi"; cat "$C/ice_alma.log"; exit 1
fi
sonuc_yaz 4 "TAMAM ($(( $(zaman) - T )) sn): ikinci gonder 0 dosya, ayni dosya PUT 200/var, olay kumesi == eklenen kumesi, tekrar yok"
echo "== ice alma gunlugu"; cat "$C/ice_alma.log"
echo "UCTAN UCA TAMAM: 4 senaryo, toplam $(( $(zaman) - BASLANGIC )) sn"
