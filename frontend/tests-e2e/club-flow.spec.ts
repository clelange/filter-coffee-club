import { expect, test } from '@playwright/test';

test('Pi operator brews, then phone and kiosk tasters rate', async ({ page, browser }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'wakeLock', {
      configurable: true,
      value: {
        request: async () => {
          if (sessionStorage.getItem('wake-lock-fail')) throw new Error('Wake Lock unavailable');
          (globalThis as typeof globalThis & { __wakeLockRequested?: boolean }).__wakeLockRequested = true;
          return { release: async () => undefined };
        }
      }
    });
  });
  await page.goto('/');
  await expect(page).toHaveURL(/\/setup$/);

  await page.getByLabel('Your display name').fill('Ada');
  await page.getByLabel('Four-digit PIN').fill('1234');
  await page.getByLabel('Repeat PIN').fill('1234');
  await page.getByText('Shared touch display').click();
  await page.getByRole('button', { name: 'Create administrator' }).click();
  await expect(page).toHaveURL(/\/admin$/);

  await page.getByLabel('New member display name').fill('Bob');
  await page.getByLabel('Four-digit PIN').fill('2468');
  await page.getByRole('button', { name: 'Add member' }).click();
  await expect(page.getByText('Member added.')).toBeVisible();

  await page.goto('/coffees');
  await page.getByRole('button', { name: '+ Add coffee' }).click();
  await page.getByLabel('Roaster / brand').fill('PSI Roasters');
  await page.getByLabel('Coffee name').fill('Collider Blend');
  await page.getByRole('button', { name: 'Save coffee' }).click();
  await expect(page.getByRole('heading', { name: 'Collider Blend' })).toBeVisible();

  await page.goto('/brews/new');
  await page.getByRole('button', { name: /Light natural \/ fruity/ }).click();
  await page.getByRole('button', { name: 'Save and open brew mode' }).click();
  await expect(page.getByText('settings locked on screen')).toBeVisible();
  await expect(page.getByText('Collider Blend')).toBeVisible();
  await expect.poll(() => page.evaluate(() => Boolean((globalThis as typeof globalThis & { __wakeLockRequested?: boolean }).__wakeLockRequested))).toBe(true);
  await page.evaluate(() => sessionStorage.setItem('wake-lock-fail', '1'));
  await page.reload();
  await expect(page.getByRole('button', { name: 'Finish brew' })).toBeVisible();
  await expect.poll(() => page.evaluate(() => {
    const finish = [...document.querySelectorAll('button')].find((item) => item.textContent?.includes('Finish brew'));
    return Boolean(finish && finish.getBoundingClientRect().bottom <= window.innerHeight && document.documentElement.scrollWidth <= document.documentElement.clientWidth);
  })).toBe(true);

  await page.getByRole('button', { name: 'Finish brew' }).click();
  await page.getByLabel('Minutes').fill('3');
  await page.getByLabel('Seconds').fill('5');
  await page.getByRole('button', { name: 'Finalize and invite tasters' }).click();
  await expect(page.getByRole('heading', { name: 'Taste. Scan. Rate.' })).toBeVisible();
  await expect(page.getByAltText(/QR code to rate/)).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);

  const ratingPath = await page.getByRole('link', { name: 'Rate on this screen' }).getAttribute('href');
  expect(ratingPath).toContain('next=');
  const mobileRatingPath = new URL(ratingPath!, 'http://127.0.0.1:8000').searchParams.get('next');
  expect(mobileRatingPath).toContain('/rate/');
  const phoneContext = await browser.newContext({
    baseURL: 'http://127.0.0.1:8000',
    viewport: { width: 360, height: 800 },
    isMobile: true,
    hasTouch: true
  });
  const phone = await phoneContext.newPage();
  await phone.goto(mobileRatingPath!);
  await expect(phone).toHaveURL(/\/login\?next=/);
  await phone.getByLabel('Profile').selectOption({ label: 'Bob' });
  await phone.getByLabel('PIN').fill('2468');
  await phone.getByRole('button', { name: 'Sign in' }).click();
  await expect(phone.getByRole('heading', { name: 'How did it land?' })).toBeVisible();
  await expect.poll(() => phone.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await phone.getByRole('button', { name: 'Submit rating' }).click();
  await expect(phone.getByRole('heading', { name: 'Thanks, Bob.' })).toBeVisible();
  await phoneContext.close();

  await page.getByRole('link', { name: 'Rate on this screen' }).click();
  await page.getByLabel('PIN').fill('1234');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'How did it land?' })).toBeVisible();
  await page.getByRole('button', { name: 'Submit rating' }).click();
  await expect(page.getByRole('heading', { name: 'Thanks, Ada.' })).toBeVisible();
  await page.getByRole('button', { name: 'Done' }).click();
  await expect(page.getByRole('heading', { name: 'Taste. Scan. Rate.' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Sign in' })).toBeVisible();
  await page.setViewportSize({ width: 768, height: 1024 });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
});
