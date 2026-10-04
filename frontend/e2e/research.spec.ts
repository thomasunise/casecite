import { test, expect } from '@playwright/test';

// Logged-out state of the main area: the auth overlay (AppRoutes renders it
// in place of every view) plus the always-visible sidebar sections.
test.describe('Auth overlay and workspace shell', () => {
  test.beforeEach(async ({ page }) => {
    await page.route(/\/\/[^/]+\/api\/|localhost:8000/, (route) => route.abort());
    await page.goto('/');
  });

  test('auth overlay introduces the product when logged out', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Welcome to CaseCite' })).toBeVisible();
    await expect(page.getByText(/legal research platform/i)).toBeVisible();
  });

  test('auth overlay offers Register and Sign In', async ({ page }) => {
    // The header (with its own Register / Sign In) renders inside <main>, so
    // scope to the overlay container: the heading's parent element.
    const overlay = page.getByRole('heading', { name: 'Welcome to CaseCite' }).locator('..');
    await expect(overlay.getByRole('button', { name: 'Register' })).toBeVisible();
    await expect(overlay.getByRole('button', { name: 'Sign In' })).toBeVisible();
  });

  test('overlay Register button opens the signup modal', async ({ page }) => {
    const overlay = page.getByRole('heading', { name: 'Welcome to CaseCite' }).locator('..');
    await overlay.getByRole('button', { name: 'Register' }).click();
    await expect(page.getByRole('heading', { name: 'Register' })).toBeVisible();
  });

  test('overlay Sign In button opens the login modal', async ({ page }) => {
    const overlay = page.getByRole('heading', { name: 'Welcome to CaseCite' }).locator('..');
    await overlay.getByRole('button', { name: 'Sign In' }).click();
    await expect(page.getByRole('heading', { name: 'Sign In' })).toBeVisible();
  });

  test('analysis mode selector is present in the sidebar', async ({ page }) => {
    const sidebar = page.locator('aside[data-layout="left-sidebar"]');
    await expect(sidebar).toBeVisible();
    await expect(sidebar.getByText('Analysis Mode')).toBeVisible();

    const modeButtons = sidebar.locator('button[class*="modeBtn"]');
    expect(await modeButtons.count()).toBeGreaterThanOrEqual(3);
    for (const title of ['Matter Strategy', 'Contracts', 'Drafting']) {
      await expect(sidebar.getByText(title, { exact: true })).toBeVisible();
    }
  });

  test('sidebar displays the Knowledge Base documents section', async ({ page }) => {
    const sidebar = page.locator('aside[data-layout="left-sidebar"]');
    await expect(sidebar).toBeVisible();

    await expect(sidebar.getByText('Documents', { exact: true })).toBeVisible();
    await expect(sidebar.getByText('Knowledge Base', { exact: true })).toBeVisible();
    await expect(sidebar.getByText('All documents & sources')).toBeVisible();
  });
});
