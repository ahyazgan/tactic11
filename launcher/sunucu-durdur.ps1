# tactic11 - projeye ait sunucu sureclerini durdur.
#
# NEDEN: Sunucular pencereden bagimsiz ve GIZLI calisiyor (baslat-gizli.vbs).
# Bu, terminali kapatinca sitenin kapanmamasi icin bilincli bir tercih; ama
# onlari durdurmanin baska yolu yok. Gorev Yoneticisi'nde "node.exe" ve
# "python.exe" olarak gorunuyorlar, hangisi oldugu belli degil.
#
# GOZETMEN ONCE (2026-09-09'da olculdu): yalniz node.exe'yi oldurmek YETMIYOR.
# SUNUCU.bat'i calistiran cmd.exe hayatta kaliyor ve sunucuyu GERI GETIRIYOR -
# olculdu: DURDUR sonrasi 3 saniye icinde 3000 portunu yeni bir node kaptigi
# icin BASLAT "portu baska program tutuyor" deyip derlemeyi reddetti. O yuzden
# once GOZETMEN zincir (SUNUCU.bat cmd'si ve npx sarmalayicilari), sonra node.
#
# KAPSAM: Yalniz BU KURULUMUN surecleri kapatilir - komut satiri bu betigin
# proje kokunu iceriyorsa. Makinede urunun ikinci bir kopyasi varsa ona
# dokunulmaz (satista onemli). Eskiden sabit "football-intelligence\frontend"
# metni araniyordu; o, her kopyayi eslestiriyordu.
param(
  [ValidateSet("frontend", "backend", "hepsi")] [string]$Bilesen = "hepsi",
  [switch]$Sessiz
)

# Betik launcher\ icinde; proje koku bir ust klasor.
$burasi = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$kok = Split-Path -Parent $burasi
if (-not $kok) { Write-Output "proje klasoru bulunamadi"; exit 2 }

$kapatilan = 0
function Yaz { param([string]$m) if (-not $Sessiz) { Write-Output $m } }

# KENDI ATALARIMIZI ASLA OLDURME.
# SUNUCU.bat ve BASLAT.bat bu betigi cagiriyor; ikisinin de komut satiri proje
# yolunu ve "SUNUCU.bat" metnini icerir - yani asagidaki gozetmen filtresine
# TAKILIRLAR. Olculdu (2026-09-09): koruma yokken SUNUCU.bat kendini oldurdu,
# cmd aninda -1 ile cikti, hicbir log satiri yazilmadi ve site hic acilmadi.
# Bayt-birebir kopyasi (farkli ADLA) sorunsuz calisiyordu - fark yalnizca isimdi.
$atalar = @{}
$id = $PID
while ($id -and -not $atalar.ContainsKey([int]$id)) {
  $atalar[[int]$id] = $true
  $pr = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $id) -ErrorAction SilentlyContinue
  if (-not $pr) { break }
  $id = [int]$pr.ParentProcessId
}

function Durdur {
  param([int]$Id, [string]$Etiket)
  if ($atalar.ContainsKey($Id)) { return }   # kendimiz ya da bizi cagiran
  try {
    Stop-Process -Id $Id -Force -ErrorAction Stop
    Yaz ("durduruldu: " + $Etiket + " (PID " + $Id + ")")
    $script:kapatilan++
  } catch {
    # Zaten olmus olabilir (gozetmeni oldurunce cocugu da gidebiliyor) - sorun degil.
    if (Get-Process -Id $Id -ErrorAction SilentlyContinue) {
      Yaz ("kapatilamadi: " + $Etiket + " PID " + $Id)
    }
  }
}

if ($Bilesen -in @("frontend", "hepsi")) {
  $hepsi = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
           Where-Object { $_.CommandLine }
  $bizim = $hepsi | Where-Object { $_.CommandLine -like ("*" + $kok + "*") }

  # 1) GOZETMENLER: SUNUCU.bat'i ya da BASLAT.bat'i calistiran kabuklar.
  #    Once bunlar; yoksa cocuk oldurulunce yenisini dogururlar.
  $gozetmen = $bizim | Where-Object {
    $_.Name -in @("cmd.exe", "wscript.exe", "cscript.exe") -and
    ($_.CommandLine -like "*SUNUCU.bat*" -or $_.CommandLine -like "*baslat-gizli.vbs*")
  }
  foreach ($g in $gozetmen) { Durdur -Id $g.ProcessId -Etiket ("gozetmen " + $g.Name) }

  # 2) npx sarmalayicilari: "cmd /d /s /c next start ...". Bunlarin komut satiri
  #    proje yolunu TASIMAZ, o yuzden cocugu (node) uzerinden sahiplik kurulur:
  #    ebeveyni bizim node'umuz olan ya da bizim node'u doguran kabuklar.
  $node = $bizim | Where-Object { $_.Name -eq "node.exe" }
  $ebeveynler = @{}
  foreach ($n in $node) { $ebeveynler[[int]$n.ParentProcessId] = $true }
  $sarmalayici = $hepsi | Where-Object {
    $_.Name -eq "cmd.exe" -and $ebeveynler.ContainsKey([int]$_.ProcessId) -and
    $_.CommandLine -like "*next*start*"
  }
  foreach ($s in $sarmalayici) { Durdur -Id $s.ProcessId -Etiket "npx sarmalayici" }

  # 3) Asil sunucular.
  foreach ($n in $node) { Durdur -Id $n.ProcessId -Etiket "frontend node" }
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
    Durdur -Id $c.OwningProcess -Etiket "backend python"
  }
}

if ($kapatilan -eq 0) { Yaz "calisan tactic11 sunucusu bulunamadi." }
exit 0
