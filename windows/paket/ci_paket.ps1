# CI: PyInstaller + Inno Setup ile kurulum paketi üretir, sessiz kurar, dener, kaldırır.
# Yerelde de çalışır (Windows, Python ortamı kurulu). Çıktılar windows/paket/cikti/ altında.
param([string]$Surum = '0.1.1')
$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
$k = $PSScriptRoot
Set-Location $k
# CI'da uygulamanin GitHub surum denetimi KAPALI: ag izleyici hicbir istisna taniyamaz (docs/AG-GARANTISI.md).
# Bu degisken kurulu uygulamaya, kurulum programinin yeniden actigi kopyaya ve alt sureclere de gecer.
$env:KIMLIK_GUNCELLEME = 'kapali'
$ozet = [ordered]@{ surum = $Surum; python = (python --version) }
function Adim($m) { Write-Host "`n=== $m" -ForegroundColor Cyan }
function Dene($m, [scriptblock]$b) { if (-not (& $b)) { throw "BAŞARISIZ: $m" } else { Write-Host "[tamam] $m" } }

Adim 'Simge'
python simge_uret.py; if ($LASTEXITCODE) { throw 'simge' }

Adim 'PyInstaller'
$t = Measure-Command { python -m PyInstaller --noconfirm --distpath dist --workpath yapi kimlikmerkezi.spec; if ($LASTEXITCODE) { throw 'pyinstaller' } }
$ozet['pyinstaller_sn'] = [math]::Round($t.TotalSeconds, 1)
$dist = Join-Path $k 'dist\KimlikMerkezi'
Dene 'iki exe üretildi' { (Test-Path "$dist\KimlikMerkezi.exe") -and (Test-Path "$dist\kimlikmerkezi-mcp.exe") }
$ozet['klasor_mb'] = [math]::Round(((Get-ChildItem $dist -Recurse -File | Measure-Object Length -Sum).Sum) / 1MB, 1)

Adim 'Inno Setup'
$iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
if (-not $iscc) { $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
if (-not (Test-Path $iscc)) { choco install innosetup -y --no-progress; $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
$ozet['inno'] = (Get-Item $iscc).VersionInfo.ProductVersion
& $iscc "/DSurum=$Surum" "/DKaynak=$dist" KimlikMerkezi.iss
if ($LASTEXITCODE) { throw 'iscc' }
$kur = Get-Item "cikti\KimlikMerkezi-$Surum-kurulum.exe"
$ozet['kurulum_paketi_mb'] = [math]::Round($kur.Length / 1MB, 1)

Adim 'SHA256SUMS'
$h = (Get-FileHash $kur.FullName -Algorithm SHA256).Hash.ToLower()
"$h  $($kur.Name)" | Out-File -Encoding ascii -NoNewline cikti\SHA256SUMS
"`n" | Out-File -Encoding ascii -Append -NoNewline cikti\SHA256SUMS
Get-Content cikti\SHA256SUMS
# doğrulama (kullanıcının yapacağı gibi)
$beklenen = ((Get-Content cikti\SHA256SUMS | Select-Object -First 1) -split '\s+')[0]
Dene 'SHA256SUMS paketle eşleşiyor' { $beklenen -eq (Get-FileHash $kur.FullName -Algorithm SHA256).Hash.ToLower() }

function Kur() {
  $p = Start-Process $kur.FullName -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/TASKS=otobaslat', "/LOG=$k\cikti\kur.log" -Wait -PassThru
  return $p.ExitCode
}
function Kaldir($ek) {
  $u = Get-ChildItem $hedef -Filter 'unins*.exe' | Select-Object -First 1
  $a = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') + $ek
  Start-Process $u.FullName -ArgumentList $a -Wait
  Start-Sleep 3
}

Adim 'Sessiz kurulum'
$hedef = Join-Path $env:LOCALAPPDATA 'Programs\KimlikMerkezi'
$ozet['kurulum_cikis'] = Kur
Dene 'kurulum çıkış kodu 0' { $ozet['kurulum_cikis'] -eq 0 }
Dene 'kullanıcı klasörüne kuruldu (yönetici izni gerekmedi)' { (Test-Path "$hedef\KimlikMerkezi.exe") -and (Test-Path "$hedef\kimlikmerkezi-mcp.exe") -and -not (Test-Path "$env:ProgramFiles\KimlikMerkezi") }
Dene 'girişte başlama kaydı (HKCU Run) yazıldı' { [bool](Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name KimlikMerkezi -ErrorAction SilentlyContinue) }
Dene 'kurulum kaydındaki sürüm (Inno) = istenen sürüm' { (Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*' | Where-Object { $_.DisplayName -eq 'Kimlik Merkezi' } | Select-Object -First 1).DisplayVersion -eq $Surum }
Dene 'başlat menüsü kısayolu var' { Test-Path "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Kimlik Merkezi.lnk" }

Adim 'Kurulu uygulamayı dene (açılış, sihirbaz, dosya denetimi/tanila, içe aktarma, Claude ekle, MCP stdio, sağlık)'
$calisma = Join-Path $env:RUNNER_TEMP 'km_dene'
if (-not $env:RUNNER_TEMP) { $calisma = Join-Path $env:TEMP 'km_dene' }
Remove-Item $calisma -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory $calisma | Out-Null
$fixture = (Resolve-Path "$k\..\..\importers\fixtures\takeout_tr").Path
# Ağ izleme: uygulama + MCP süreçleri yalnız 127.0.0.1 ile konuşuyor mu (docs/AG-GARANTISI.md; örnekleme, sınırları orada)
# İzleyici PowerShell 7 (pwsh, bu betiği çalıştıran kabuk) ile ayrı süreçte başlar; çıktısı dosyaya yazılır.
$agCikti = Join-Path $calisma 'ag_sonuc.json'
$agDurdur = Join-Path $calisma 'ag_durdur'
$agHazir = Join-Path $calisma 'ag_hazir.txt'
$agOut = Join-Path $calisma 'ag_izle.out.txt'
$agErr = Join-Path $calisma 'ag_izle.err.txt'
Remove-Item $agCikti, $agDurdur, $agHazir, $agOut, $agErr -Force -ErrorAction SilentlyContinue
$kabuk = (Get-Process -Id $PID).Path
Write-Host "ağ izleyici kabuğu: $kabuk"
$agIzleyici = Start-Process $kabuk -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "$k\ag_izle.ps1", '-Cikti', $agCikti, '-DurdurDosyasi', $agDurdur, '-Hazir', $agHazir) -PassThru -WindowStyle Hidden -RedirectStandardOutput $agOut -RedirectStandardError $agErr
function AgGunlugu() {
  foreach ($f in @($agOut, $agErr)) { if (Test-Path $f) { Write-Host "--- $(Split-Path $f -Leaf)"; $m = Get-Content -LiteralPath $f -Raw -ErrorAction SilentlyContinue; if ($m) { Write-Host $m } } }
}
# Dosyayı DOLU görene kadar okur (izleyici dosyayı oluşturmuş ama içeriği henüz yazmamış olabilir; Get-Content
# bu durumda $null döner). Zaman aşımında dosyanın durumunu söyleyen net bir hata verir.
function OkuDolu([string]$Yol, [string]$Ad, [int]$ZamanAsimiMs = 15000) {
  $bitis = (Get-Date).AddMilliseconds($ZamanAsimiMs)
  do {
    $ham = $null
    if (Test-Path -LiteralPath $Yol) {
      try { $ham = Get-Content -LiteralPath $Yol -Raw -ErrorAction Stop } catch { $ham = $null }   # yazan tarafla yarış: sonra yeniden dene
    }
    if (($null -ne $ham) -and ($ham.Trim().Length -gt 0)) { return $ham.Trim() }
    Start-Sleep -Milliseconds 100
  } while ((Get-Date) -lt $bitis)
  $durum = if (Test-Path -LiteralPath $Yol) { "dosya var ama $([int](Get-Item -LiteralPath $Yol).Length) bayt (boş)" } else { 'dosya yok' }
  throw "BAŞARISIZ: $Ad $($ZamanAsimiMs / 1000) sn içinde dolu okunamadı ($Yol): $durum"
}
for ($i = 0; $i -lt 100 -and -not (Test-Path $agHazir) -and -not $agIzleyici.HasExited; $i++) { Start-Sleep -Milliseconds 200 }
if (-not (Test-Path $agHazir)) { AgGunlugu; throw "BAŞARISIZ: ağ izleyici başlamadı (çıkış kodu: $($agIzleyici.ExitCode)); örnek alınamadı" }
$agHazirMetin = OkuDolu $agHazir 'ağ izleyici hazır işareti'
Write-Host ("[tamam] ağ izleyici başladı: " + $agHazirMetin)
python kurulu_dene.py $hedef $calisma $fixture $Surum
$deneKod = $LASTEXITCODE
Start-Sleep -Milliseconds 600
New-Item -ItemType File $agDurdur -Force | Out-Null
if (-not $agIzleyici.WaitForExit(30000)) { Write-Host '::warning::ağ izleyici 30 sn içinde kapanmadı, zorla durduruluyor'; Stop-Process -Id $agIzleyici.Id -Force -ErrorAction SilentlyContinue }
AgGunlugu
if ($deneKod) { throw 'kurulu_dene' }
if (-not (Test-Path $agCikti)) { throw 'BAŞARISIZ: ağ izleyici sonuç dosyası yazmadı (izleyici çökmüş olabilir; yukarıdaki çıktılara bakın)' }
$agMetin = OkuDolu $agCikti 'ağ izleyici sonuç dosyası'
$ag = $agMetin | ConvertFrom-Json
if ($null -eq $ag) { throw "BAŞARISIZ: ağ izleyici sonucu çözümlenemedi: $agMetin" }
Write-Host "ağ izleme sonucu:"
Write-Host ($ag | ConvertTo-Json -Depth 4)
Write-Host ("ağ izleme: {0} yoklama ({1} tanesinde uygulama süreci vardı), {2} süreç görüldü, {3} yerel bağlantı, {4} yoklama hatası, {5} ihlal" -f $ag.yoklama_sayisi, $ag.surecli_yoklama_sayisi, $ag.izlenen_surec_sayisi, $ag.yerel_baglanti_sayisi, $ag.yoklama_hatasi, @($ag.ihlaller).Count)
$ozet['ag_yoklama'] = $ag.yoklama_sayisi
$ozet['ag_surecli_yoklama'] = $ag.surecli_yoklama_sayisi
$ozet['ag_izlenen_surec'] = $ag.izlenen_surec_sayisi
$ozet['ag_yerel_baglanti'] = $ag.yerel_baglanti_sayisi
$ozet['ag_ihlal'] = @($ag.ihlaller).Count
Dene 'ağ izleyici kritik hata vermedi' { -not $ag.kritik_hata }
Dene 'örnek alınabildi (yoklama yapıldı ve uygulama süreci görüldü; aksi halde kanıt yok sayılır)' { ($ag.yoklama_sayisi -gt 5) -and ($ag.surecli_yoklama_sayisi -gt 0) -and ($ag.izlenen_surec_sayisi -gt 0) }
if ($ag.yoklama_hatasi -gt 0) { Write-Host "::warning::izleyici $($ag.yoklama_hatasi) yoklamada hata aldı, son hata: $($ag.son_hata)" }
if ($ag.yerel_baglanti_sayisi -eq 0) { Write-Host '::warning::İzleyici hiç yerel (127.0.0.1) bağlantı yakalamadı; örnekleme kısa ömürlü bağlantıları kaçırmış olabilir (bilgi, hata değil).' }
if (@($ag.ihlaller).Count -gt 0) { $ag.ihlaller | ForEach-Object { Write-Host "::error::$_" } }
Dene 'uygulama ve MCP yalnız 127.0.0.1 ile bağlandı (dış bağlantı görülmedi)' { @($ag.ihlaller).Count -eq 0 }
Copy-Item $agCikti "$k\cikti\ag_sonuc.json" -Force

# ekransız sağlık komutu (konsol exe)
$o = & "$hedef\kimlikmerkezi-mcp.exe" saglik --veri "$calisma\veri" 2>&1 | Out-String
Write-Host $o
Dene 'konsol exe sağlık komutu geçti (çıkış 0)' { $LASTEXITCODE -eq 0 }

Adim 'Üstüne kurulum (uygulama içi güncelleme akışı): veri klasörü ve ayarlar korunmalı'
Dene 'çalışan uygulama kalmadı (kurulumdan önce)' { -not (Get-Process -Name KimlikMerkezi, kimlikmerkezi-mcp -ErrorAction SilentlyContinue) }
python veri_parmak.py yaz "$calisma\parmak.json" "$calisma\veri" "$calisma\ayar\ayarlar.json"
Dene 'veri/ayar parmak izi alındı' { $LASTEXITCODE -eq 0 }
# Gerçek bir sürüm yükseltmesi: aynı kaynaktan bir üst yama numarasıyla ikinci paket (çıktı klasörü ayrı: yayın işi ilk paketi seçer)
if ($Surum -match '^(\d+)\.(\d+)\.(\d+)') { $Surum2 = "$($Matches[1]).$($Matches[2]).$([int]$Matches[3] + 1)" } else { $Surum2 = '99.0.0' }
$yukselt = Join-Path $k 'yukselt'
Remove-Item $yukselt -Recurse -Force -ErrorAction SilentlyContinue
& $iscc "/DSurum=$Surum2" "/DKaynak=$dist" "/O$yukselt" KimlikMerkezi.iss
if ($LASTEXITCODE) { throw 'iscc (yükseltme paketi)' }
$kur2 = Get-Item "$yukselt\KimlikMerkezi-$Surum2-kurulum.exe"
# Uygulamanın güncelleme sırasında çalıştırdığı bayraklar (guncelleme.py kurulum_komutu; girişte başlatma AÇIK senaryosu)
# DİKKAT: -Wait kullanılmaz; /GUNCELLEME=1 kurulumun yeniden açtığı uygulamayı da bekler ve takılır. Yalnız kurulum işlemi beklenir.
$p2 = Start-Process $kur2.FullName -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/TASKS=otobaslat', '/GUNCELLEME=1', "/LOG=$k\cikti\kur2.log" -PassThru
if (-not $p2.WaitForExit(300000)) { $p2 | Stop-Process -Force; throw 'üstüne kurulum 5 dakikada bitmedi' }
$ozet['yukseltme_kurulum_cikis'] = $p2.ExitCode
Dene 'üstüne kurulum çıkış kodu 0' { $p2.ExitCode -eq 0 }
Dene 'kurulum kaydındaki sürüm yükseldi (Inno)' { (Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*' | Where-Object { $_.DisplayName -eq 'Kimlik Merkezi' } | Select-Object -First 1).DisplayVersion -eq $Surum2 }
Dene 'program dosyaları yerinde' { (Test-Path "$hedef\KimlikMerkezi.exe") -and (Test-Path "$hedef\kimlikmerkezi-mcp.exe") }
python veri_parmak.py denetle "$calisma\parmak.json"
Dene 'veri klasörü ve ayarlar üstüne kurulumda AYNEN korundu (dosya adları, boyutlar, SHA-256)' { $LASTEXITCODE -eq 0 }
# /GUNCELLEME=1 ile kurulum bitince uygulama yeniden açılır (kurulum programı açar; tepside/arka planda çalışır)
$acildi = $false
for ($i = 0; $i -lt 60 -and -not $acildi; $i++) { $acildi = [bool](Get-Process -Name KimlikMerkezi -ErrorAction SilentlyContinue); if (-not $acildi) { Start-Sleep -Milliseconds 500 } }
Dene 'güncelleme bayrağıyla kurulum sonrası uygulama yeniden açıldı' { $acildi }
Get-Process -Name KimlikMerkezi, kimlikmerkezi-mcp -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep 2
Remove-Item $yukselt -Recurse -Force -ErrorAction SilentlyContinue

Adim 'Kaldırma: varsayılan (veri KALMALI)'
Kaldir @()
Dene 'program klasörü silindi' { -not (Test-Path $hedef) }
Dene 'Run kaydı silindi' { -not (Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name KimlikMerkezi -ErrorAction SilentlyContinue) }
Dene 'veri klasörü silinmedi' { Test-Path "$calisma\veri\kimlik.db" }

Adim 'Kaldırma: /SILVERIYI=1 (veri silinmeli)'
$ozet['yeniden_kurulum_cikis'] = Kur
Dene 'yeniden kurulum 0' { $ozet['yeniden_kurulum_cikis'] -eq 0 }
Kaldir @('/SILVERIYI=1')
Dene 'program klasörü silindi' { -not (Test-Path $hedef) }
Dene 'veri klasörü silindi' { -not (Test-Path "$calisma\veri") }

$ozet['sonuc'] = 'TUM ADIMLAR GECTI'
$json = $ozet | ConvertTo-Json
$json | Out-File cikti\ozet.json -Encoding utf8
$json
if ($env:GITHUB_STEP_SUMMARY) { "### Windows paketi`n``````json`n$json`n``````" | Out-File $env:GITHUB_STEP_SUMMARY -Append -Encoding utf8 }
