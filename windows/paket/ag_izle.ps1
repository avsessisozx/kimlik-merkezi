# Ag izleyici (CI, Windows). DOSYA BILEREK YALNIZ ASCII: Windows PowerShell 5.1 BOM'suz UTF-8'i bozabilir.
# Kimlik Merkezi sureclerinin TCP baglantilarini yoklar; 127.0.0.1 / ::1 disinda uzak adres gorurse kaydeder.
# SINIRLAR (docs/AG-GARANTISI.md): yoklama (ornekleme) yapar; yoklama araligindan kisa omurlu baglanti kacabilir.
# UDP ve DNS sorgulari surecle eslenemez. Tek basina "hic baglanmadi" kaniti degildir.
# Her durumda (hata dahil) -Cikti dosyasina JSON yazar. -Hazir dosyasi ilk yoklamadan hemen once yazilir.
param(
  [Parameter(Mandatory = $true)][string]$Cikti,
  [Parameter(Mandatory = $true)][string]$DurdurDosyasi,
  [Parameter(Mandatory = $true)][string]$Hazir,
  [string[]]$SurecAdlari = @('KimlikMerkezi', 'kimlikmerkezi-mcp'),
  [int]$AralikMs = 150
)
$ErrorActionPreference = 'Continue'
$yerel = @('127.0.0.1', '::1', '0.0.0.0', '::')
$ihlaller = New-Object System.Collections.Generic.HashSet[string]
$yerelGorulen = New-Object System.Collections.Generic.HashSet[string]
$izlenenSurec = New-Object System.Collections.Generic.HashSet[string]
$yoklama = 0
$surecli = 0
$hatalar = 0
$sonHata = ''
$kritik = ''

function Torunlar($kokler) {
  $hepsi = @{}
  foreach ($k in $kokler) { $hepsi[[int]$k] = $true }
  $tum = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Select-Object ProcessId, ParentProcessId)
  $degisti = $true
  while ($degisti) {
    $degisti = $false
    foreach ($p in $tum) {
      if ($hepsi.ContainsKey([int]$p.ParentProcessId) -and -not $hepsi.ContainsKey([int]$p.ProcessId)) {
        $hepsi[[int]$p.ProcessId] = $true
        $degisti = $true
      }
    }
  }
  return @($hepsi.Keys)
}

try {
  'basladi ' + (Get-Date).ToString('o') + ' pid=' + $PID + ' surum=' + $PSVersionTable.PSVersion | Out-File $Hazir -Encoding ascii
  while (-not (Test-Path $DurdurDosyasi)) {
    try {
      $kok = @(Get-Process -Name $SurecAdlari -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
      if ($kok.Count -gt 0) {
        $surecli++
        $idler = @(Torunlar $kok)
        foreach ($i in $idler) { [void]$izlenenSurec.Add([string]$i) }
        $baglar = @(Get-NetTCPConnection -OwningProcess $idler -ErrorAction SilentlyContinue)
        foreach ($b in $baglar) {
          $uzak = [string]$b.RemoteAddress
          if ($b.State -eq 'Listen') {
            if ($yerel -notcontains ([string]$b.LocalAddress)) { [void]$ihlaller.Add("DINLEME yerel olmayan adreste: $($b.LocalAddress):$($b.LocalPort) (surec $($b.OwningProcess))") }
            continue
          }
          if ($yerel -contains $uzak) { [void]$yerelGorulen.Add("$($b.LocalAddress):$($b.LocalPort)->$($uzak):$($b.RemotePort)"); continue }
          [void]$ihlaller.Add("DIS BAGLANTI: surec $($b.OwningProcess) $($b.LocalAddress):$($b.LocalPort) -> $($uzak):$($b.RemotePort) ($($b.State))")
        }
      }
      $yoklama++
    } catch { $hatalar++; $sonHata = [string]$_ }
    Start-Sleep -Milliseconds $AralikMs
  }
} catch { $kritik = [string]$_ }

$sonuc = [ordered]@{
  yoklama_sayisi = $yoklama
  surecli_yoklama_sayisi = $surecli
  yoklama_hatasi = $hatalar
  son_hata = $sonHata
  kritik_hata = $kritik
  izlenen_surec_sayisi = $izlenenSurec.Count
  yerel_baglanti_sayisi = $yerelGorulen.Count
  ihlaller = @($ihlaller)
}
$sonuc | ConvertTo-Json -Depth 4 | Out-File $Cikti -Encoding ascii
