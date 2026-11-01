# Çalışma günlüğü — 1 Kasım 2026 (otonom oturum, 12:00'ye kadar)

Kullanıcı isteği: top sorununu çöz, diğer geliştirmeleri yap, durmadan 12:00'ye kadar
çalış; sorun olursa kaydet ve üzerine devam et. İş listesi: `BACKLOG.md` → "Claude
otonom oturum 2026-11-01". Her kayıt saat + ne yapıldı + sonuç/sorun.

## 06:40 — Top kaybı teşhisi
- TeamTrack test bölümünde (gerçek top etiketi, 1470 görüntü / 136 top) ince ayarlı
  model topu UNUTMAMIŞ: bulma %79,4 → %81,6, kesinlik %94,7 → %96,5.
- 117092 panoramasında kayıp gerçek: top tespitli kare %16,4 → %9,8 (hepsi saha içinde,
  oyuncu yakınında); oyundaki 37 olay anında topu görme %35 → %16.
- Sonuç: kayıp SoccerTrack kamerasına özgü; MOT dilimlerindeki etiketsiz toplar modele
  bu kamerada "top = arka plan" öğretti.
- Plan: v2 — MOT dilimlerinde topları eski modelle etiketle (öğretmen), 128058'i bağımsız
  test için tamamen ayır.

## Bekleyen kullanıcı kararları
- (yok)
