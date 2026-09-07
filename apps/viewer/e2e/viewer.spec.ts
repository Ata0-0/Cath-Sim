/**
 * Verifies the acceptance criteria that can only be checked in a real browser:
 * the viewer opens, the research-only label is visible, the catheter renders,
 * the solver metrics update, and the actuation controls change the shape.
 */

import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByTestId('scene-canvas')).toBeVisible();
  (page as unknown as { _errors: string[] })._errors = errors;
});

test('viewer opens with the research-only label and a rendered scene', async ({ page }) => {
  await expect(page.getByTestId('research-banner')).toContainText(
    'Research prototype - Not for clinical use.',
  );
  await expect(page.getByTestId('metrics-hud')).toBeVisible();
  await expect(page.getByTestId('demo-warning')).toContainText(/placeholder/i);

  const canvas = page.getByTestId('scene-canvas');
  const box = await canvas.boundingBox();
  expect(box?.width ?? 0).toBeGreaterThan(200);
  expect(box?.height ?? 0).toBeGreaterThan(200);
});

test('the solver runs and reports metrics', async ({ page }) => {
  const hud = page.getByTestId('metrics-hud');
  await expect(hud).toContainText('Solver iterations');
  await expect(hud).toContainText('Residual |grad E|');
  // Simulation time must advance while the loop is running.
  const first = await page.getByTestId('sim-time').textContent();
  await expect
    .poll(async () => page.getByTestId('sim-time').textContent(), { timeout: 20_000 })
    .not.toBe(first);
});

test('steering changes the solved shape', async ({ page }) => {
  // Pause so the comparison is against a settled state.
  const readTip = async () => {
    const text = await page.getByTestId('metrics-hud').textContent();
    const match = text?.match(/Tip position([-\d., ]+)mm/);
    return match?.[1]?.trim() ?? '';
  };
  const before = await readTip();
  await page.locator('#steer-x').fill('1');
  await expect.poll(readTip, { timeout: 20_000 }).not.toBe(before);
});

test('play / pause / step / reset controls work', async ({ page }) => {
  await page.getByTestId('play-pause').click();
  await expect(page.getByTestId('play-pause')).toHaveText('Play');
  await expect(page.getByTestId('step')).toBeEnabled();
  await page.getByTestId('step').click();
  await page.getByTestId('reset').click();
  await expect(page.getByTestId('play-pause')).toHaveText('Play');
});

test('no uncaught page errors during a session', async ({ page }) => {
  await page.waitForTimeout(3000);
  const errors = (page as unknown as { _errors: string[] })._errors;
  expect(errors).toEqual([]);
});
