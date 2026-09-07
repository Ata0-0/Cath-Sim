import { defineConfig, devices } from '@playwright/test';

/**
 * End-to-end check that the viewer actually starts and renders.
 *
 * Browser binary: Playwright normally downloads its own Chromium. In sandboxes
 * and CI images that ship a pre-installed browser instead, point
 * `PLAYWRIGHT_CHROMIUM_EXECUTABLE` at it (for example
 * `/opt/pw-browsers/chromium`) and this config will use it rather than trying
 * to download a matching build.
 *
 * WebGL: headless Chromium has no GPU here, so the software rasteriser
 * (SwiftShader) is enabled explicitly. Without it `new THREE.WebGLRenderer()`
 * throws and the scene never appears.
 */
const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined;

export default defineConfig({
  testDir: './e2e',
  timeout: 120_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'off',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        launchOptions: {
          executablePath,
          args: [
            '--enable-unsafe-swiftshader',
            '--use-gl=angle',
            '--use-angle=swiftshader',
            '--no-sandbox',
            '--disable-dev-shm-usage',
          ],
        },
      },
    },
  ],
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1',
    url: 'http://127.0.0.1:5173',
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
