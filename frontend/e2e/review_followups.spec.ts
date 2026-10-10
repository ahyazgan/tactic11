import { expect, test } from "@playwright/test";

test("gelişim takibi yalnız onaylı notları gösterir ve açık taslağı korur", async ({ page }) => {
  const reports = [1, 2, 3].map(number => ({
    id: `00000000-0000-4000-8000-00000000000${number}`,
    video_id: "22222222-2222-4222-8222-222222222222",
    title: `${number}. maç raporu`, version: 3,
    reviewed_at: number === 3 ? null : "2026-10-10T12:00:00Z", reviewed_by: "analyst",
    document: {
      club: "Kulüp", opponent: "Rakip", match_date: null, scope: "selected_segments",
      summary: "Kaydedilmiş maç özeti", strengths: "", training_focus: ["Pozisyon çalışması"],
      findings: [{
        id: `11111111-1111-4111-8111-11111111111${number}`, category: "player", start: 1, end: 4,
        title: number === 2 ? "Destek koşusu" : "Alan paylaşımı", player: "İrfan",
        observation: "Kaynak rapordaki gözlem", action: "Bir önceki çalışma önerisi",
        next_check: number === 3 ? "Onaysız not görünmemeli" : "Koşunun başlangıç zamanını kontrol et",
      }],
    },
  }));
  await page.addInitScript(() => localStorage.setItem("manager2_access_token", "followup-test-token"));
  await page.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me") return route.fulfill({ json: { email: "analyst@test", tenant_id: "club", role: "analyst" } });
    if (path === "/api/match-reports") return route.fulfill({ json: reports });
    if (path.endsWith("/playback")) return route.fulfill({ status: 503, json: { detail: "Testte oynatma kapalı" } });
    return route.fulfill({ json: [] });
  });
  await page.goto("/match-reports");
  const history = page.locator("details").filter({ hasText: "Önceki raporlardan gelişim takibi" });
  await history.locator("summary").click();
  await expect(history.getByRole("article")).toHaveCount(2);
  await expect(history.getByText("Onaysız not görünmemeli")).toHaveCount(0);
  await history.getByLabel("Oyuncu veya takip konusu ara").fill("İRFAN");
  await expect(history.getByRole("article")).toHaveCount(2);
  await history.getByLabel("Oyuncu veya takip konusu ara").fill("Destek");
  await expect(history.getByRole("article")).toHaveCount(1);
  await history.getByRole("button", { name: "Kaynak raporu aç" }).click();
  await expect(page.getByRole("heading", { name: "2. maç raporu", exact: true })).toBeVisible();
  await page.getByLabel("Maç değerlendirmesi", { exact: true }).fill("Kaybolmayacak yeni gözlem");
  await history.getByLabel("Oyuncu veya takip konusu ara").fill("Alan");
  await history.getByRole("button", { name: "Kaynak raporu aç" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Başka bir rapora geçmeden" })).toBeVisible();
  await expect(page.getByLabel("Maç değerlendirmesi", { exact: true })).toHaveValue("Kaybolmayacak yeni gözlem");
  await expect(page.getByRole("heading", { name: "2. maç raporu", exact: true })).toBeVisible();
});
