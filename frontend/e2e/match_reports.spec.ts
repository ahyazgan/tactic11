import { expect, test } from "@playwright/test";
import { spawnSync } from "node:child_process";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { statSync, writeFileSync } from "node:fs";

test("rapor alanı giriş olmadan gerçek veri istemez", async ({ page }) => {
  const privateRequests: string[] = [];
  page.on("request", request => { if (request.url().includes("/api/match-reports")) privateRequests.push(request.url()); });
  await page.goto("/match-reports");
  await expect(page.getByRole("heading", { name: "Kulübünüzün raporlarına giriş yapın" })).toBeVisible();
  await expect(page.getByLabel("E-posta", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Giriş yap", exact: true })).toBeVisible();
  expect(privateRequests).toEqual([]);
});

test("kaydetme çakışması analistin yazdığı notu korur", async ({ page }) => {
  const report = {
    id: "11111111-1111-4111-8111-111111111111", video_id: "22222222-2222-4222-8222-222222222222",
    title: "U17 raporu", version: 2, reviewed_at: "2026-10-10T12:00:00Z", reviewed_by: "coach",
    document: { club: "Kulüp", opponent: "Rakip", match_date: null, scope: "selected_segments", summary: "Kaydedilmiş özet",
      strengths: "", training_focus: ["Alan paylaşımı"], findings: [] },
  };
  await page.addInitScript(() => localStorage.setItem("manager2_access_token", "ui-test-token"));
  await page.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me") return route.fulfill({ json: { email: "coach@test", tenant_id: "club", role: "coach" } });
    if (path === "/api/match-reports" && route.request().method() === "POST") return route.fulfill({ status: 201, json: {
      ...report, ...route.request().postDataJSON(), id: "33333333-3333-4333-8333-333333333333", version: 1, reviewed_at: null,
    } });
    if (path === "/api/match-reports") return route.fulfill({ json: [report] });
    if (path === "/api/match-reports/videos") return route.fulfill({ json: [{ id: report.video_id, filename: "source.mp4", duration_seconds: 30, size_bytes: 100 }] });
    if (path.endsWith("/exports")) return route.fulfill({ json: [] });
    if (path.endsWith("/playback")) return route.fulfill({ status: 503, json: { detail: "Testte video servisi kapalı." } });
    if (route.request().method() === "PUT") return route.fulfill({ status: 409, json: {
      detail: "Rapor başka bir oturumda değişti. Yeniden yükleyin; notlarınızı koruyun.",
      error: { code: "conflict", message: "Rapor başka bir oturumda değişti.", request_id: "a".repeat(150) },
    } });
    return route.fulfill({ json: [] });
  });
  await page.goto("/match-reports");
  await page.getByRole("button", { name: /U17 raporu/ }).click();
  await page.getByLabel("Maç değerlendirmesi", { exact: true }).fill("Kaybolmaması gereken yeni analist notu");
  await expect(page.getByRole("button", { name: "PDF indir", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "İncelemeyi onayla" })).toHaveCount(0);
  await page.getByRole("button", { name: "Değişiklikleri kaydet" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "başka bir oturumda" })).toBeVisible();
  await expect(page.getByLabel("Maç değerlendirmesi", { exact: true })).toHaveValue("Kaybolmaması gereken yeni analist notu");
  await expect(page.getByRole("button", { name: "PDF indir", exact: true })).toBeDisabled();
  page.once("dialog", dialog => dialog.accept());
  await page.reload();
  await expect(page.getByLabel("Maç değerlendirmesi", { exact: true })).toHaveValue("Kaybolmaması gereken yeni analist notu");
  await expect(page.getByRole("button", { name: "Değişiklikleri kaydet" })).toBeEnabled();
  await page.getByRole("button", { name: "Değişiklikleri kaydet" }).click();
  await page.getByRole("button", { name: "Notlarımı ayrı rapora kaydet" }).click();
  await expect(page.getByRole("heading", { name: "U17 raporu (kopya)", exact: true })).toBeVisible();
  await expect(page.getByLabel("Maç değerlendirmesi", { exact: true })).toHaveValue("Kaybolmaması gereken yeni analist notu");
  await expect(page.getByRole("button", { name: "PDF indir", exact: true })).toBeDisabled();
});

for (const differentAccount of [false, true]) {
  test(`oturum yenileme: ${differentAccount ? "başka hesaba eski notları gösterme" : "aynı hesabın notlarını koru"}`, async ({ page }) => {
    const report = {
      id: "11111111-1111-4111-8111-111111111111", video_id: "22222222-2222-4222-8222-222222222222",
      title: "Korunacak taslak", version: 1, reviewed_at: null, reviewed_by: null,
      document: { club: "Kulüp", opponent: "Rakip", match_date: null, scope: "selected_segments", summary: "",
        strengths: "", training_focus: [], findings: [] },
    };
    let renewed = false;
    await page.addInitScript(() => localStorage.setItem("manager2_access_token", "expired-test-token"));
    await page.route("**/api/**", async route => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/auth/login") {
        renewed = true;
        return route.fulfill({ json: { access_token: "renewed-test-token", refresh_token: "test-refresh" } });
      }
      if (path === "/api/auth/me") return route.fulfill({ json: {
        email: renewed && differentAccount ? "new@beta.test" : "coach@alpha.test",
        tenant_id: renewed && differentAccount ? "beta" : "alpha", role: "coach",
      } });
      if (path === "/api/match-reports") return route.fulfill({ json: renewed && differentAccount ? [] : [report] });
      if (path.endsWith("/playback")) return route.fulfill({ status: 503, json: { detail: "Video testte kapalı" } });
      if (route.request().method() === "PUT") return route.fulfill({ status: 401, json: { detail: "expired" } });
      return route.fulfill({ json: [] });
    });
    await page.goto("/match-reports");
    await page.getByRole("button", { name: /Korunacak taslak/ }).click();
    await page.getByLabel("Maç değerlendirmesi", { exact: true }).fill("Kaybolmaması gereken özel not");
    await page.getByRole("button", { name: "Değişiklikleri kaydet" }).click();
    await expect(page.getByText(/Kaydetmediğiniz notlar bu sekmede korunuyor/)).toBeVisible();
    await page.getByLabel("E-posta", { exact: true }).fill(differentAccount ? "new@beta.test" : "coach@alpha.test");
    await page.getByLabel("Şifre", { exact: true }).fill("test-only");
    await page.getByRole("button", { name: "Giriş yap", exact: true }).click();
    if (differentAccount) {
      await expect(page.getByRole("heading", { name: "Görüntüden uygulanabilir öneriye" })).toBeVisible();
      await expect(page.getByLabel("Maç değerlendirmesi", { exact: true })).toHaveCount(0);
    } else {
      await expect(page.getByLabel("Maç değerlendirmesi", { exact: true })).toHaveValue("Kaybolmaması gereken özel not");
      await expect(page.getByRole("button", { name: "Değişiklikleri kaydet" })).toBeEnabled();
    }
  });
}

test("PWA özel raporları çevrimdışı önbellekten sunmaz", async ({ page, context }) => {
  test.skip(process.env.E2E_REVIEW_BACKEND !== "true", "Isolated API required");
  const response = await page.request.post("/api/auth/login", { data: {
    email: "analyst@review-pilot.test", password: "review-local-test-only", tenant_slug: "review-pilot",
  } });
  expect(response.ok()).toBeTruthy();
  const { access_token: token } = await response.json();
  await page.goto("/match-reports");
  await page.evaluate(async () => {
    const old = await caches.open("tactic11-v3");
    await old.put("/api/match-reports", new Response("old private report"));
    await navigator.serviceWorker.register("/sw.js");
    await navigator.serviceWorker.ready;
  });
  await expect.poll(() => page.evaluate(() => !!navigator.serviceWorker.controller)).toBeTruthy();
  expect(await page.evaluate(() => caches.has("tactic11-v3"))).toBeFalsy();
  const status = await page.evaluate(async (access: string) =>
    (await fetch("/api/match-reports", { headers: { Authorization: `Bearer ${access}` } })).status, token);
  expect(status).toBe(200);
  expect(await page.evaluate(async () => !!await caches.match("/api/match-reports"))).toBeFalsy();
  await context.setOffline(true);
  const offline = await page.evaluate(async (access: string) => {
    try { return (await fetch("/api/match-reports", { headers: { Authorization: `Bearer ${access}` } })).status; }
    catch { return "offline"; }
  }, token);
  expect(offline).toBe("offline");
});

test("geciken refresh yanıtı yeni giriş yapılan hesabın tokenlarını değiştiremez", async ({ page }) => {
  const report = {
    id: "11111111-1111-4111-8111-111111111111", video_id: "22222222-2222-4222-8222-222222222222",
    title: "Oturum yarışı", version: 1, reviewed_at: null, reviewed_by: null,
    document: { club: "Kulüp", opponent: "Rakip", match_date: null, scope: "selected_segments", summary: "",
      strengths: "", training_focus: [], findings: [] },
  };
  let release!: () => void, refreshing = false;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.addInitScript(() => {
    localStorage.setItem("manager2_access_token", "old-access");
    localStorage.setItem("manager2_refresh_token", "old-refresh");
  });
  await page.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me") return route.fulfill({ json: { email: "coach@test", tenant_id: "club", role: "coach" } });
    if (path === "/api/auth/refresh") {
      refreshing = true; await gate;
      return route.fulfill({ json: { access_token: "obsolete-access", refresh_token: "obsolete-refresh" } });
    }
    if (path === "/api/match-reports") return route.fulfill({ json: [report] });
    if (route.request().method() === "PUT") return route.fulfill({ status: 401, json: { detail: "expired" } });
    if (path.endsWith("/playback")) return route.fulfill({ status: 503, json: { detail: "Test videosu kapalı" } });
    return route.fulfill({ json: [] });
  });
  await page.goto("/match-reports");
  await page.getByRole("button", { name: /Oturum yarışı/ }).click();
  await page.getByLabel("Maç değerlendirmesi", { exact: true }).fill("Önceki hesap notu");
  await page.getByRole("button", { name: "Değişiklikleri kaydet" }).click();
  await expect.poll(() => refreshing).toBe(true);
  await page.evaluate(() => {
    localStorage.setItem("manager2_access_token", "new-account-access");
    localStorage.setItem("manager2_refresh_token", "new-account-refresh");
  });
  release();
  await expect(page.getByRole("alert").filter({ hasText: "Oturum açılamadı" })).toBeVisible();
  expect(await page.evaluate(() => [localStorage.getItem("manager2_access_token"), localStorage.getItem("manager2_refresh_token")]))
    .toEqual(["new-account-access", "new-account-refresh"]);
});

test("gerçek API: video yükle, pozisyonu onayla, PDF ve klip paketini indir", async ({ page, context }, testInfo) => {
  test.skip(process.env.E2E_REVIEW_BACKEND !== "true", "Isolated review API and source MP4 required");
  const longMatch = process.env.E2E_REVIEW_LONG_MATCH === "true";
  test.setTimeout(longMatch ? 300_000 : 120_000);
  const timings: Record<string, number> = {};
  const title = `Teknik teslim doğrulaması ${Date.now()}`;
  await page.goto("/match-reports");
  await page.getByLabel("E-posta", { exact: true }).fill("analyst@review-pilot.test");
  await page.getByLabel("Şifre", { exact: true }).fill("review-local-test-only");
  await page.getByLabel("Kulüp kodu (varsa)").fill("review-pilot");
  await page.getByRole("button", { name: "Giriş yap", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Yeni rapor", exact: true })).toBeVisible();
  const uploadStarted = Date.now();
  await page.getByLabel("MP4 video yükle").setInputFiles(process.env.E2E_REVIEW_VIDEO!);
  await expect(page.getByRole("status")).toContainText("Video kaydedildi", { timeout: longMatch ? 180_000 : 30_000 });
  timings.upload_ms = Date.now() - uploadStarted;
  await page.getByLabel("Rapor başlığı", { exact: true }).fill(title);
  await page.getByRole("button", { name: "Rapor oluştur", exact: true }).click();
  await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible();
  await expect.poll(() => page.locator("video").evaluate((video: HTMLVideoElement) => video.readyState), { timeout: 20_000 }).toBeGreaterThanOrEqual(1);
  await page.locator("video").evaluate((video: HTMLVideoElement) => video.play());
  await expect.poll(() => page.locator("video").evaluate((video: HTMLVideoElement) => video.currentTime)).toBeGreaterThan(0);
  await page.locator("video").evaluate((video: HTMLVideoElement) => video.pause());
  if (longMatch) {
    const duration = await page.locator("video").evaluate((video: HTMLVideoElement) => video.duration);
    expect(duration).toBeCloseTo(5400, 0);
    for (const at of [2700, 5390]) {
      const started = Date.now();
      await page.locator("video").evaluate((video: HTMLVideoElement, time) => { video.currentTime = time; }, at);
      await expect.poll(() => page.locator("video").evaluate((video: HTMLVideoElement) => !video.seeking && video.readyState >= 2), { timeout: 30_000 }).toBe(true);
      await page.locator("video").evaluate((video: HTMLVideoElement) => video.play());
      await expect.poll(() => page.locator("video").evaluate((video: HTMLVideoElement) => video.currentTime)).toBeGreaterThan(at);
      await page.locator("video").evaluate((video: HTMLVideoElement) => video.pause());
      timings[`seek_and_play_${at}_ms`] = Date.now() - started;
    }
  }
  await page.getByLabel("Kulüp", { exact: true }).fill("Teknik deneme kulübü");
  await page.getByLabel("Rakip", { exact: true }).fill("Kaynak görüntüdeki rakip");
  await page.getByLabel("Maç değerlendirmesi", { exact: true }).fill("Teknik doğrulama raporu. Bir futbol analistinin uzman değerlendirmesi değildir.");
  await page.getByLabel("Antrenman odağı 1", { exact: true }).fill("Örnek alan; gerçek antrenör değerlendirmesiyle doldurulmalı.");
  const intervals = longMatch ? [[2699, 2702], [5395, 5398]] : [[1, 4], [5, 8]];
  for (const [index, [start, end]] of intervals.entries()) {
    if (index === 0) {
      await page.getByRole("region", { name: "Video analiz çalışma alanı" }).focus();
      await page.keyboard.press("n");
    } else await page.getByRole("button", { name: "Pozisyon ekle", exact: true }).click();
    await page.getByLabel("Başlangıç (saniye)", { exact: true }).fill(String(start));
    await page.getByLabel("Bitiş (saniye)", { exact: true }).fill(String(end));
    await page.getByLabel("Pozisyon başlığı", { exact: true }).fill(`Teknik kesim ${start}–${end}`);
    await page.getByLabel("Gözlem", { exact: true }).fill("Bu kayıt klip, metin ve zaman aralığı eşleşmesini doğrular.");
    await page.getByLabel("Çalışma önerisi", { exact: true }).fill("Taktik öneri için antrenör incelemesi gerekir.");
    await page.getByLabel("Oyuncu (isteğe bağlı)").fill("Teknik deneme oyuncusu");
    await page.getByLabel("Sonraki maçta neye bakacağız?", { exact: true }).fill("Sonraki kayıtta aynı zaman aralığını kaynak görüntüyle karşılaştır.");
    if (index === 0) {
      const frameTime = start + 1;
      await page.locator("video").evaluate((video: HTMLVideoElement, time) => { video.currentTime = time; }, frameTime);
      await expect.poll(() => page.locator("video").evaluate((video: HTMLVideoElement) => video.currentTime)).toBe(frameTime);
      await page.getByRole("region", { name: "Video analiz çalışma alanı" }).focus();
      await page.keyboard.press("i");
      await expect(page.getByLabel("Başlangıç (saniye)", { exact: true })).toHaveValue(String(frameTime));
      await page.getByLabel("Başlangıç (saniye)", { exact: true }).fill(String(start));
      await page.getByRole("button", { name: "Bu kareye çizim yap" }).click();
      const canvas = page.getByTestId("drawing-canvas").locator("canvas");
      await expect(canvas).toBeVisible();
      await canvas.scrollIntoViewIfNeeded();
      const bounds = (await canvas.boundingBox())!;
      await page.mouse.move(bounds.x + bounds.width * .2, bounds.y + bounds.height * .3);
      await page.mouse.down();
      await page.mouse.move(bounds.x + bounds.width * .7, bounds.y + bounds.height * .6, { steps: 5 });
      await page.mouse.up();
      await expect(page.getByText(/1\/20 işaret/)).toBeVisible();
    }
    await expect(page.getByRole("button", { name: "Değişiklikleri kaydet" })).toBeDisabled();
    await page.getByRole("button", { name: "Rapora ekle", exact: true }).click();
  }
  await page.getByRole("button", { name: "Değişiklikleri kaydet" }).click();
  await expect(page.getByRole("status")).toContainText("Rapor kaydedildi");
  await page.getByRole("checkbox", { name: "Videodaki pozisyonları, oyuncu adlarını ve yorumları kontrol ettim." }).check();
  await page.getByRole("button", { name: "İncelemeyi onayla" }).click();
  await expect(page.getByRole("status")).toContainText("İnceleme kaydedildi");
  const followUps = page.locator("details").filter({ hasText: "Önceki raporlardan gelişim takibi" });
  await followUps.locator("summary").click();
  await followUps.getByLabel("Oyuncu veya takip konusu ara").fill(title);
  await expect(followUps.getByRole("article")).toHaveCount(2);
  await expect(followUps.getByText("Sonraki kayıtta aynı zaman aralığını kaynak görüntüyle karşılaştır.", { exact: false })).toHaveCount(2);
  const pdfStarted = Date.now();
  const pdfDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "PDF indir", exact: true }).click();
  await (await pdfDownload).saveAs(testInfo.outputPath("report.pdf"));
  timings.pdf_ms = Date.now() - pdfStarted;
  const exportStarted = Date.now();
  await page.getByRole("button", { name: "Klipli teslim paketi hazırla" }).click();
  await expect(page.getByRole("button", { name: "ZIP indir", exact: true })).toBeVisible({ timeout: 60_000 });
  const zipDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "ZIP indir", exact: true }).click();
  const delivery = await zipDownload;
  expect(delivery.url()).toContain("/review-media/exports/");
  expect(delivery.suggestedFilename()).toMatch(/^match-report-v\d+\.zip$/);
  await delivery.saveAs(testInfo.outputPath("delivery.zip"));
  timings.export_ms = Date.now() - exportStarted;
  await page.screenshot({ path: testInfo.outputPath("report-screen.png"), fullPage: true });
  const extracted = testInfo.outputPath("delivery");
  const python = process.env.E2E_PYTHON ?? (process.platform === "win32" ? "../venv/Scripts/python.exe" : "python");
  const extraction = spawnSync(python, ["-m", "zipfile", "-e", testInfo.outputPath("delivery.zip"), extracted], { encoding: "utf8" });
  expect(extraction.status, extraction.stderr).toBe(0);
  await context.setOffline(true);
  await page.goto(pathToFileURL(join(extracted, "index.html")).href);
  await expect(page.locator("video")).toHaveCount(2);
  await expect(page.getByRole("img", { name: "Analistin pozisyon çizimi" })).toBeVisible();
  expect(await page.getByRole("img", { name: "Analistin pozisyon çizimi" }).evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);
  await page.locator("video").first().evaluate((video: HTMLVideoElement) => video.play());
  await expect.poll(() => page.locator("video").first().evaluate((video: HTMLVideoElement) => video.currentTime)).toBeGreaterThan(0);
  await page.screenshot({ path: testInfo.outputPath("offline-delivery.png"), fullPage: true });
  await context.setOffline(false);
  await page.goto("/match-reports");
  await page.getByRole("button", { name: new RegExp(title) }).click();
  await expect(page.getByLabel("Maç değerlendirmesi", { exact: true })).toHaveValue(/Teknik doğrulama raporu/);
  await expect(page.getByRole("button", { name: "ZIP indir", exact: true })).toBeVisible();
  await page.getByRole("heading", { name: "Video ve pozisyonlar", exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath("video-review.png") });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("heading", { name: "Video ve pozisyonlar", exact: true }).scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  const mobileDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "PDF indir", exact: true }).click();
  await (await mobileDownload).cancel();
  await page.screenshot({ path: testInfo.outputPath("mobile-review.png") });
  writeFileSync(testInfo.outputPath("measurements.json"), JSON.stringify({
    long_match: longMatch, fixture_bytes: statSync(process.env.E2E_REVIEW_VIDEO!).size,
    intervals, timings, pdf_bytes: statSync(testInfo.outputPath("report.pdf")).size,
    zip_bytes: statSync(testInfo.outputPath("delivery.zip")).size,
  }, null, 2));
});
