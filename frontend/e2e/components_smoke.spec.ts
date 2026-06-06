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
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
    page.on("console", (m) => {
      if (m.type() === "error") errors.push(`console: ${m.text()}`);
    });
    const resp = await page.goto("/");
    await expect(page.locator("body")).toBeVisible();
    // DIAGNOSTIC — neden "Hızlı erişim" görünmüyor?
    const visible = await page
      .locator("text=Hızlı erişim")
      .isVisible()
      .catch(() => false);
    if (!visible) {
      const url = page.url();
      const status = resp?.status();
      const bodyText = (await page.locator("body").innerText()).slice(0, 800);
      const html = (await page.content()).slice(0, 1500);
      throw new Error(
        `DIAG home: status=${status} url=${url}\n` +
          `ERRORS=${JSON.stringify(errors)}\n` +
          `BODYTEXT=${JSON.stringify(bodyText)}\n` +
          `HTML=${html}`,
      );
    }
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
