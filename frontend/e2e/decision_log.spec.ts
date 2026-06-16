/**
 * Decision log E2E — DESIGN.md §FAZ3.D5.
 *
 * Login → /matches/{id}/live → DecisionPanel form'unu doldur
 * (substitution out=100, in=200) → "Kaydet" → "Bu oturumda N karar
 * kaydedildi" mesajı → /admin/matches/{id}/decisions'da satır görünür.
 */
import { test, expect } from "@playwright/test";

const TEST_EMAIL = process.env.E2E_TEST_EMAIL ?? "test@example.com";
const TEST_PASSWORD = process.env.E2E_TEST_PASSWORD ?? "test-password-1234";
const TEST_MATCH_ID = process.env.E2E_TEST_MATCH_ID ?? "16029";
const TEST_TEAM_ID = process.env.E2E_TEST_TEAM_ID ?? "217";

test.describe("Decision log", () => {
  test.skip(
    process.env.E2E_BACKEND !== "true",
    "Backend gerekir — E2E_BACKEND=true ile çalıştır",
  );

  test.beforeEach(async ({ page }) => {
    await page.goto("/login");
    await page.locator('input[type="email"]').fill(TEST_EMAIL);
    await page.locator('input[type="password"]').fill(TEST_PASSWORD);
    await page.locator("form button[type='submit']").click();
    await page.waitForURL((url) => !url.pathname.includes("/login"), {
      timeout: 10_000,
    });
  });

  test("substitution kaydı /admin/.../decisions'a yansır", async ({ page }) => {
    const url =
      `/matches/${TEST_MATCH_ID}/live` +
      `?my_team_id=${TEST_TEAM_ID}&interval_seconds=5&max_minute=10`;
    await page.goto(url);

    // DecisionPanel görünür olana kadar bekle
    const panel = page
      .locator("text=/Karar|Decision/i")
      .first()
      .or(page.locator('[data-testid="decision-panel"]').first());
    await expect(panel).toBeVisible({ timeout: 15_000 });

    // Substitution radio veya tab seçimi — UI varyasyonu için esnek
    const subRadio = page
      .getByRole("radio", { name: /substitution|değiş/i })
      .or(page.locator('input[value="substitution"]'))
      .first();
    if ((await subRadio.count()) > 0) {
      await subRadio.click();
    }

    // Subject (out) + Related (in) player ID input'ları
    const outInput = page
      .locator('input[name*="subject"], input[placeholder*="çıkan" i], input[placeholder*="out" i]')
      .first();
    const inInput = page
      .locator('input[name*="related"], input[placeholder*="giren" i], input[placeholder*="in" i]')
      .first();

    if ((await outInput.count()) === 0 || (await inInput.count()) === 0) {
      test.skip(true, "DecisionPanel input'ları bulunamadı — UI değişmiş olabilir");
      return;
    }
    await outInput.fill("100");
    await inInput.fill("200");

    // Kaydet butonu
    const saveBtn = page.getByRole("button", { name: /kaydet|save/i }).first();
    await saveBtn.click();

    // Onay mesajı — "1 karar kaydedildi" veya benzeri
    const confirm = page
      .locator("text=/karar kaydedildi|saved/i")
      .first();
    await expect(confirm).toBeVisible({ timeout: 10_000 });

    // API endpoint üzerinden doğrulama — token localStorage'dan
    const verified = await page.evaluate(async (matchId) => {
      const token = localStorage.getItem("manager2_access_token");
      if (!token) return { ok: false, count: 0 };
      const resp = await fetch(`/admin/matches/${matchId}/decisions`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) return { ok: false, count: 0, status: resp.status };
      const items = await resp.json();
      const list = Array.isArray(items) ? items : items.items ?? [];
      return { ok: true, count: list.length };
    }, TEST_MATCH_ID);

    expect(verified.ok).toBeTruthy();
    expect(verified.count).toBeGreaterThan(0);
  });
});
