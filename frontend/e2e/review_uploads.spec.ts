import { expect, test } from "@playwright/test";

test("tus: bağlantı kesilince duraklat, yenile ve aynı dosyayı kaldığı yerden tamamla", async ({ page }) => {
  test.skip(process.env.E2E_REVIEW_BACKEND !== "true", "Isolated API and source required");
  test.setTimeout(120_000);
  let interrupt = true, creations = 0, sawFirst = false, refreshes = 0, unauthorized = false;
  const resumedOffsets: number[] = [];
  page.on("request", request => { if (request.url().endsWith("/api/auth/refresh")) refreshes++; });
  await page.route("**/api/match-reports/uploads**", async route => {
    const request = route.request();
    if (request.method() === "POST") creations++;
    if (request.method() === "PATCH") {
      const offset = Number(request.headers()["upload-offset"]);
      if (offset > 0 && interrupt) { sawFirst = true; return route.abort("internetdisconnected"); }
      if (!interrupt) {
        resumedOffsets.push(offset);
        if (!unauthorized) { unauthorized = true; return route.fulfill({ status: 401, json: { detail: "Oturum yenileme testi" } }); }
      }
    }
    return route.continue();
  });
  await page.goto("/match-reports");
  await page.getByLabel("E-posta", { exact: true }).fill("analyst@review-pilot.test");
  await page.getByLabel("Şifre", { exact: true }).fill("review-local-test-only");
  await page.getByLabel("Kulüp kodu (varsa)").fill("review-pilot");
  await page.getByRole("button", { name: "Giriş yap", exact: true }).click();
  await page.getByLabel("MP4 video yükle").setInputFiles(process.env.E2E_REVIEW_VIDEO!);
  await expect.poll(() => sawFirst).toBe(true);
  await page.getByRole("button", { name: "Duraklat", exact: true }).click();
  await expect(page.getByRole("button", { name: "Yüklemeye devam et" })).toBeVisible();
  const token = await page.evaluate(() => localStorage.getItem("manager2_access_token"));
  const response = await page.request.get("/api/match-reports/uploads", { headers: { Authorization: `Bearer ${token}` } });
  const pending = await response.json();
  expect(pending).toHaveLength(1);
  expect(pending[0].offset).toBe(2 * 1024 * 1024);
  await page.reload();
  await expect(page.getByText(/Yarım kalan yüklemeler/)).toBeVisible();
  interrupt = false;
  await page.getByLabel("MP4 video yükle").setInputFiles(process.env.E2E_REVIEW_VIDEO!);
  await expect(page.getByRole("status")).toContainText("Video kaydedildi", { timeout: 60_000 });
  expect(creations).toBe(1);
  expect(resumedOffsets[0]).toBe(pending[0].offset);
  expect(refreshes).toBe(1);
  await expect(page.getByLabel("Kaynak video")).not.toHaveValue("");
});
