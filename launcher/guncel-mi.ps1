# tactic11 - calisan sunucu GUNCEL kodu mu sunuyor?
#
# NEDEN: SUNUCU.bat yalniz ".next\BUILD_ID" YOKSA derliyordu ve 3000 dinleniyorsa
# hic dokunmuyordu. Sonuc: kod degisse bile eski derleme sunulmaya devam ediyor.
# Olculdu (2026-09-09): hem frontend hem backend 16 saat boyunca bir onceki gunun
# kodunu sundu; /video-tracking 404, /decisions/track 500 veriyordu ve bunu
# anlamanin hicbir yolu yoktu.
#
# YONTEM: git yerine DOSYA ZAMANI. Git SHA'si commit edilmemis degisiklikleri
# kacirir; derleme sonrasi yapilan bir duzenleme de bayatliktir.
#
# Cikis kodu:  0 = guncel   1 = BAYAT (yeniden derle/baslat)   2 = bilinmiyor
param(
  [Parameter(Mandatory = $true)][ValidateSet("frontend", "backend")] [string]$Bilesen,
  [string]$Kok
)

# DIKKAT: $Kok varsayilani param() icinde $PSScriptRoot OLAMAZ. Betik
# "powershell -File" ile calistirildiginda param varsayilanlari $PSScriptRoot
# HENUZ ATANMADAN degerlendirilir; $Kok bos kalir, tum yollar bozulur ve betik
# "kaynak okunamadi" (2) doner. Olculdu: SUNUCU.bat backend'i bu yuzden hic
# yeniden baslatmadi. Govdede atamak dogru calisir.
if (-not $Kok) {
  # Betik launcher\ icinde; proje koku BIR UST klasordur.
  $burasi = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
  if ($burasi) { $Kok = Split-Path -Parent $burasi }
}
if (-not $Kok) { Write-Output "proje klasoru bulunamadi"; exit 2 }

$fe = Join-Path $Kok "frontend"
$be = $Kok

# Yok sayilanlar: derleme ciktilari ve bagimlilik agaci - bunlar kaynak degil.
$YOKSAY = '\\(node_modules|\.next|__pycache__|\.git)\\'

function Get-NewestWrite {
  param([string[]]$Yollar)
  $en = $null
  foreach ($y in $Yollar) {
    # TEK DOSYA: dogrudan oku.
    # Get-ChildItem -Path <dosya> -Recurse KULLANILMAZ: PowerShell dosya adini
    # FILTRE sayip UST KLASORDEN itibaren ozyineliyor. package.json icin bu,
    # tum node_modules agacini taramak demek. Olculdu: bes config dosyasi
    # yuzunden tek kontrol 90 SANIYE suruyordu (dogru tarama 0,06 sn).
    if ([System.IO.File]::Exists($y)) {
      $t = [System.IO.File]::GetLastWriteTime($y)
      if (-not $en -or $t -gt $en) { $en = $t }
      continue
    }
    if (-not [System.IO.Directory]::Exists($y)) { continue }
    # KLASOR: .NET ile numaralandir - Get-ChildItem'in FileInfo nesnesi
    # uretmesinden belirgin hizli.
    try {
      foreach ($f in [System.IO.Directory]::EnumerateFiles(
                       $y, '*', [System.IO.SearchOption]::AllDirectories)) {
        if ($f -match $YOKSAY) { continue }
        $t = [System.IO.File]::GetLastWriteTime($f)
        if (-not $en -or $t -gt $en) { $en = $t }
      }
    } catch {
      # Erisim reddi vb. numaralandirmayi yarida keser: eksik cevap vermektense
      # "bilinmiyor" de. Cagiran taraf bunu "dokunma" olarak yorumluyor.
      return $null
    }
  }
  return $en
}

if ($Bilesen -eq "frontend") {
  $buildId = Join-Path $fe ".next\BUILD_ID"
  if (-not (Test-Path $buildId)) { Write-Output "derleme yok"; exit 1 }
  $derleme = (Get-Item $buildId).LastWriteTime
  # tsconfig.tsbuildinfo BILEREK yok: o bir derleme CIKTISI, derleme sirasinda
  # yenilenir; kaynak sayilirsa her kontrol "bayat" der ve sonsuz derleme olur.
  $kaynak = Get-NewestWrite @(
    (Join-Path $fe "src"),
    (Join-Path $fe "package.json"),
    (Join-Path $fe "next.config.js"),
    (Join-Path $fe "postcss.config.js"),
    (Join-Path $fe "tailwind.config.ts"),
    (Join-Path $fe "tsconfig.json")
  )
  if (-not $kaynak) { Write-Output "kaynak okunamadi"; exit 2 }
  if ($kaynak -gt $derleme) {
    Write-Output ("BAYAT: kaynak " + $kaynak.ToString("HH:mm") + " > derleme " + $derleme.ToString("HH:mm"))
    exit 1
  }
  Write-Output ("guncel (derleme " + $derleme.ToString("dd.MM HH:mm") + ")")
  exit 0
}

# backend: derleme yok; calisan SURECIN baslangici kaynaktan eski mi?
$conn = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $conn) { Write-Output "backend calismiyor"; exit 1 }
$proc = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $conn.OwningProcess) -ErrorAction SilentlyContinue
if (-not $proc) { Write-Output "surec okunamadi"; exit 2 }
$baslangic = $proc.CreationDate
$kaynak = Get-NewestWrite @((Join-Path $be "app"), (Join-Path $be "scripts"))
if (-not $kaynak) { Write-Output "kaynak okunamadi"; exit 2 }
if ($kaynak -gt $baslangic) {
  Write-Output ("BAYAT: kaynak " + $kaynak.ToString("HH:mm") + " > surec " + $baslangic.ToString("HH:mm"))
  exit 1
}
Write-Output ("guncel (surec " + $baslangic.ToString("dd.MM HH:mm") + ")")
exit 0
