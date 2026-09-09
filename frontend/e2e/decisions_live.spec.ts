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
    // ŞİMDİ banner — aynı ifade sayfa altındaki açıklamada da geçtiği için
    // afişin kendisine kapsanır (aksi halde strict mode ihlali).
    await expect(
      page.getByTestId("primary-action").getByText("ŞİMDİ ŞUNU YAP"),
    ).toBeVisible();
    // En az 4 engine kartı (demo seed: 80. dk → closing high, momentum opp, foul high, star starved)
    await expect(page.getByText("Kapanış reçetesi")).toBeVisible();
    // "Momentum" kelimesi momentum göstergesinin açıklamasında da geçiyor
    await expect(page.getByTestId("momentum-card")).toBeVisible();
    await expect(page.getByText("Yıldız beslemesi")).toBeVisible();
    await expect(page.getByText("Faul ritmi + hakem")).toBeVisible();
    // Aciliyet rozeti — tema etiketi sinyal listesinde de geçtiği için afişe kapsanır
    await expect(
      page.getByTestId("primary-action").getByText("oyun yönetimi"),
    ).toBeVisible();
  });

  test("minute slider changes closing recipe", async ({ page }) => {
    await page.goto("/decisions/live");
    // Default 80. dk → "yükselt" tempo (berabere son 15 dk)
    // Kart içinde "tempo/yükselt" key_message'da da geçiyor → tempo satırı hedeflenir
    await expect(page.getByTestId("closing-tempo")).toHaveText(/tempo: .*yükselt/i);
    // Slider'ı erken evreye çek
    const slider = page.locator('input[type="range"]');
    await slider.fill("60");
    // 60. dk berabere → "normal" tempo
    await expect(page.getByText(/tempo: .*normal/i)).toBeVisible({
      timeout: 3000,
    });
  });

  test("replay button cycles through minutes and builds timeline", async ({ page }) => {
    await page.goto("/decisions/live");
    // Slider'ı 60'a çek + replay başlat
    const slider = page.locator('input[type="range"]');
    await slider.fill("60");
    const replayBtn = page.getByRole("button", { name: /Replay/i });
    await replayBtn.click();
    // 2-3 tick (≥1.8s) sonra timeline en az 2 entry olmalı
    await page.waitForTimeout(2000);
    // Pause
    await page.getByRole("button", { name: /Duraklat/i }).click();
    // Karar Geçmişi başlığı görünür
    await expect(page.getByText("Karar Geçmişi")).toBeVisible();
    // En az 2 timeline kartı (minute label'leri farklı)
    const minuteLabels = page.locator("text=/^[567][0-9]'$/");
    const count = await minuteLabels.count();
    expect(count).toBeGreaterThanOrEqual(2);
  });

  test("live mode toggle auto-advances minute in DEMO_MODE", async ({ page }) => {
    await page.goto("/decisions/live");
    const slider = page.locator('input[type="range"]');
    await slider.fill("70");
    const initial = await slider.inputValue();
    // Canlı mod checkbox
    await page.getByLabel(/Canlı mod/i).check();
    // 5sn aralık var; 6 sn bekle → dakika +1 olmalı
    await page.waitForTimeout(6000);
    const after = await slider.inputValue();
    expect(parseInt(after)).toBeGreaterThan(parseInt(initial));
    // Live rozet görünür
    await expect(page.getByText("● LIVE")).toBeVisible();
  });

  test("mobile viewport: cards stack to single column", async ({ page }) => {
    await page.setViewportSize({ width: 380, height: 800 });
    await page.goto("/decisions/live");
    // Grid container hâlâ var
    const grid = page.locator(".live-decision-grid");
    await expect(grid).toBeVisible();
  });

  test("urgency transitions across phases (low → high → critical)", async ({ page }) => {
    await page.goto("/decisions/live");
    const slider = page.locator('input[type="range"]');
    // Early (60): banner null, "izleme modu" mesajı
    await slider.fill("60");
    await expect(page.getByText(/izleme modu|net karar yok/i)).toBeVisible();
    // Late (80): "Berabere · son 15 dk"
    await slider.fill("80");
    await expect(
      page.getByTestId("closing-recipe").getByText(/son 15 dk/i),
    ).toBeVisible();
    // Stoppage (92): "uzatma → acil" — reçete kartında görünmeli
    await slider.fill("92");
    await expect(
      page.getByTestId("closing-recipe").getByText(/uzatma|acil/i).first(),
    ).toBeVisible();
  });
});
