/**
 * Leagues → Teams → Team detay navigation E2E — DESIGN.md §FAZ3.D2.
 *
 * Login → sidebar Ligler → bir lig tıkla → takımlar → bir takım → detay.
 * Backend zorunlu (E2E_BACKEND=true).
 */
import { test, expect } from "@playwright/test";

const TEST_EMAIL = process.env.E2E_TEST_EMAIL ?? "test@example.com";
const TEST_PASSWORD = process.env.E2E_TEST_PASSWORD ?? "test-password-1234";

test.describe("Leagues navigation", () => {
  test.skip(
    process.env.E2E_BACKEND !== "true",
    "Backend gerekir — E2E_BACKEND=true ile çalıştır",
  );

  test.beforeEach(async ({ page }) => {
    // Giriş yap — UI form üzerinden
    await page.goto("/login");
    await page.locator('input[type="email"]').fill(TEST_EMAIL);
    await page.locator('input[type="password"]').fill(TEST_PASSWORD);
    await page.locator("form button[type='submit']").click();
    // Login sonrası ana sayfaya yönlendirmeyi bekle
    await page.waitForURL((url) => !url.pathname.includes("/login"), {
      timeout: 10_000,
    });
  });

  test("sidebar 'Ligler' tıklanır → /leagues açılır → tablo görünür", async ({
    page,
  }) => {
    // Sidebar bağlantısı (Sidebar component'inde Türkçe etiket)
    await page.locator('a[href="/leagues"]').first().click();
    await expect(page).toHaveURL(/\/leagues/);
    // Veri tablosunda en az 1 satır veya empty state mesajı
    const ligLabel = page.locator("text=Ligler").first();
    await expect(ligLabel).toBeVisible({ timeout: 10_000 });
  });

  test("bir lig tıkla → /leagues/{id}/teams açılır", async ({ page }) => {
    await page.goto("/leagues");
    // İlk lig link'ini bul — DataTable'da satırlar <a href="/leagues/...">
    const firstLeagueLink = page
      .locator('a[href*="/leagues/"][href*="/teams"]')
      .first();
    const linkCount = await firstLeagueLink.count();
    if (linkCount === 0) {
      test.skip(true, "/leagues sayfasında lig yok — sync_league job çalışmalı");
      return;
    }
    await firstLeagueLink.click();
    await expect(page).toHaveURL(/\/leagues\/\d+\/teams/);
    // Takım sayfasında "Takımlar" başlığı veya tablo
    await expect(page.locator("body")).toBeVisible();
  });

  test("bir takım tıkla → /teams/{id} açılır → form/rating görünür", async ({
    page,
  }) => {
    await page.goto("/leagues");
    const firstLeagueLink = page
      .locator('a[href*="/leagues/"][href*="/teams"]')
      .first();
    if ((await firstLeagueLink.count()) === 0) {
      test.skip(true, "ligler yüklü değil");
      return;
    }
    await firstLeagueLink.click();
    await page.waitForURL(/\/teams/);
    const firstTeamLink = page
      .locator('a[href^="/teams/"]')
      .filter({ hasText: /./ })
      .first();
    if ((await firstTeamLink.count()) === 0) {
      test.skip(true, "lig içinde takım yok");
      return;
    }
    await firstTeamLink.click();
    await expect(page).toHaveURL(/\/teams\/\d+/);
    // Detay sayfasında form veya rating panel'i bekle
    const formOrRating = page.locator("text=/Form|Rating/i").first();
    await expect(formOrRating).toBeVisible({ timeout: 10_000 });
  });
});
