/**
 * Maç-içi karar sayfası E2E smoke — DEMO_MODE ile çalışır (backend gereksiz).
 *
 * Sayfa açılır → "ŞİMDİ ŞUNU YAP" başlığı görünür → 7 engine kartı render edilir
 * → dakika slider'ı değişince DOM güncellenir (closing_strategy reçetesi farklılaşır).
 */
import { test, expect } from "@playwright/test";

test.describe("Decisions live (DEMO_MODE)", () => {
  test("renders primary action banner + engine cards", async ({ page }) => {
    await page.goto("/decisions/live");
    // ŞİMDİ banner
    await expect(page.getByText("ŞİMDİ ŞUNU YAP")).toBeVisible();
    // En az 4 engine kartı (demo seed: 80. dk → closing high, momentum opp, foul high, star starved)
    await expect(page.getByText("Kapanış reçetesi")).toBeVisible();
    await expect(page.getByText("Momentum")).toBeVisible();
    await expect(page.getByText("Yıldız beslemesi")).toBeVisible();
    await expect(page.getByText("Faul ritmi + hakem")).toBeVisible();
    // Aciliyet rozet (yüksek/orta)
    await expect(page.getByText("oyun yönetimi")).toBeVisible();
  });

  test("minute slider changes closing recipe", async ({ page }) => {
    await page.goto("/decisions/live");
    // Default 80. dk → "yükselt" tempo (berabere son 15 dk)
    await expect(page.getByText(/tempo: .*yükselt/i)).toBeVisible();
    // Slider'ı erken evreye çek
    const slider = page.locator('input[type="range"]');
    await slider.fill("60");
    // 60. dk berabere → "normal" tempo
    await expect(page.getByText(/tempo: .*normal/i)).toBeVisible({
      timeout: 3000,
    });
  });
});
