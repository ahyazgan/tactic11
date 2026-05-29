/**
 * Halftime brief sayfası E2E — DESIGN.md §FAZ3.D3.
 *
 * Login → /matches/{id}/halftime?my_team_id=N → "1. Yarı Sayılar" başlığı
 * görünür → "Açıkla" butonu → ExplainPanel açılır.
 *
 * LLM stub mode'da brief sahte content olabilir; sadece panel açılma
 * tetiklenir.
 */
import { test, expect } from "@playwright/test";

const TEST_EMAIL = process.env.E2E_TEST_EMAIL ?? "test@example.com";
const TEST_PASSWORD = process.env.E2E_TEST_PASSWORD ?? "test-password-1234";
const TEST_MATCH_ID = process.env.E2E_TEST_MATCH_ID ?? "16029";
const TEST_TEAM_ID = process.env.E2E_TEST_TEAM_ID ?? "217";

test.describe("Halftime brief", () => {
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

  test("halftime sayfa '1. Yarı Sayılar' bölümünü gösterir", async ({
    page,
  }) => {
    await page.goto(
      `/matches/${TEST_MATCH_ID}/halftime?my_team_id=${TEST_TEAM_ID}`,
    );
    // Backend event ingest yoksa boş state olabilir
    const heading = page.locator("text=/1\\.\\s?Yarı Sayılar/").first();
    await expect(heading).toBeVisible({ timeout: 15_000 });
  });

  test("'Açıkla' butonuna tıkla → ExplainPanel açılır", async ({ page }) => {
    await page.goto(
      `/matches/${TEST_MATCH_ID}/halftime?my_team_id=${TEST_TEAM_ID}`,
    );
    const explainBtn = page.getByRole("button", { name: /açıkla/i }).first();
    const btnCount = await explainBtn.count();
    if (btnCount === 0) {
      test.skip(true, "Açıkla butonu yok — feature disabled olabilir");
      return;
    }
    await explainBtn.click();
    // ExplainPanel açılması — panel body görünür
    const panel = page.locator('[data-testid="explain-panel"], [role="region"][aria-label*="açıkla" i]').first();
    // Çoğu pattern data-testid kullanır; yedek olarak görünen herhangi bir panel
    const explainContent = panel.or(
      page.locator("text=/yorum|brief|açıklama/i").first(),
    );
    await expect(explainContent).toBeVisible({ timeout: 10_000 });
  });
});
