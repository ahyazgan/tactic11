# sports/

Spor-spesifik sabitler ve tanımlar. "Bir sporu tanımlayan parametre kümesi"
burada toplanır; geri kalan kod bunlara isimle değil koda bağlıdır.

**Bugün dolu:** `football.py`
**İleride (Ufuk 4):** `basketball.py`, `volleyball.py`. `football.py` şablon alınır.

**Tutulması gereken bilgi tipleri:**
- spor adı (string sabit)
- pozisyon kodları
- skor yapısı (futbol: ev/dep gol; basketbol: çeyrek skorları)
- "maç tamamlandı" anlamı

**Kural:** `engine/`, `data/`, `api/` içinden `"football"` literal'i geçmez —
bu modülün sabitleri kullanılır.
