import { defineConfig, devices } from '@playwright/test'

// 与 scripts/run_e2e.py 共用 TRPG_E2E_PORT，未设置时默认 18000。
const e2ePort = process.env.TRPG_E2E_PORT || '18000'

export default defineConfig({
  testDir: './e2e',
  workers: 1,
  use: {
    baseURL: `http://127.0.0.1:${e2ePort}`,
    locale: 'zh-CN',
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 5'] } },
  ],
})
