import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests-e2e',
  timeout: 30_000,
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:8000',
    trace: 'retain-on-failure'
  },
  projects: [
    { name: 'pi-and-mobile', use: { ...devices['Desktop Chrome'], viewport: { width: 1024, height: 600 } } }
  ],
  webServer: {
    command: '../.venv/bin/python ../scripts/e2e_server.py',
    url: 'http://127.0.0.1:8000/health/ready',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000
  }
});
