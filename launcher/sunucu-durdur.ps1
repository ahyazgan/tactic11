# tactic11 - projeye ait sunucu sureclerini durdur.
#
# NEDEN: Sunucular pencereden bagimsiz ve GIZLI calisiyor (baslat-gizli.vbs).
# Bu, terminali kapatinca sitenin kapanmamasi icin bilincli bir tercih; ama
# bugune kadar onlari durdurmanin hicbir yolu yoktu. Gorev Yoneticisi'nde
# "node.exe" ve "python.exe" olarak gorunuyorlar, hangisi oldugu belli degil.
#
# GUVENLIK: Yalniz KOMUT SATIRI bu projeyi gosteren surecler kapatilir.
# Baska bir node/python projesi calisiyorsa ona dokunulmaz.
param(
  [ValidateSet("frontend", "backend", "hepsi")] [string]$Bilesen = "hepsi",
  [switch]$Sessiz
)

$kapatilan = 0

function Yaz { param([string]$m) if (-not $Sessiz) { Write-Output $m } }

if ($Bilesen -in @("frontend", "hepsi")) {
  $node = Get-CimInstance Win32_Process -Filter "name='node.exe'" -ErrorAction SilentlyContinue |
          Where-Object { $_.CommandLine -like '*football-intelligence\frontend*' }
  foreach ($p in $node) {
    try {
      Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
      Yaz ("durduruldu: frontend (node PID " + $p.ProcessId + ")")
      $kapatilan++
    } catch { Yaz ("kapatilamadi: node PID " + $p.ProcessId) }
  }
}

if ($Bilesen -in @("backend", "hepsi")) {
  # 8000'i dinleyeni bul; ama KOMUT SATIRI dev_api'yi gostermiyorsa DOKUNMA.
  # Baska bir program 8000'i tutuyor olabilir - onu kapatmak bizim isimiz degil.
  $conn = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
  foreach ($c in $conn) {
    $p = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $c.OwningProcess) -ErrorAction SilentlyContinue
    if (-not $p) { continue }
    if ($p.CommandLine -notlike '*dev_api*') {
      Yaz ("dokunulmadi: 8000 portunu baska program tutuyor (" + $p.Name + " PID " + $c.OwningProcess + ")")
      continue
    }
    try {
      Stop-Process -Id $c.OwningProcess -Force -ErrorAction Stop
      Yaz ("durduruldu: backend (python PID " + $c.OwningProcess + ")")
      $kapatilan++
    } catch { Yaz ("kapatilamadi: python PID " + $c.OwningProcess) }
  }
}

if ($kapatilan -eq 0) { Yaz "calisan tactic11 sunucusu bulunamadi." }
exit 0
