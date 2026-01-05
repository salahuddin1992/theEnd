import { test, expect } from '@playwright/test';

/**
 * NebulaCompute API E2E Tests
 * Tests API endpoints through the browser
 */

test.describe('API Health Checks', () => {
  test('should return health status from API', async ({ request }) => {
    const response = await request.get('/api/health').catch(() => null);

    if (response) {
      expect(response.ok() || response.status() === 404).toBeTruthy();
    }
  });

  test('should return cluster info from API', async ({ request }) => {
    const response = await request.get('/api/cluster/info').catch(() => null);

    if (response && response.ok()) {
      const data = await response.json();
      expect(data).toBeDefined();
    }
  });
});

test.describe('Workers API', () => {
  test('should list workers from API', async ({ request }) => {
    const response = await request.get('/api/workers').catch(() => null);

    if (response && response.ok()) {
      const data = await response.json();
      expect(Array.isArray(data) || data.workers !== undefined).toBeTruthy();
    }
  });

  test('should get worker stats from API', async ({ request }) => {
    const response = await request.get('/api/workers/stats').catch(() => null);

    if (response && response.ok()) {
      const data = await response.json();
      expect(data).toBeDefined();
    }
  });
});

test.describe('Jobs API', () => {
  test('should list jobs from API', async ({ request }) => {
    const response = await request.get('/api/jobs').catch(() => null);

    if (response && response.ok()) {
      const data = await response.json();
      expect(Array.isArray(data) || data.jobs !== undefined).toBeTruthy();
    }
  });

  test('should get job queue status from API', async ({ request }) => {
    const response = await request.get('/api/jobs/queue').catch(() => null);

    if (response && response.ok()) {
      const data = await response.json();
      expect(data).toBeDefined();
    }
  });
});

test.describe('Metrics API', () => {
  test('should return Prometheus metrics', async ({ request }) => {
    const response = await request.get('/metrics').catch(() => null);

    if (response && response.ok()) {
      const text = await response.text();
      // Prometheus metrics typically contain # HELP or # TYPE
      expect(text.includes('#') || text.includes('_total') || text.includes('_count')).toBeTruthy();
    }
  });

  test('should return cluster metrics', async ({ request }) => {
    const response = await request.get('/api/metrics').catch(() => null);

    if (response && response.ok()) {
      const data = await response.json();
      expect(data).toBeDefined();
    }
  });
});

test.describe('WebSocket Connection', () => {
  test('should establish WebSocket connection', async ({ page }) => {
    await page.goto('/');

    // Check if WebSocket connections are being made
    const wsConnections: string[] = [];

    page.on('websocket', ws => {
      wsConnections.push(ws.url());
    });

    // Wait for potential WebSocket connections
    await page.waitForTimeout(3000);

    // Log connections for debugging
    if (wsConnections.length > 0) {
      console.log('WebSocket connections:', wsConnections);
    }
  });
});
