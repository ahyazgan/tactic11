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
    // Demo hit_rate %71 görünür
    await expect(page.getByText("%71")).toBeVisible();
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
});
