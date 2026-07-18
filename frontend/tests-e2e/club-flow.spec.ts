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

  const peopleTab = page.getByRole('tab', { name: 'People' });
  await expect(page.getByRole('tab')).toHaveCount(5);
  await expect(peopleTab).toHaveAttribute('aria-selected', 'true');
  await peopleTab.focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.getByRole('tab', { name: 'Equipment' })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('heading', { name: 'Grinder', exact: true })).toBeVisible();
  await page.keyboard.press('ArrowLeft');
  await expect(peopleTab).toHaveAttribute('aria-selected', 'true');

  await page.setViewportSize({ width: 393, height: 851 });
  const menuButton = page.getByRole('button', { name: 'Menu' });
  const mainNavigation = page.getByRole('navigation', { name: 'Main navigation' });
  await expect(menuButton).toBeVisible();
  await expect(mainNavigation).toBeHidden();
  await menuButton.click();
  await expect(menuButton).toHaveAttribute('aria-expanded', 'true');
  await expect(page.getByRole('link', { name: 'Admin' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Ada · Sign out' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(menuButton).toHaveAttribute('aria-expanded', 'false');
  await expect(menuButton).toBeFocused();
  const adminSectionSelect = page.getByRole('combobox', { name: 'Admin section', exact: true });
  await expect(adminSectionSelect).toBeVisible();
  await adminSectionSelect.selectOption('equipment');
  await expect(page.getByRole('heading', { name: 'Grinder', exact: true })).toBeVisible();
  await adminSectionSelect.selectOption('people');
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await page.setViewportSize({ width: 1024, height: 600 });

  await page.getByLabel('New member display name').fill('Bob');
  await page.getByLabel('Four-digit PIN').fill('2468');
  await page.getByRole('button', { name: 'Add member' }).click();
  await expect(page.getByText('Member added.')).toBeVisible();
  await expect(page.getByLabel('Require PIN change for Bob')).toBeChecked();

  await page.goto('/coffees');
  await page.getByRole('button', { name: '+ Add coffee' }).click();
  await page.getByLabel('Roaster / brand').fill('PSI Roasters');
  await page.getByLabel('Coffee name').fill('Collider Blend');
  await page.getByRole('button', { name: 'Save coffee' }).click();
  await expect(page.getByRole('heading', { name: 'Collider Blend' })).toBeVisible();

  await page.goto('/brews/new');
  await page.getByRole('button', { name: '+ Coffee' }).click();
  const inlineRoaster = page.getByLabel('Roaster / brand');
  const inlineCoffeeName = page.getByLabel('Coffee name');
  const inlineSave = page.getByRole('button', { name: 'Save coffee' });
  await inlineSave.click();
  await expect(inlineRoaster).toBeFocused();
  await inlineRoaster.fill('Responsive Layout Review Roastery');
  await inlineCoffeeName.fill('Ethiopia Guji Hambela Buku Abel Extended Lot Name');
  let failInlineCoffee = true;
  await page.route('**/api/v1/coffees', async (route) => {
    if (route.request().method() === 'POST' && failInlineCoffee) {
      failInlineCoffee = false;
      await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'Temporary coffee failure' }) });
      return;
    }
    await route.continue();
  });
  await inlineSave.click();
  await expect(page.getByRole('alert')).toHaveText('Temporary coffee failure');
  await expect(inlineRoaster).toHaveValue('Responsive Layout Review Roastery');
  await expect(inlineCoffeeName).toHaveValue('Ethiopia Guji Hambela Buku Abel Extended Lot Name');
  await page.unroute('**/api/v1/coffees');
  await inlineSave.click();
  await expect(page.getByLabel('Coffee').locator('option:checked')).toHaveText('Responsive Layout Review Roastery · Ethiopia Guji Hambela Buku Abel Extended Lot Name');
  await page.getByRole('button', { name: /Light natural \/ fruity/ }).click();
  await page.getByRole('spinbutton', { name: 'Coffee dose' }).fill('40');
  await page.getByRole('spinbutton', { name: 'Total water' }).fill('600');
  await page.getByRole('button', { name: 'Save and open brew mode' }).click();
  await expect(page.getByText('settings locked on screen')).toBeVisible();
  await expect(page.getByText('Ethiopia Guji Hambela Buku Abel Extended Lot Name')).toBeVisible();
  await expect.poll(() => page.evaluate(() => {
    const metric = document.querySelector<HTMLElement>('.hero-metric');
    const value = metric?.querySelector<HTMLElement>('strong');
    const label = metric?.querySelector<HTMLElement>('span');
    if (!value || !label) return -1;
    return label.getBoundingClientRect().top - value.getBoundingClientRect().bottom;
  })).toBeGreaterThanOrEqual(6);
  await expect.poll(() => page.evaluate(() => Boolean((globalThis as typeof globalThis & { __wakeLockRequested?: boolean }).__wakeLockRequested))).toBe(true);
  await page.evaluate(() => sessionStorage.setItem('wake-lock-fail', '1'));
  await page.reload();
  await expect(page.getByRole('button', { name: 'Finish brew' })).toBeVisible();
  await expect.poll(() => page.evaluate(() => {
    const finish = [...document.querySelectorAll('button')].find((item) => item.textContent?.includes('Finish brew'));
    return Boolean(finish && finish.getBoundingClientRect().bottom <= window.innerHeight && document.documentElement.scrollWidth <= document.documentElement.clientWidth);
  })).toBe(true);

  await page.getByRole('button', { name: 'Finish brew' }).click();
  const modalLayout = await page.evaluate(() => {
    const dialog = document.querySelector<HTMLElement>('.modal');
    const fields = dialog?.querySelector<HTMLElement>('.field-grid');
    const actions = dialog?.querySelector<HTMLElement>('.actions');
    if (!dialog || !fields || !actions) return null;
    const dialogBox = dialog.getBoundingClientRect();
    return {
      actionGap: actions.getBoundingClientRect().top - fields.getBoundingClientRect().bottom,
      background: getComputedStyle(dialog).backgroundColor,
      withinViewport: dialogBox.top >= 0 && dialogBox.bottom <= window.innerHeight
    };
  });
  expect(modalLayout?.actionGap).toBeGreaterThanOrEqual(10);
  expect(modalLayout?.background).toBe('rgb(255, 253, 252)');
  expect(modalLayout?.withinViewport).toBe(true);
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
  await expect(phone).toHaveURL(/\/account\/pin\?next=/);
  await phone.getByLabel('Current PIN').fill('2468');
  await phone.getByLabel('New PIN', { exact: true }).fill('1357');
  await phone.getByLabel('Repeat new PIN').fill('1357');
  await phone.getByRole('button', { name: 'Change PIN and continue' }).click();
  await expect(phone.getByRole('heading', { name: 'How did it land?' })).toBeVisible();
  for (const sliderName of ['Overall liking', 'Acidity', 'Bitterness', 'Sweetness', 'Body']) {
    await expect(phone.getByRole('slider', { name: sliderName, exact: true })).toBeVisible();
  }
  const flavorDisclosures = phone.locator('.flavor-disclosure');
  await expect(flavorDisclosures).toHaveCount(8);
  for (let index = 0; index < await flavorDisclosures.count(); index += 1) {
    await expect(flavorDisclosures.nth(index)).toHaveAttribute('aria-expanded', 'false');
  }
  const fruityDisclosure = phone.locator('.flavor-disclosure').filter({ hasText: 'Fruity' });
  await expect(phone.getByRole('button', { name: 'Berry' })).toBeHidden();
  await fruityDisclosure.click();
  await expect(phone.getByRole('button', { name: 'Berry' })).toBeVisible();
  for (const flavor of ['Fruity · general', 'Berry', 'Grape', 'Citrus', 'Stone fruit']) {
    await phone.getByRole('button', { name: flavor, exact: true }).click();
  }
  await expect(fruityDisclosure).toContainText('5 selected');
  await expect(phone.getByRole('button', { name: 'Tropical fruit' })).toBeDisabled();
  await expect(phone.getByRole('button', { name: 'Berry' })).toBeEnabled();
  await phone.getByRole('button', { name: 'Berry' }).click();
  await expect(fruityDisclosure).toContainText('4 selected');
  await expect(phone.getByRole('button', { name: 'Tropical fruit' })).toBeEnabled();
  const ratingScaleLayout = await phone.evaluate(() => {
    const name = document.querySelector<HTMLElement>('.scale-name');
    const score = document.querySelector<HTMLElement>('.scale-title output');
    const anchor = document.querySelector<HTMLElement>('.anchors span');
    const intensityHint = document.querySelector<HTMLElement>('.intensity-grid .scale-hint');
    if (!name || !score || !anchor || !intensityHint) return null;
    return {
      titleGap: score.getBoundingClientRect().left - name.getBoundingClientRect().right,
      anchorSize: getComputedStyle(anchor).fontSize,
      anchorWeight: getComputedStyle(anchor).fontWeight,
      intensitySize: getComputedStyle(intensityHint).fontSize,
      intensityWeight: getComputedStyle(intensityHint).fontWeight
    };
  });
  expect(ratingScaleLayout?.titleGap).toBeGreaterThanOrEqual(16);
  expect(ratingScaleLayout?.anchorSize).toBe(ratingScaleLayout?.intensitySize);
  expect(ratingScaleLayout?.anchorWeight).toBe(ratingScaleLayout?.intensityWeight);
  await expect.poll(() => phone.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await phone.getByRole('button', { name: 'Submit rating' }).click();
  await expect(phone.getByRole('heading', { name: 'Thanks, Bob.' })).toBeVisible();
  await phone.goto('/analytics');
  await expect(phone.getByRole('heading', { name: 'Find the useful signal.' })).toBeVisible();
  const coffeeFilter = phone.getByRole('combobox', { name: 'Coffee', exact: true });
  const axisFilter = phone.getByRole('combobox', { name: 'Horizontal axis', exact: true });
  const mobileCoffeeBox = await coffeeFilter.boundingBox();
  const mobileAxisBox = await axisFilter.boundingBox();
  expect(mobileCoffeeBox).not.toBeNull();
  expect(mobileAxisBox).not.toBeNull();
  expect(Math.abs(mobileCoffeeBox!.x - mobileAxisBox!.x)).toBeLessThanOrEqual(1);
  expect(Math.abs(mobileCoffeeBox!.width - mobileAxisBox!.width)).toBeLessThanOrEqual(1);
  expect(mobileAxisBox!.y).toBeGreaterThan(mobileCoffeeBox!.y + mobileCoffeeBox!.height);
  await phone.setViewportSize({ width: 768, height: 1024 });
  const tabletCoffeeBox = await coffeeFilter.boundingBox();
  const tabletAxisBox = await axisFilter.boundingBox();
  expect(tabletCoffeeBox).not.toBeNull();
  expect(tabletAxisBox).not.toBeNull();
  expect(Math.abs(tabletCoffeeBox!.y - tabletAxisBox!.y)).toBeLessThanOrEqual(1);
  expect(Math.abs(tabletCoffeeBox!.width - tabletAxisBox!.width)).toBeLessThanOrEqual(1);
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

  const invitationPath = new URL(page.url()).pathname;
  await page.goto(`/login?next=${encodeURIComponent(invitationPath)}`);
  await page.getByLabel('PIN').fill('1234');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Taste. Scan. Rate.' })).toBeVisible();
  const personalRatingPath = await page.getByRole('link', { name: 'Rate on this screen' }).getAttribute('href');
  expect(personalRatingPath).toMatch(/^\/rate\//);
  await page.getByRole('link', { name: 'Rate on this screen' }).click();
  await expect(page).toHaveURL(/\/rate\//);
  await expect(page.getByRole('heading', { name: 'Thanks, Ada.' })).toBeVisible();
  await page.setViewportSize({ width: 768, height: 1024 });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
});
