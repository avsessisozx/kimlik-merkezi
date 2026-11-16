#!/bin/sh
# İmzalı release APK'sını emülatöre kurar, BAŞLATIR ve ana ekranın açıldığını doğrular. Kullanım: surum_dogrula.sh <apk>
set -eu
APK="$1"
PAKET=app.kimlikmerkezi.toplayici
adb install -r "$APK"
adb logcat -c
adb shell am start -W -n "$PAKET/.ui.MainActivity"
sleep 8
PID=$(adb shell pidof "$PAKET" || true)
[ -n "$PID" ] || { echo "HATA: uygulama calismiyor"; adb logcat -d | tail -40; exit 1; }
adb shell dumpsys window | grep -E "mCurrentFocus|mFocusedApp" | grep -q "MainActivity" || { echo "HATA: ana ekran on planda degil"; adb shell dumpsys window | grep -E "mCurrentFocus|mFocusedApp"; exit 1; }
if adb logcat -d | grep -q "FATAL EXCEPTION"; then echo "HATA: calisma sirasinda cokme"; adb logcat -d | grep -A15 "FATAL EXCEPTION" | head -40; exit 1; fi
echo "DOGRULANDI: release APK kuruldu, basladi, ana ekran acik"
