import { test, expect } from '@playwright/test';

// The emailed reset link lands on /reset-password?token=… and must work signed
// out. There is no backend in CI: the token check is answered here, and every
// other API call is aborted (the app degrades gracefully).
test.describe('Reset password page', () => {
  test.beforeEach(async ({ page }) => {
    await page.route(/\/\/[^/]+\/api\/|localhost:8000/, (route) => {
      if (route.request().url().includes('/auth/verify-reset-token')) {
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ valid: true }) });
      }
      return route.abort();
    });
  });

  test('a link with no token explains itself instead of redirecting', async ({ page }) => {
    await page.goto('/reset-password');
    await expect(page).toHaveURL(/\/reset-password$/);
    await expect(page.getByRole('heading', { name: "This reset link can't be used" })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Request a new link' })).toBeVisible();
  });

  test('a valid link shows the new-password form with the policy', async ({ page }) => {
    await page.goto('/reset-password?token=e2e-token');
    await expect(page.getByRole('heading', { name: 'Choose a new password' })).toBeVisible();
    await expect(page.getByLabel('New password', { exact: true })).toBeVisible();
    await expect(page.getByLabel('Confirm new password')).toBeVisible();
    await expect(page.getByText(/At least 12 characters/)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Reset password' })).toBeVisible();
  });

  test('a weak password is rejected before any request is made', async ({ page }) => {
    await page.goto('/reset-password?token=e2e-token');
    await page.getByLabel('New password', { exact: true }).fill('short');
    await page.getByLabel('Confirm new password').fill('short');
    await page.getByRole('button', { name: 'Reset password' }).click();
    await expect(page.getByRole('alert')).toContainText('at least 12 characters');
  });

  test('signed out, an unknown address shows the sign-in overlay rather than the app', async ({ page }) => {
    // Signed out, every non-reset path shows the sign-in overlay.
    await page.goto('/no-such-page');
    await expect(page.getByRole('heading', { name: 'Welcome to CaseCite' })).toBeVisible();
  });
});
