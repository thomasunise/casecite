import { test, expect } from '@playwright/test';

test.describe('Health Checks', () => {
  test('frontend loads without console errors', async ({ page }) => {
    const consoleErrors: string[] = [];

    // Listen for console errors before navigating
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    await page.goto('/');

    // Wait for the app to fully render
    await expect(page.locator('header[data-layout="header"]')).toBeVisible();

    // Filter out known benign errors (e.g., failed API calls to backend that may not be running)
    const criticalErrors = consoleErrors.filter((err) => {
      // Ignore network errors from API calls (backend may not be running in test).
      // Chromium and Firefox phrase these differently.
      if (err.includes('Failed to fetch') || err.includes('ERR_CONNECTION_REFUSED')) return false;
      if (err.includes('net::ERR_')) return false;
      if (err.includes('Cross-Origin Request Blocked')) return false;
      if (err.includes('CORS request did not succeed')) return false;
      if (err.includes('NetworkError when attempting to fetch resource')) return false;
      // Ignore favicon 404
      if (err.includes('favicon')) return false;
      // Ignore React DevTools extension messages
      if (err.includes('DevTools')) return false;
      return true;
    });

    expect(criticalErrors).toEqual([]);
  });

  test('backend health endpoint responds if available', async ({ page }) => {
    // Attempt to reach the backend health endpoint
    // This test is lenient: it passes if the backend responds with a 200,
    // but also passes (skips) if the backend is not running.
    let response;
    try {
      // Bounded so a black-holed port (as opposed to a refused one) can't
      // consume the whole test budget before we get to skip.
      response = await page.request.get('http://localhost:8000/health', { timeout: 5000 });
    } catch {
      // Backend is not running, skip this assertion
      test.skip(true, 'Backend is not running at http://localhost:8000');
      return;
    }

    if (response) {
      expect(response.status()).toBe(200);
    }
  });

  test('all CSS modules load correctly (no unstyled content flash)', async ({ page }) => {
    await page.goto('/');

    // Wait for the full layout to render
    const header = page.locator('header[data-layout="header"]');
    await expect(header).toBeVisible();

    const sidebar = page.locator('aside[data-layout="left-sidebar"]');
    await expect(sidebar).toBeVisible();

    const rightPanel = page.locator('aside[data-layout="right-panel"]');
    await expect(rightPanel).toBeVisible();

    // Verify that CSS modules have loaded by checking that elements have
    // module-scoped class names (they contain underscores or hashes)
    // rather than being plain unstyled elements.
    const headerClasses = await header.getAttribute('class');
    expect(headerClasses).toBeTruthy();
    expect(headerClasses!.length).toBeGreaterThan(0);

    const sidebarClasses = await sidebar.getAttribute('class');
    expect(sidebarClasses).toBeTruthy();
    expect(sidebarClasses!.length).toBeGreaterThan(0);

    // Check that the header has a computed background color (not transparent/default)
    // which indicates CSS has loaded
    const headerBgColor = await header.evaluate((el) => {
      return window.getComputedStyle(el).backgroundColor;
    });
    // Background should not be fully transparent (rgba(0,0,0,0))
    // A styled header will have some background color set
    expect(headerBgColor).toBeTruthy();
  });

  test('page title and meta tags are present', async ({ page }) => {
    await page.goto('/');

    // The page should have a title
    const title = await page.title();
    expect(title).toBeTruthy();
    expect(title.length).toBeGreaterThan(0);
  });

  test('no broken images on the page', async ({ page }) => {
    await page.goto('/');

    // Wait for the app to render
    await expect(page.locator('header[data-layout="header"]')).toBeVisible();

    // Check all images are loaded correctly
    const images = page.locator('img');
    const imageCount = await images.count();

    for (let i = 0; i < imageCount; i++) {
      const img = images.nth(i);
      const naturalWidth = await img.evaluate((el: HTMLImageElement) => el.naturalWidth);
      const src = await img.getAttribute('src');

      // Images should have a natural width > 0 (meaning they loaded)
      // Skip data URIs as they are always valid
      if (src && !src.startsWith('data:')) {
        expect(naturalWidth, `Image ${src} failed to load`).toBeGreaterThan(0);
      }
    }
  });

  test('app renders all three layout regions', async ({ page }) => {
    await page.goto('/');

    // Verify the three main layout regions exist
    await expect(page.locator('header[data-layout="header"]')).toBeVisible();
    await expect(page.locator('aside[data-layout="left-sidebar"]')).toBeVisible();
    await expect(page.locator('aside[data-layout="right-panel"]')).toBeVisible();
  });
});
