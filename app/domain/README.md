# domain/

Spordan ve sağlayıcıdan bağımsız çekirdek modeller.

**Bugün:** League, Team, Match, Player (pydantic).
**Yarın:** Lineup, Event, TrackingFrame eklenecek.

**Kural:** Burada hiçbir model API yanıtı şekline ya da DB tablosu yapısına
özel olmaz. Bu, sistemin "iç dili"dir. Sources buraya çevirir, DB buradan eşler,
engine bunu okur.

**Spor parametrik:** Modellerde `sport: str` alanı taşınır; futbol özel sabitler
`sports/football.py`'de durur.

**Çok-kulüp hazırlığı:** Bugün `tenant_id` eklenmedi ama modeller bunu sonradan
ekleyecek şekilde basit tutuldu. Tek-kulüp varsayımı koda gömülmemeli.

**Neye bağımlı:** Hiçbir uygulama katmanına. Salt veri.
