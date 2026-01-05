import { test, expect } from '@playwright/test';

/**
 * NebulaCompute Dashboard E2E Tests
 * Tests the main dashboard functionality
 */

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should load the dashboard homepage', async ({ page }) => {
    // Wait for the page to load
    await expect(page).toHaveTitle(/NebulaCompute|Dashboard/i);
  });

  test('should display the navigation menu', async ({ page }) => {
    // Check for navigation elements
    const nav = page.locator('nav, [role="navigation"], header');
    await expect(nav.first()).toBeVisible();
  });

  test('should show cluster status section', async ({ page }) => {
    // Look for cluster-related content
    const statusSection = page.locator('text=/cluster|status|workers/i').first();
    await expect(statusSection).toBeVisible({ timeout: 10000 });
  });
});

test.describe('Workers Page', () => {
  test('should navigate to workers page', async ({ page }) => {
    await page.goto('/');

    // Try to find and click workers link
    const workersLink = page.locator('a[href*="worker"], button:has-text("Workers")').first();

    if (await workersLink.isVisible()) {
      await workersLink.click();
      await expect(page.url()).toContain('worker');
    }
  });

  test('should display worker list or empty state', async ({ page }) => {
    await page.goto('/workers');

    // Should show either workers or empty state message
    const content = page.locator('text=/worker|no workers|empty/i').first();
    await expect(content).toBeVisible({ timeout: 10000 });
  });
});

test.describe('Jobs Page', () => {
  test('should navigate to jobs page', async ({ page }) => {
    await page.goto('/');

    // Try to find and click jobs link
    const jobsLink = page.locator('a[href*="job"], button:has-text("Jobs")').first();

    if (await jobsLink.isVisible()) {
      await jobsLink.click();
      await expect(page.url()).toContain('job');
    }
  });

  test('should display jobs list or empty state', async ({ page }) => {
    await page.goto('/jobs');

    // Should show either jobs or empty state message
    const content = page.locator('text=/job|no jobs|empty|queue/i').first();
    await expect(content).toBeVisible({ timeout: 10000 });
  });
});
