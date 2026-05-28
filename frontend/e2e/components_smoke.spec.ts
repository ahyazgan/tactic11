/**
 * Frontend smoke — sayfaların hata atmadan render olduğunu doğrular.
 * Backend olmadan static rotalar çalışır (login).
 * Backend ile entegre testler ayrı job'da koşar (E2E_BACKEND=true).
 */
import { test, expect } from "@playwright/test";

test.describe("Sayfa smoke render", () => {
  test("/login render olur", async ({ page }) => {
    await page.goto("/login");
    await expect(page.locator("body")).toBeVisible();
    // Email input mevcut olmalı
    await expect(page.locator('input[type="email"]')).toBeVisible();
  });

  test("/ home page render olur", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("body")).toBeVisible();
    // Hızlı erişim başlığı
    await expect(page.locator("text=Hızlı erişim")).toBeVisible({ timeout: 10_000 });
  });
});

test.describe("Backend bağımlı", () => {
  test.skip(
    process.env.E2E_BACKEND !== "true",
    "Backend test gerektirir — E2E_BACKEND=true ile çalıştır",
  );

  test("/leagues backend ile yüklenir", async ({ page }) => {
    await page.goto("/leagues");
    // Tablo veya boş state mesajı görünmeli
    await expect(
      page.locator("text=Ligler").first(),
    ).toBeVisible({ timeout: 10_000 });
  });

  test("/admin viewer rolünde / 'e redirect", async ({ page }) => {
    // Viewer token enjekte (mock)
    await page.goto("/login");
    await page.evaluate(() => {
      localStorage.setItem("manager2_access_token", "viewer-token");
    });
    await page.goto("/admin");
    // /admin → /'e redirect (RequireRole guard)
    await page.waitForURL((url) => url.pathname !== "/admin", { timeout: 5_000 });
  });
});
