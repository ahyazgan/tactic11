# tactic11 - ne calisiyor, guncel mi, otomatik acilis kurulu mu?
#
# NEDEN: Sunucular gizli calistigi icin durumlarini gormenin hicbir yolu yoktu.
# 2026-09-09'da hem frontend hem backend 16 saat boyunca bir onceki gunun
# kodunu sundu; site aciliyordu, sayfalar 404/500 veriyordu ve nedeni
# gorunmuyordu. Bu rapor tam o soruyu cevaplar: "su an hangi kod calisiyor?"
#
# Turkce ozel karakter BILEREK kullanilmiyor: PowerShell 5.1 BOM'suz .ps1
# dosyalarini ANSI okur, cikti bozulur (bkz. cp1254 stdout tuzagi).
$burasi = $PSScriptRoot                 # launcher\ klasoru
$kok = Split-Path -Parent $burasi       # proje koku (football-intelligence\)

function Satir {
  param([string]$ad, [string]$deger)
  $etiket = if ($ad) { $ad + ":" } else { "" }   # bos ad = devam satiri, ":" basma
  Write-Output ("  {0,-16} {1}" -f $etiket, $deger)
}

function Port {
  param([int]$p)
  $c = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $c) { return $null }
  $proc = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $c.OwningProcess) -ErrorAction SilentlyContinue
  if (-not $proc) { return $null }
  return [pscustomobject]@{ Pid = $c.OwningProcess; Ad = $proc.Name; Baslangic = $proc.CreationDate }
}

function Guncellik {
  param([string]$bilesen)
  $cikti = & (Join-Path $burasi "guncel-mi.ps1") -Bilesen $bilesen -Kok $kok
  return [pscustomobject]@{ Kod = $LASTEXITCODE; Mesaj = ($cikti -join " ") }
}

Write-Output ""
Write-Output "=== tactic11 durum ==="
Write-Output ""

# --- Frontend ---
Write-Output "SITE (frontend, port 3000)"
$fe = Port 3000
if ($fe) {
  Satir "durum" ("calisiyor - " + $fe.Ad + " PID " + $fe.Pid)
  Satir "baslangic" $fe.Baslangic.ToString("dd.MM.yyyy HH:mm")
  # Port dinlemek YETMEZ. 2026-09-09'daki ariza tam buydu: port aciktı ama
  # /video-tracking 404 veriyordu. Gercekten sayfa donuyor mu, sorulur.
  foreach ($yol in @("/", "/video-tracking")) {
    try {
      $r = Invoke-WebRequest -Uri ("http://localhost:3000" + $yol) -UseBasicParsing `
             -TimeoutSec 10 -ErrorAction Stop
      Satir "sayfa" ("{0,-16} HTTP {1}" -f $yol, $r.StatusCode)
    } catch {
      $kod = $_.Exception.Response.StatusCode.value__
      Satir "sayfa" ("{0,-16} !! {1}" -f $yol, $(if ($kod) { "HTTP $kod" } else { "cevap yok" }))
    }
  }
} else {
  Satir "durum" "CALISMIYOR  (baslatmak icin BASLAT.bat)"
}
# Derleme durumu sunucu kapaliyken de anlamli (derleme diskte durur).
$fg = Guncellik "frontend"
Satir "kod" $(if ($fg.Kod -eq 0) { $fg.Mesaj } else { "!! " + $fg.Mesaj })
if ($fg.Kod -ne 0 -and $fe) {
  Satir "" "-> BASLAT.bat calistir: yeniden derlenip guncel kod sunulacak."
}
Write-Output ""

# --- Backend ---
Write-Output "API (backend, port 8000)"
$be = Port 8000
if ($be) {
  Satir "durum" ("calisiyor - " + $be.Ad + " PID " + $be.Pid)
  Satir "baslangic" $be.Baslangic.ToString("dd.MM.yyyy HH:mm")
  try {
    $h = Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 3 -ErrorAction Stop
    Satir "saglik" ("durum=" + $h.status + "  surum=" + $h.version + "  db=" + $h.db)
  } catch { Satir "saglik" "/health cevap vermedi" }
  # Bayatlik yalniz CALISAN surec icin anlamli: derleme yok, karsilastirma
  # "kaynak zamani vs surec baslangici" uzerinden yapiliyor.
  $bg = Guncellik "backend"
  Satir "kod" $(if ($bg.Kod -eq 0) { $bg.Mesaj } else { "!! " + $bg.Mesaj })
  if ($bg.Kod -eq 1) { Satir "" "-> BASLAT.bat calistir: API yeniden baslatilacak." }
} else {
  Satir "durum" "calismiyor  (site yine acilir, demo veriye duser)"
}
Write-Output ""

# --- Otomatik acilis ---
Write-Output "OTOMATIK ACILIS"
$startup = [Environment]::GetFolderPath('Startup')
$kayit = Join-Path $startup "tactic11-baslat.vbs"
if (Test-Path $kayit) {
  Satir "durum" "KURULU"
  # Kaydin isaret ettigi yol hala var mi? Klasor tasinmissa acilis sessizce kirilir.
  $icerik = Get-Content $kayit -Raw -ErrorAction SilentlyContinue
  $m = [regex]::Match($icerik, '"([^"]+SUNUCU\.bat)"')
  if ($m.Success) {
    $hedef = $m.Groups[1].Value
    Satir "hedef" $hedef
    if (-not (Test-Path $hedef)) {
      Satir "" "!! HEDEF YOK - acilis calismaz. ACILISA-EKLE.bat'i tekrar calistir."
    } elseif ((Resolve-Path $hedef).Path -ne (Resolve-Path (Join-Path $burasi "SUNUCU.bat")).Path) {
      Satir "" "!! Kayit BASKA bir klasoru gosteriyor. ACILISA-EKLE.bat'i tekrar calistir."
    }
  } else {
    Satir "" "!! Kayit okunamadi - ACILISA-EKLE.bat'i tekrar calistir."
  }
} else {
  Satir "durum" "kurulu degil  (eklemek icin ACILISA-EKLE.bat)"
}
Write-Output ""
Write-Output "  Adres: http://localhost:3000    Durdurmak: DURDUR.bat"
Write-Output ""
