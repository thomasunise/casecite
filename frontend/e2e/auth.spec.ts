import { test, expect } from '@playwright/test';

// The self-hosted UI: a logged-out visitor sees the workspace shell with
// "Sign In" / "Register" in the header and an auth overlay in the main area.
// There is no backend in CI, so API calls are aborted to keep the run
// deterministic (the app degrades gracefully; nothing here needs a server).
test.describe('Authentication Flow', () => {
  test.beforeEach(async ({ page }) => {
    await page.route(/\/\/[^/]+\/api\/|localhost:8000/, (route) => route.abort());
    await page.goto('/');
  });

  test('header shows Sign In and Register when logged out', async ({ page }) => {
    const header = page.locator('header[data-layout="header"]');
    await expect(header).toBeVisible();
    await expect(header.getByRole('button', { name: /Sign In/i })).toBeVisible();
    await expect(header.getByRole('button', { name: /Register/i })).toBeVisible();
  });

  test('clicking Sign In opens the login modal', async ({ page }) => {
    const header = page.locator('header[data-layout="header"]');
    await header.getByRole('button', { name: /Sign In/i }).click();

    await expect(page.getByRole('heading', { name: 'Sign In' })).toBeVisible();
    await expect(page.getByText('Welcome back')).toBeVisible();
  });

  test('login modal has email and password fields', async ({ page }) => {
    const header = page.locator('header[data-layout="header"]');
    await header.getByRole('button', { name: /Sign In/i }).click();
    await expect(page.getByRole('heading', { name: 'Sign In' })).toBeVisible();

    // Scope to the modal so the header's own Sign In button doesn't collide.
    const modal = page.locator('[class*="modalContainer"]');
    await expect(modal.locator('input[type="email"][placeholder="you@example.com"]')).toBeVisible();
    await expect(modal.locator('input[type="password"][placeholder="Your password"]')).toBeVisible();
    await expect(modal.getByText('Email', { exact: true })).toBeVisible();
    await expect(modal.getByText('Password', { exact: true })).toBeVisible();
    await expect(modal.getByRole('button', { name: 'Sign In', exact: true })).toBeVisible();
  });

  test('clicking Register opens the signup modal', async ({ page }) => {
    const header = page.locator('header[data-layout="header"]');
    await header.getByRole('button', { name: /Register/i }).click();

    await expect(page.getByRole('heading', { name: 'Register' })).toBeVisible();
    await expect(page.getByText('Create your account')).toBeVisible();
  });

  test('signup modal has name, email, password, and confirm password fields', async ({ page }) => {
    const header = page.locator('header[data-layout="header"]');
    await header.getByRole('button', { name: /Register/i }).click();
    await expect(page.getByRole('heading', { name: 'Register' })).toBeVisible();

    const modal = page.locator('[class*="modalContainer"]');
    await expect(modal.locator('input[type="text"][placeholder="John Smith"]')).toBeVisible();
    await expect(modal.getByText('Full Name *', { exact: true })).toBeVisible();
    await expect(modal.locator('input[type="email"][placeholder="john@lawfirm.com"]')).toBeVisible();
    await expect(modal.getByText('Work Email *', { exact: true })).toBeVisible();
    await expect(modal.locator('input[type="password"][placeholder="12+ characters with upper, lower, number & symbol"]')).toBeVisible();
    await expect(modal.getByText('Password *', { exact: true })).toBeVisible();
    await expect(modal.locator('input[type="password"][placeholder="Confirm your password"]')).toBeVisible();
    await expect(modal.getByText('Confirm Password *', { exact: true })).toBeVisible();
  });

  test('signup validates required fields on empty submission', async ({ page }) => {
    const header = page.locator('header[data-layout="header"]');
    await header.getByRole('button', { name: /Register/i }).click();
    await expect(page.getByRole('heading', { name: 'Register' })).toBeVisible();

    const modal = page.locator('[class*="modalContainer"]');
    await modal.getByRole('button', { name: 'Register', exact: true }).click();

    // Validation runs client-side before any request (authStore.handleSignupSubmit).
    const errorBox = page.locator('[class*="errorBox"]');
    await expect(errorBox).toBeVisible({ timeout: 5000 });
    await expect(errorBox).toContainText('Please enter your name');
  });

  test('can switch between login and signup modals', async ({ page }) => {
    const header = page.locator('header[data-layout="header"]');
    await header.getByRole('button', { name: /Sign In/i }).click();
    await expect(page.getByRole('heading', { name: 'Sign In' })).toBeVisible();

    const modal = page.locator('[class*="modalContainer"]');

    // "Don't have an account? Register" at the bottom of the login modal
    await modal.getByRole('button', { name: 'Register', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Register' })).toBeVisible();

    // "Already have an account? Sign in" at the bottom of the signup modal
    await modal.getByRole('button', { name: 'Sign in', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Sign In' })).toBeVisible();
  });

  test('login modal can be closed via Cancel button', async ({ page }) => {
    const header = page.locator('header[data-layout="header"]');
    await header.getByRole('button', { name: /Sign In/i }).click();
    await expect(page.getByRole('heading', { name: 'Sign In' })).toBeVisible();

    await page.getByRole('button', { name: 'Cancel' }).click();
    await expect(page.getByRole('heading', { name: 'Sign In' })).not.toBeVisible();
  });

  test('signup modal can be closed via Cancel button', async ({ page }) => {
    const header = page.locator('header[data-layout="header"]');
    await header.getByRole('button', { name: /Register/i }).click();
    await expect(page.getByRole('heading', { name: 'Register' })).toBeVisible();

    await page.getByRole('button', { name: 'Cancel' }).click();
    await expect(page.getByRole('heading', { name: 'Register' })).not.toBeVisible();
  });
});
