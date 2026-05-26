# snapshot/

Zaman içinde durum kaydı. Her sync'te o anki takım/oyuncu durumunun bir özetini
zaman damgasıyla saklar — **üzerine yazmadan**, geçmiş biriktirilir.

**Neden gerekli:**
- "Geçen ay X takımının formu neydi?" sorusu cevaplanabilsin.
- "Tahmin doğru çıktı mı?" için geçmiş durum + sonraki gerçek lazım.
- ML tahmin (`engine/predict/`) eğitim verisinin doğal kaynağı bu.

**Faz 1'de:** sadece temel mekanizma — bir `snapshot_record` tablosu ve
"şu anda kaydet" fonksiyonu. Sorgulayan tarafı sonra geliştirilir.

**Neye bağımlı:** `db/`, `domain/`.
