import { test, expect } from '@playwright/test';

test.describe('Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await page.route(/\/\/[^/]+\/api\/|localhost:8000/, (route) => route.abort());
    await page.goto('/');
  });

  test('app loads with the auth overlay when logged out', async ({ page }) => {
    const header = page.locator('header[data-layout="header"]');
    await expect(header).toBeVisible();
    await expect(header.getByRole('heading', { name: 'Workspace' })).toBeVisible();

    // Logged-out visitors get the overlay instead of a view (AppRoutes).
    await expect(page.getByRole('heading', { name: 'Welcome to CaseCite' })).toBeVisible();
  });

  test('left sidebar has navigation sections', async ({ page }) => {
    const sidebar = page.locator('aside[data-layout="left-sidebar"]');
    await expect(sidebar).toBeVisible();

    await expect(sidebar.getByText('Analysis Mode')).toBeVisible();
    await expect(sidebar.getByText('Legal Tools')).toBeVisible();
    await expect(sidebar.getByText('Documents', { exact: true })).toBeVisible();

    const modeButtons = sidebar.locator('button[class*="modeBtn"]');
    expect(await modeButtons.count()).toBeGreaterThan(0);
  });

  test('clicking a nav item while logged out prompts registration', async ({ page }) => {
    const sidebar = page.locator('aside[data-layout="left-sidebar"]');
    await expect(sidebar).toBeVisible();

    const modeButtons = sidebar.locator('button[class*="modeBtn"]');
    expect(await modeButtons.count()).toBeGreaterThan(1);

    // Logged-out users see locked mode buttons ...
    await expect(modeButtons.first()).toHaveClass(/modeBtnLocked|Locked/);

    // ... and clicking one opens the signup modal instead of navigating
    // (LeftSidebar: if (!isAuthenticated) setShowSignupModal(true)).
    await modeButtons.first().click();
    await expect(page.getByRole('heading', { name: 'Register' })).toBeVisible();

    // Dismissing it leaves the app on the auth overlay.
    await page.getByRole('button', { name: 'Cancel' }).click();
    await expect(page.getByRole('heading', { name: 'Register' })).not.toBeVisible();
    await expect(page.getByRole('heading', { name: 'Welcome to CaseCite' })).toBeVisible();
  });

  test('sidebar collapse and expand works', async ({ page }) => {
    const sidebar = page.locator('aside[data-layout="left-sidebar"]');
    await expect(sidebar).toBeVisible();

    const collapseButton = sidebar.getByRole('button', { name: /Collapse sidebar/i });
    await expect(collapseButton).toBeVisible();
    await collapseButton.click();

    await expect(sidebar).toHaveClass(/sidebarCollapsed|Collapsed/);
    await expect(sidebar.getByText('Analysis Mode')).not.toBeVisible();

    const expandButton = sidebar.getByRole('button', { name: /Expand sidebar/i });
    await expect(expandButton).toBeVisible();
    await expandButton.click();

    await expect(sidebar.getByText('Analysis Mode')).toBeVisible();
  });

  test('right panel collapse and expand works', async ({ page }) => {
    const rightPanel = page.locator('aside[data-layout="right-panel"]');
    await expect(rightPanel).toBeVisible();

    const collapseButton = rightPanel.getByRole('button', { name: /Collapse panel/i });
    await expect(collapseButton).toBeVisible();
    await collapseButton.click();

    await expect(rightPanel).toHaveClass(/rightPanelCollapsed|Collapsed/);

    const expandButton = rightPanel.getByRole('button', { name: /Expand panel/i });
    await expect(expandButton).toBeVisible();
    await expandButton.click();

    await expect(rightPanel.getByRole('button', { name: 'Sources' })).toBeVisible();
  });
});
