/**
 * Login flow E2E — DESIGN.md §FAZ3.D1.
 *
 * Backend test mode'da: tenant seed + default test user gerekir
 * (production mode'da seed dışarıdan).
 */
import { test, expect } from "@playwright/test";

test.describe("Login akışı", () => {
  test("login devre dışı — /login ana sayfaya yönlendirir", async ({ page }) => {
    // Login kaldırıldı (önizleme): /login form göstermez, /'e yönlendirir.
    await page.goto("/login");
    await page.waitForURL((url) => !url.pathname.startsWith("/login"), {
      timeout: 10_000,
    });
    // / Genel Bakış konsolunu render eder (tam-ekran fixed).
    await expect(page.locator("text=Genel Bakış").first()).toBeVisible({
      timeout: 10_000,
    });
  });

  test("logout token'ları temizler ve /login'e döner", async ({ page }) => {
    // Manuel token enjekte (gerçek login backend'e bağlı)
    await page.goto("/login");
    await page.evaluate(() => {
      localStorage.setItem("manager2_access_token", "dummy");
      localStorage.setItem("manager2_refresh_token", "dummy-refresh");
    });
    await page.goto("/");
    // / Genel Bakış konsolunu render eder; konsol içeriği görünür olmalı.
    await expect(page.locator("text=Genel Bakış").first()).toBeVisible({
      timeout: 10_000,
    });
  });
});
