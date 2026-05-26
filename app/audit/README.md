# audit/

Açıklanabilirlik katmanı. "Neden bunu önerdi?" sorusunun cevabı.

**Faz 2'de dolmaya başlar.** Şimdi sadece interface + README: kayıt formatı belirlenir.

**Kayıt formatı (planlanan):**
```
AuditRecord(
    id, created_at,
    subject_type,     # team | player | match
    subject_id,
    metric,           # ör: "form_score", "load_risk"
    value,            # üretilen sonuç
    inputs,           # üretirken kullanılan metrikler/maçlar (JSON)
    engine_version,   # üreten kodun sürümü
    explanation?,     # ai/ üretimiyse insan-dili açıklama
)
```

**Tasarım kuralı:** Motor bir sonuç ürettiğinde dayandığı metriklerle birlikte
döner; `audit/` bunu kalıcı yazar. Engine doğrudan audit'e yazmaz — orkestrasyon
yazar (engine saf kalsın).
