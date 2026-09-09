# Veri kaynakları ve lisansları

tactic11 **ticari** bir üründür. Kullanılan her veri kaynağının lisansı burada
kayıtlıdır; atıf gerektirenler ürünle birlikte gösterilmelidir.

## Kullanımda

| Kaynak | Lisans | Ne | Atıf |
|---|---|---|---|
| **StatsBomb Open Data** | [kendi şartları](https://github.com/statsbomb/open-data) | La Liga event verisi (101 maç külliyatı) | StatsBomb |
| **SkillCorner Open Data** | MIT | Yayından çıkarılmış takip verisi (A-League) | SkillCorner |
| **Orange County SC vs Oakland Roots** | **CC BY 3.0** | 4K yayın maç özeti (kamera/kesme doğrulaması) | **BZFilms** |
| RF-DETR | Apache-2.0 | Nesne tespiti | — |
| supervision (ByteTrack) | MIT | Takip | — |

### CC BY 3.0 atıf metni (ürün/dokümanda gösterilmeli)

> Video: "Game Highlights @OrangeCountySoccerClub Vs Oakland Roots" —
> [BZFilms](https://www.youtube.com/@BZFilms), [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/),
> [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Game_Highlights_%40OrangeCountySoccerClub_Vs_Oakland_Roots.webm)

## Bilerek KULLANILMAYANLAR

| Kaynak | Neden |
|---|---|
| YouTube / archive.org tam maç yayınları | **Telifli.** Ticari üründe kullanmak alıcıya hukuki risk devreder. |
| SoccerNet | NDA + yalnız araştırma; ticari yasak |
| Kaggle DFL, Roboflow `sports` | DFL yarışma lisansı |
| ultralytics (YOLOv8/11) | **AGPL-3.0** — ticari üründe kaynak açma zorunluluğu doğurur |

## Token gerektirenler (kullanıcı sağlamalı)

- **SoccerTrack v2** — CC BY 4.0, sabit panoramik 4K + bbox etiketleri.
  `huggingface.co/datasets/atomscott/soccertrack-v2`, gated: HF hesabı +
  `HF_TOKEN` gerekli. Listeleme anonim çalışır, indirme 401 verir.
  **Not:** sabit kamera — TV yayını değil.

## İndirme

Veri dosyaları repoda tutulmaz (`.gitignore`). İndirme komutları:

- SkillCorner → `scripts/validate_passes.py` docstring
- CC BY video → `data/tracking/videos/` (Commons doğrudan indirme)
