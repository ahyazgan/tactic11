# agents/

Otomasyon katmanı. Bir ajan, engine'leri ve isteğe bağlı olarak `ai/` yorumunu kullanıp
bir konu hakkında yapılandırılmış çıktı (`AgentResult`) üretir.

**Çalışma biçimi (`base.py`):**
1. Çağıran `agent.run(session, context)` çağırır.
2. Ajan engine'leri kullanır, gerekirse yorum ister.
3. `AgentResult` döner; kalıcı yazmayı çağıran yapar (`store.py`, `save_agent_output`).
4. Aynı (ajan, sürüm, konu) yeniden çalışırsa mevcut satır güncellenir.

Ajan kendisi veritabanına yazmaz. Engine'den farkı: yoruma gidebilir, kota ve önbellek
yan etkisi doğurabilir.

**Ajanlar:**

| Zaman | Ajanlar |
|---|---|
| Maç öncesi | `pre_match_report`, `opponent_scout`, `game_plan`, `lineup_recommendation`, `tactical_adjustment`, `training_plan`, `mega_match` |
| Maç içi | `live_decision_digest`, `halftime_analysis`, `substitution_advice` |
| Maç sonrası | `post_match_report`, `player_feedback`, `media_brief` |
| Dönemsel | `weekly_digest`, `scout_watchlist_digest`, `injury_load` |

**Bağımlılık yönü:** `agents/` → `ai/` → `engine/`. Tersi yok.

**Sınır:** ajan çıktısının kalitesi altındaki engine'in kalitesiyle sınırlıdır; ajan yeni
kanıt üretmez. Karar önerilerinin isabeti ölçülmüş değildir (bkz. `engine/decision_uplift`).
