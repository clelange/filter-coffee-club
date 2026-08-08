import { defineConfig, devices } from '@playwright/test';

const e2ePort = Number(process.env.E2E_PORT ?? 8000);
const baseURL = `http://127.0.0.1:${e2ePort}`;

export default defineConfig({
  testDir: './tests-e2e',
  timeout: 30_000,
  workers: 1,
  use: {
    baseURL,
    trace: 'retain-on-failure'
  },
  projects: [
    {
      name: 'pi-and-mobile',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1024, height: 600 } }
    }
  ],
  webServer: {
    command: `E2E_PORT=${e2ePort} ../.venv/bin/python ../scripts/e2e_server.py`,
    url: `${baseURL}/health/ready`,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000
  }
});
