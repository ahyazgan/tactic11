# data/validation/

DB'ye yazmadan ÖNCE veri kalite kapısı.

**Kontrol örnekleri:**
- Zorunlu alanlar dolu mu (takım adı, maç tarihi, skor mantığı)
- Tarih mantıklı mı (gelecekteki tamamlanmış maç olmaz)
- Aynı kayıt çift mi (external_id çakışması)
- Oyuncu birden çok takımda aynı anda mı görünüyor

**Sonuç:** Geçersiz/şüpheli kayıt sessizce çöpe ATILMAZ — loglanır ve "rejected"
işaretiyle saklanır (sonradan inceleme için).

**Tasarım:** Kurallar listesi + her kuralı uygulayan saf fonksiyon. Yeni kural
= yeni fonksiyon. Genişlemeye açık.

**Ne zaman dolacak:** Faz 1.
**Neye bağımlı:** `domain/`. (DB'ye veya kaynağa bağımlı değil — saf doğrulayıcı.)
