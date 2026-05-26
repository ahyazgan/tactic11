# core/usage/

Maliyet ve kota koruması.

**Ne yapar:**
- API-Football çağrılarını sayar (günlük/aylık).
- (İleride) Claude token kullanımını sayar.
- Eşik tanımlanır: yaklaşınca uyarı log'u, aşınca çağrıyı engelle.

**Amaç:** kotayı bir anda tüketmemek, sürpriz fatura yememek.

**Ne zaman dolacak:** Faz 1.
**Neye bağımlı:** sadece `core/config` ve `db/` (sayaçları kalıcı tutmak için).

**Arayüz (planlanan):**
```python
class UsageMeter:
    def record(self, provider: str, units: int = 1) -> None: ...
    def check(self, provider: str) -> UsageStatus: ...  # OK | NEAR | EXCEEDED
```
