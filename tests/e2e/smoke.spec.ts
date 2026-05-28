import { test, expect } from "@playwright/test";

/**
 * Smoke tests — every public-without-auth surface that ships with the app.
 *
 * These do NOT call the backend. They verify:
 * - the SPA bundle loads
 * - the route tree resolves the home route
 * - the welcome tour is render-able
 * - 404 page is reachable
 *
 * Anything that needs `/api/*` requires real Databricks auth and lives
 * in a separate authenticated suite (out of scope for this smoke run).
 */

test.describe("Núclea Modeler — smoke", () => {
  test("home page renders the hero + navigation", async ({ page }) => {
    await page.goto("/");
    // Title is set by index.html / Vite define
    await expect(page).toHaveTitle(/N(ú|u)clea/);
    // Hero copy: avoid coupling to specific words — just check something rendered
    await expect(page.locator("main, [role='main']").first()).toBeVisible();
  });

  test("404 page shows the custom not-found component", async ({ page }) => {
    await page.goto("/this-route-does-not-exist-12345");
    await expect(page.getByText(/404/i)).toBeVisible();
    await expect(page.getByRole("link", { name: /Voltar ao início/i })).toBeVisible();
  });

  test("welcome tour opens on first visit and can be dismissed", async ({ page, context }) => {
    // Fresh storage state guarantees the tour fires.
    await context.clearCookies();
    await page.goto("/");
    // Tour appears after the boot delay (see welcome-tour.tsx: 800ms).
    const tourTitle = page.getByText(/Cadastre uma conexão/i);
    await expect(tourTitle).toBeVisible({ timeout: 5_000 });

    // Skip dismisses and persists the flag.
    await page.getByRole("button", { name: /Pular tour/i }).click();
    await expect(tourTitle).not.toBeVisible();

    // Reload — tour must NOT reappear.
    await page.reload();
    await expect(page.getByText(/Cadastre uma conexão/i)).not.toBeVisible({
      timeout: 3_000,
    });
  });

  test("Cmd+K opens global search overlay", async ({ page }) => {
    await page.goto("/");
    // Skip tour first to remove overlap with the search sheet.
    const skip = page.getByRole("button", { name: /Pular tour/i });
    if (await skip.isVisible().catch(() => false)) {
      await skip.click();
    }
    await page.keyboard.press("Meta+k");
    await expect(page.getByPlaceholder(/Buscar/i)).toBeVisible();
  });

  test("skip-to-content link is keyboard-reachable", async ({ page }) => {
    await page.goto("/");
    // First Tab should hit the skip link.
    await page.keyboard.press("Tab");
    const skip = page.locator("text=Pular para o conteúdo principal");
    await expect(skip).toBeFocused();
  });
});
