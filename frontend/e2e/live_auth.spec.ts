import { test, expect } from "@playwright/test";

// This suite targets a NEXT_PUBLIC_DEMO_MODE=false build; demo CI stays unchanged.
test.describe("Gerçek API giriş akışı", () => {
  test.skip(process.env.E2E_LIVE_API !== "true", "E2E_LIVE_API=true ve gerçek veri modu derlemesi gerekir");

  test("401 klip yokmuş gibi gösterilmez; giriş bağlantısı sunulur", async ({ page }) => {
    await page.route("**/api/tracking/**", route => route.fulfill({status:401,json:{detail:"authentication required"}}));
    await page.goto("/video-tracking");
    await expect(page.getByRole("alert").filter({hasText:"Video işlemek için giriş"})).toBeVisible();
    await page.getByRole("link", {name:"Giriş yap",exact:true}).click();
    await expect(page.getByRole("heading", {name:"Manager’a giriş"})).toBeVisible();
  });

  test("hatalı parola formda kalır ve belirgin hata verir", async ({ page }) => {
    await page.route("**/api/auth/login", route => route.fulfill({status:401,json:{detail:"invalid credentials"}}));
    await page.goto("/login");
    await page.getByLabel("E-posta", {exact:true}).fill("analyst@example.test");
    await page.getByLabel("Parola", {exact:true}).fill("wrong-password");
    await page.getByRole("button", {name:"Giriş yap",exact:true}).click();
    await expect(page.getByRole("alert").filter({hasText:"Giriş yapılamadı"})).toBeVisible();
    expect(await page.evaluate(() => localStorage.getItem("manager2_access_token"))).toBeNull();
    await expect(page).toHaveURL(/\/login$/);
  });

  for (const next of ["/video-tracking", "https://example.org/elsewhere", "http://["]) {
    test(`başarılı giriş güvenli dönüş: ${next}`, async ({ page }) => {
      let body: Record<string, unknown> | undefined;
      await page.route("**/api/auth/login", route => {
        body = route.request().postDataJSON();
        return route.fulfill({json:{access_token:"test-access",refresh_token:"test-refresh"}});
      });
      // Observe the returned URL without letting the destination trigger API refresh.
      await page.route("**/*", async route => {
        const url = new URL(route.request().url());
        if (route.request().isNavigationRequest() && ["/", "/video-tracking"].includes(url.pathname)) {
          return route.fulfill({contentType:"text/html; charset=utf-8",body:"<h1>Oturum açıldı</h1>"});
        }
        await route.fallback();
      });
      await page.goto(`/login?next=${encodeURIComponent(next)}`);
      await page.getByLabel("E-posta", {exact:true}).fill("analyst@example.test");
      await page.getByLabel("Parola", {exact:true}).fill("example-password");
      await page.getByLabel("Kulüp kodu", {exact:false}).fill("club-test");
      await page.getByRole("button", {name:"Giriş yap",exact:true}).click();
      await expect(page.getByRole("heading", {name:"Oturum açıldı"})).toBeVisible();
      expect(new URL(page.url()).pathname).toBe(next === "/video-tracking" ? next : "/");
      expect(body).toEqual({email:"analyst@example.test",password:"example-password",tenant_slug:"club-test"});
      expect(await page.evaluate(() => localStorage.getItem("manager2_access_token"))).toBe("test-access");
      expect(await page.evaluate(() => localStorage.getItem("manager2_refresh_token"))).toBe("test-refresh");
    });
  }
});
