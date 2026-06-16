/**
 * Frontend smoke — sayfaların hata atmadan render olduğunu doğrular.
 * Backend olmadan static rotalar çalışır (login).
 * Backend ile entegre testler ayrı job'da koşar (E2E_BACKEND=true).
 */
import { test, expect } from "@playwright/test";

test.describe("Sayfa smoke render", () => {
  test("/login ana sayfaya yönlendirir (login kaldırıldı)", async ({ page }) => {
    // Login kaldırıldı: /login form göstermez, /'e yönlendirir.
    await page.goto("/login");
    await page.waitForURL((url) => !url.pathname.startsWith("/login"), {
      timeout: 10_000,
    });
    // / artık Genel Bakış konsolunu render eder (tam-ekran fixed; body değil
    // konsol içeriği kontrol edilir).
    await expect(page.locator("text=Genel Bakış").first()).toBeVisible({
      timeout: 10_000,
    });
  });

  test("/ home page render olur", async ({ page }) => {
    await page.goto("/");
    // Ana sayfa Genel Bakış konsoludur (kart launcher kaldırıldı).
    await expect(page.locator("text=Genel Bakış").first()).toBeVisible({
      timeout: 10_000,
    });
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
