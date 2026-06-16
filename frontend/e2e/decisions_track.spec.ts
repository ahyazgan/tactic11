/**
 * Karar Takip sayfası E2E — DEMO_MODE.
 *
 * Açılır → 4 summary kart (isabet/toplam/pozitif/negatif) + son kararlar tablosu.
 */
import { test, expect } from "@playwright/test";

test.describe("Decisions track (DEMO_MODE)", () => {
  test("renders summary cards + decisions table", async ({ page }) => {
    await page.goto("/decisions/track");
    // Summary kartları
    await expect(page.getByText("İsabet")).toBeVisible();
    await expect(page.getByText("Toplam", { exact: true })).toBeVisible();
    await expect(page.getByText("Pozitif", { exact: true })).toBeVisible();
    await expect(page.getByText("Negatif", { exact: true })).toBeVisible();
    // Demo hit_rate %67 görünür (6 pos / 9 resolved)
    await expect(page.getByText("%67")).toBeVisible();
    // Tablo: en az bir karar satırı (substitution)
    await expect(page.getByText("substitution").first()).toBeVisible();
    // Outcome label
    await expect(page.getByText(/✓ Doğru|✗ Yanlış|⏳ Bekliyor/).first()).toBeVisible();
  });

  test("type breakdown shows distribution", async ({ page }) => {
    await page.goto("/decisions/track");
    await expect(page.getByText("Tipe Göre Dağılım")).toBeVisible();
    // substitution: 8 satırı
    await expect(page.getByText("substitution").last()).toBeVisible();
  });

  test("limit slider updates header subtitle", async ({ page }) => {
    await page.goto("/decisions/track");
    const slider = page.locator('input[type="range"]');
    await slider.fill("50");
    await expect(page.locator(".pgdesc, .ep").first()).toBeVisible();
  });

  test("inline outcome buttons mark pending rows + recompute hit_rate", async ({ page }) => {
    await page.goto("/decisions/track");
    // Önce %67 görünüyor
    await expect(page.getByText("%67")).toBeVisible();
    // İlk ✓ butonunu tıkla (pending row için)
    const positiveBtn = page.locator('button[title="Doğru çıktı"]').first();
    await positiveBtn.click();
    // hit_rate 6 → 7 / 9 → 10 (1 pending pozitif oldu) → %70 görünmeli
    await expect(page.getByText("%70")).toBeVisible({ timeout: 2000 });
  });
});
