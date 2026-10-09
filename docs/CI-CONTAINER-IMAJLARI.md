# CI container imajları

10 Ekim 2026. PR #282'nin ilk iki CI denemesinde Docker Hub, Python ve
PostgreSQL imajlarını kod çalışmadan önce `429 Too Many Requests` / anonim
indirme limiti nedeniyle reddetti. Başarılı test/lint işleri bu hataya dahil
değildi; başarısız işler atlanmadı.

CI artık aynı Docker Official Images içeriklerini Docker'ın ECR Public
deposundan, değişmez manifest digest'leriyle alır. Kaynağın resmî yayıncı
tarafından sunulduğu [Docker duyurusunda](https://www.docker.com/blog/news-from-aws-reinvent-docker-official-images-on-amazon-ecr-public/)
açıklanır. Kullanıcı hesabı, yeni ücretli hizmet veya yeni kimlik bilgisi
gerekmiyor.

Digest'ler önceki başarılı PR #281 işlerinin günlüklerinden alındı. ECR'den
manifestler okundu; ham baytların SHA-256 değerleri bu digest'lerle birebir
eşleşti ve Linux/amd64 alt manifestleri doğrulandı. Doğrulama sırasında imaj
katmanları yerel bilgisayara indirilmedi.

| CI girdisi | Sabit manifest |
|---|---|
| Python `3.11-slim` | `e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce` |
| PostgreSQL `16` | `ca0bd484cb98bf4b24eb1010e73fb3fcbd6714d240fbc1a10eea5b7dbecb641d` |

[Kaynak işler, manifest URL'leri ve doğrulama kaydı](measurements/ci-official-image-mirrors-20261010.json).

Dockerfile'ın `PYTHON_BASE_IMAGE` yapı argümanının varsayılanı
`python:3.11-slim` olarak kalır; CI argümanı sabit ECR kaynağını seçer.
Standart Dockerfile komutları yerleşik frontend ile derlenir; ayrıca
Docker Hub'dan `docker/dockerfile` frontend imajı indirilmez.

Bu sabitleme yeni imaj güncellemelerini otomatik olarak almaz. Güncellerken
resmî kaynak manifesti ve ECR bayt eşitliği yeniden doğrulanmalı, kayıt ile
workflow digest'leri birlikte değiştirilmeli; Docker build/import ve gerçek
PostgreSQL migration/rollback işleri tekrar geçmelidir.
