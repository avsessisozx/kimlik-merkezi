# Ağ izleyici (CI, Windows): Kimlik Merkezi süreçlerinin TCP bağlantılarını yoklar ve 127.0.0.1 / ::1
# dışında bir uzak adres görürse kaydeder. ci_paket.ps1 bunu arka planda başlatır, işi bitince durdurur.
# SINIRLAR (docs/AG-GARANTISI.md): yoklama (örnekleme) yapar; yoklama aralığından kısa ömürlü bir bağlantı
# kaçabilir. UDP ve DNS sorguları süreçle eşlenemez (DNS'i svchost yapar). Bu adım kanıtı güçlendirir,
# tek başına "hiç bağlanmadı" demek için yeterli değildir; Python düzeyi koruma ve statik denetimle birlikte okunur.
param(
  [Parameter(Mandatory)][string]$Cikti,
  [Parameter(Mandatory)][string]$DurdurDosyasi,
  [string[]]$SurecAdlari = @('KimlikMerkezi', 'kimlikmerkezi-mcp'),
  [int]$AralikMs = 150
)
$ErrorActionPreference = 'Continue'
$yerel = @('127.0.0.1', '::1', '0.0.0.0', '::')
$ihlaller = New-Object System.Collections.Generic.HashSet[string]
$yerelGorulen = New-Object System.Collections.Generic.HashSet[string]
$izlenenSurec = New-Object System.Collections.Generic.HashSet[string]
$yoklama = 0
$hatalar = 0

function Torunlar([int[]]$kokler) {
  # kök süreçler + alt süreçleri (Win32_Process üst-süreç bağıyla)
  $hepsi = @{}
  foreach ($k in $kokler) { $hepsi[$k] = $true }
  $tum = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Select-Object ProcessId, ParentProcessId
  $degisti = $true
  while ($degisti) {
    $degisti = $false
    foreach ($p in $tum) {
      if ($hepsi.ContainsKey([int]$p.ParentProcessId) -and -not $hepsi.ContainsKey([int]$p.ProcessId)) { $hepsi[[int]$p.ProcessId] = $true; $degisti = $true }
    }
  }
  return @($hepsi.Keys)
}

while (-not (Test-Path $DurdurDosyasi)) {
  try {
    $kok = @(Get-Process -Name $SurecAdlari -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
    if ($kok.Count -gt 0) {
      $idler = Torunlar $kok
      foreach ($i in $idler) { [void]$izlenenSurec.Add([string]$i) }
      $baglar = Get-NetTCPConnection -OwningProcess $idler -ErrorAction SilentlyContinue
      foreach ($b in $baglar) {
        $uzak = ([string]$b.RemoteAddress)
        if ($b.State -eq 'Listen') {
          if ($yerel -notcontains ([string]$b.LocalAddress)) { [void]$ihlaller.Add("DİNLEME yerel olmayan adreste: $($b.LocalAddress):$($b.LocalPort) (süreç $($b.OwningProcess))") }
          continue
        }
        if ($yerel -contains $uzak) { [void]$yerelGorulen.Add("$($b.LocalAddress):$($b.LocalPort)->$uzak:$($b.RemotePort)"); continue }
        [void]$ihlaller.Add("DIŞ BAĞLANTI: süreç $($b.OwningProcess) $($b.LocalAddress):$($b.LocalPort) -> $uzak:$($b.RemotePort) ($($b.State))")
      }
    }
    $yoklama++
  } catch { $hatalar++ }
  Start-Sleep -Milliseconds $AralikMs
}

$sonuc = [ordered]@{
  yoklama_sayisi = $yoklama
  yoklama_hatasi = $hatalar
  izlenen_surec_sayisi = $izlenenSurec.Count
  yerel_baglanti_sayisi = $yerelGorulen.Count
  ihlaller = @($ihlaller)
}
$sonuc | ConvertTo-Json -Depth 4 | Out-File $Cikti -Encoding utf8
