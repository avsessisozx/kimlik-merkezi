# CI: PyInstaller + Inno Setup ile kurulum paketi üretir, sessiz kurar, dener, kaldırır.
# Yerelde de çalışır (Windows, Python ortamı kurulu). Çıktılar windows/paket/cikti/ altında.
param([string]$Surum = '0.1.0')
$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
$k = $PSScriptRoot
Set-Location $k
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

Adim 'Kurulu uygulamayı dene (açılış, sihirbaz, içe aktarma, Claude ekle, MCP stdio, sağlık)'
$calisma = Join-Path $env:RUNNER_TEMP 'km_dene'
if (-not $env:RUNNER_TEMP) { $calisma = Join-Path $env:TEMP 'km_dene' }
Remove-Item $calisma -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory $calisma | Out-Null
$fixture = (Resolve-Path "$k\..\..\importers\fixtures\takeout_tr").Path
# Ağ izleme: uygulama + MCP süreçleri yalnız 127.0.0.1 ile konuşuyor mu (docs/AG-GARANTISI.md; örnekleme, sınırları orada)
$agCikti = Join-Path $calisma 'ag_sonuc.json'
$agDurdur = Join-Path $calisma 'ag_durdur'
$agIzleyici = Start-Process powershell -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "$k\ag_izle.ps1", '-Cikti', $agCikti, '-DurdurDosyasi', $agDurdur) -PassThru -WindowStyle Hidden
python kurulu_dene.py $hedef $calisma $fixture $Surum
$deneKod = $LASTEXITCODE
Start-Sleep -Milliseconds 600
New-Item -ItemType File $agDurdur -Force | Out-Null
[void]$agIzleyici.WaitForExit(30000)
if ($deneKod) { throw 'kurulu_dene' }
Dene 'ağ izleyici sonuç yazdı' { Test-Path $agCikti }
$ag = Get-Content $agCikti -Raw | ConvertFrom-Json
Write-Host ("ağ izleme: {0} yoklama, {1} süreç görüldü, {2} yerel bağlantı, {3} ihlal" -f $ag.yoklama_sayisi, $ag.izlenen_surec_sayisi, $ag.yerel_baglanti_sayisi, @($ag.ihlaller).Count)
$ozet['ag_yoklama'] = $ag.yoklama_sayisi
$ozet['ag_izlenen_surec'] = $ag.izlenen_surec_sayisi
$ozet['ag_yerel_baglanti'] = $ag.yerel_baglanti_sayisi
$ozet['ag_ihlal'] = @($ag.ihlaller).Count
Dene 'ağ izleyici gerçekten çalıştı (yoklama yapıldı, uygulama süreci görüldü)' { ($ag.yoklama_sayisi -gt 5) -and ($ag.izlenen_surec_sayisi -gt 0) }
if ($ag.yerel_baglanti_sayisi -eq 0) { Write-Host '::warning::İzleyici hiç yerel (127.0.0.1) bağlantı yakalamadı; örnekleme kısa ömürlü bağlantıları kaçırmış olabilir (bilgi, hata değil).' }
if (@($ag.ihlaller).Count -gt 0) { $ag.ihlaller | ForEach-Object { Write-Host "::error::$_" } }
Dene 'uygulama ve MCP yalnız 127.0.0.1 ile bağlandı (dış bağlantı görülmedi)' { @($ag.ihlaller).Count -eq 0 }
Copy-Item $agCikti "$k\cikti\ag_sonuc.json" -Force

# ekransız sağlık komutu (konsol exe)
$o = & "$hedef\kimlikmerkezi-mcp.exe" saglik --veri "$calisma\veri" 2>&1 | Out-String
Write-Host $o
Dene 'konsol exe sağlık komutu geçti (çıkış 0)' { $LASTEXITCODE -eq 0 }

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
