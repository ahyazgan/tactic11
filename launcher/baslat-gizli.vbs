' tactic11 - sunucuyu pencere olmadan (gizli) baslatir. SUNUCU.bat'i calistirir.
'
' Yolu SABIT GOMULU DEGIL: kendi bulundugu klasoru okur. Proje klasoru
' tasinsa, adi degisse ya da baska bir bilgisayara kurulsa da calisir.
'
' Bilgisayar acilisinda otomatik baslatmak icin ACILISA-EKLE.bat'a BIR KEZ
' cift tikla - o, Baslangic klasorune yolu gomulu AYRI bir kopya uretir
' (Baslangic klasorunden calisan bir betik proje klasorunu bulamayacagi icin).
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
kok = fso.GetParentFolderName(WScript.ScriptFullName)
sh.Run """" & kok & "\SUNUCU.bat""", 0, False
