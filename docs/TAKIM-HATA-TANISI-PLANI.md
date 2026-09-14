# Kamera takım hatalarının tanısı — 14 Eylül 2026

Başlangıç `883faea`; Codex kamera kapsamı. Önceki PR #237 kontrolleri izlenir.

1. `audit_team_errors.py`: mevcut 3 m birebir eşleme ve dondurulmuş hizalamayı
   koruyarak her gözlemin mesafesini, alternatif rakip konumunu, takip boyunca
   eşleşen GT takım/kimliklerini ve forma renklerini kaydet. İşaretler birbiriyle
   örtüşebilir; konumsal GT değişimini kesin takip hatası diye adlandırma.
2. Önce geliştirme bölümündeki en fazla hatayı taşıyan takipleri gerçek video
   kareleriyle incele. Renk hatası ile kalibrasyon/eşleme belirsizliğini ayır.
   Kontrol etiketlerinden sınıflandırıcı/eşik öğrenme.
3. Kanıtlanan düzeltme varsa aynı gözlemlerde geliştirme karşılaştırması yap;
   kararı sabitleyip kontrol et. Başarısız deneyi üretime alma. Ölçümün kendisi
   yanıltıcıysa öncelik güvenilir tanı ve rapor olsun.
4. Tanı hesapları için anlamlı regresyonlar; gerekli test/lint/tip kontrolleri,
   girdi hash'leriyle sonuç raporu, commit/push ve PR.
