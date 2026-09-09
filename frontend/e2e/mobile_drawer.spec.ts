/**
 * Mobile sidebar drawer — hamburger → drawer açılır → nav link tıklanır →
 * drawer otomatik kapanır. ESC tuşu da kapatır.
 */
import { test, expect } from "@playwright/test";

test.describe("Mobile drawer (DEMO_MODE)", () => {
  // iPhone 14 Pro YATAY. Dikey telefonda (<768px + portrait) uygulama bilinçli
  // olarak "cihazınızı yatay çevirin" kaplaması gösterir (globals.css) — o
  // durumda çekmece zaten kullanılamaz. Çekmece UX'i tabletler ve yatay
  // telefonlar içindir; test de onu doğrulamalı.
  test.use({ viewport: { width: 844, height: 390 } });

  test("hamburger opens drawer, nav link reachable, click closes", async ({ page }) => {
    await page.goto("/decisions/live");
    // Hamburger button (.menu-btn) görünür (tabletten dar viewport)
    const menuBtn = page.getByRole("button", { name: /Menüyü aç/i });
    await expect(menuBtn).toBeVisible();
    await menuBtn.click();
    // Sidebar nav görünür hale gelir
    const navLink = page.getByRole("link", { name: /Maç-içi Karar/i }).first();
    await expect(navLink).toBeVisible();
    // Linke tık → drawer kapanır + sayfa değişir
    await navLink.click();
    await expect(page).toHaveURL(/\/decisions\/live/);
    // Drawer kapanmış (hamburger tekrar görünür, sidebar bağlamı dışında)
    await expect(page.getByRole("button", { name: /Menüyü aç/i })).toBeVisible();
  });

  test("ESC key closes drawer", async ({ page }) => {
    await page.goto("/decisions/live");
    await page.getByRole("button", { name: /Menüyü aç/i }).click();
    await expect(page.getByRole("button", { name: /Menüyü kapat/i })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("button", { name: /Menüyü aç/i })).toBeVisible();
  });

  test("backdrop click closes drawer", async ({ page }) => {
    await page.goto("/decisions/track");
    await page.getByRole("button", { name: /Menüyü aç/i }).click();
    // .nav-backdrop element'i overlay
    await page.locator(".nav-backdrop").click();
    await expect(page.getByRole("button", { name: /Menüyü aç/i })).toBeVisible();
  });
});
