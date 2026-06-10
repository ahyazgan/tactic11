"use client";

/**
 * "Demo modunda bu ekran canlıdır" şeridi.
 *
 * Çoğu ekran DEMO_MODE'da mock veri gösterirken bu şeridi taşıyan ekranlar
 * (Bildirimler / Sözleşmeler / Kalibrasyon) demo modunda bile GERÇEK backend
 * API'sine gider. Kullanıcı "neden boş/hata görüyorum" demesin diye durumu
 * tek satırla açıklar. DEMO kapalıyken render edilmez (zaten her şey canlı).
 */

import { DEMO_MODE } from "@/lib/demo-mode";

export function DemoLiveBanner() {
  if (!DEMO_MODE) return null;
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 9, marginBottom: 14,
      padding: "8px 13px", borderRadius: 10,
      border: "1px solid var(--accent)", background: "var(--accent-lt)",
      fontSize: 12.5, color: "var(--ink)", lineHeight: 1.45,
    }}>
      <i className="ti ti-broadcast" style={{ fontSize: 16, color: "var(--accent)", flexShrink: 0 }} />
      <span>
        <b>Demo modunda bu ekran canlıdır</b> — veriler doğrudan sunucudan gelir.
        Backend bağlı değilse boş ya da hata görünmesi normaldir.
      </span>
    </div>
  );
}
