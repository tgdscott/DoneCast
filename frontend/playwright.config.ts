import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  // Look for tests in both legacy ./e2e and the requested ./src/tests locations
  testDir: '.',
  testMatch: [
    'src/tests/**/*.spec.ts',
    'src/tests/**/*.spec.tsx',
    'e2e/**/*.spec.ts',
    'e2e/**/*.spec.tsx',
  ],
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
  snapshotDir: 'e2e/__screenshots__',
  webServer: {
    command: 'npm run dev',
  url: process.env.E2E_BASE_URL || 'http://127.0.0.1:5173',
    reuseExistingServer: true,
    timeout: 120_000,
  },
  use: {
  baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
    screenshot: 'only-on-failure',
    viewport: { width: 1280, height: 800 },
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
