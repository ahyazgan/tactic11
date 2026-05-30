/**
 * Live WebSocket sayfası E2E — DESIGN.md §FAZ3.D4.
 *
 * Login → /matches/{id}/live?... → status badge "open" + snapshot history
 * counter ≥ 2 (interval_seconds=5 ile 15 sn içinde 2-3 snapshot beklenir).
 *
 * Server disconnect/restart simulasyonu yapılamadığı için reconnect testi
 * burada değil — manuel doğrulanmalı (DevTools'ta WS kapat).
 */
import { test, expect } from "@playwright/test";

const TEST_EMAIL = process.env.E2E_TEST_EMAIL ?? "test@example.com";
const TEST_PASSWORD = process.env.E2E_TEST_PASSWORD ?? "test-password-1234";
const TEST_MATCH_ID = process.env.E2E_TEST_MATCH_ID ?? "16029";
const TEST_TEAM_ID = process.env.E2E_TEST_TEAM_ID ?? "217";

test.describe("Live WebSocket", () => {
  test.skip(
    process.env.E2E_BACKEND !== "true",
    "Backend + WebSocket gerekir — E2E_BACKEND=true ile çalıştır",
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

  test("live sayfası 15 sn içinde status='open' ve ≥2 snapshot alır", async ({
    page,
  }) => {
    const url =
      `/matches/${TEST_MATCH_ID}/live` +
      `?my_team_id=${TEST_TEAM_ID}&interval_seconds=5&max_minute=10`;
    await page.goto(url);

    // Status badge "open" (Faz 3 B1: 4-state)
    const openBadge = page
      .locator("text=/open/i")
      .or(page.locator('[data-testid="ws-status-open"]'))
      .first();
    await expect(openBadge).toBeVisible({ timeout: 15_000 });

    // Snapshot history counter ≥ 2 — sayfada "history" / "snapshot N" gösteren
    // bir element olmalı. Pattern: "2/X snapshot" veya "history: N"
    // Esnek selector: sayısal değer içeren history rozet
    await page.waitForTimeout(15_000);
    const counterCandidates = [
      page.locator('[data-testid="snapshot-count"]'),
      page.locator("text=/snapshot.*\\d/i"),
      page.locator("text=/history.*\\d/i"),
    ];
    let counterValue = 0;
    for (const candidate of counterCandidates) {
      if ((await candidate.count()) > 0) {
        const text = (await candidate.first().textContent()) ?? "";
        const match = text.match(/\d+/);
        if (match) {
          counterValue = Math.max(counterValue, parseInt(match[0], 10));
        }
      }
    }
    expect(counterValue).toBeGreaterThanOrEqual(2);
  });
});
