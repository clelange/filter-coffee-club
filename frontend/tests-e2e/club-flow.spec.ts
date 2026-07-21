import { expect, test, type Page } from '@playwright/test';
import { fileURLToPath } from 'node:url';

const ethiopiaPhoto = fileURLToPath(
  new URL('../../backend/app/demo_assets/catalog/demo-coffee-ethiopia.webp', import.meta.url)
);
const colombiaPhoto = fileURLToPath(
  new URL('../../backend/app/demo_assets/catalog/demo-coffee-colombia.webp', import.meta.url)
);

const keyboardCapableControls =
  'input:not([type="range"]):not([type="radio"]):not([type="checkbox"]), textarea';

async function enterKioskPin(page: Page, pin: string, label = 'PIN') {
  const pad = page.getByRole('group', { name: label, exact: true });
  for (const digit of pin) await pad.getByRole('button', { name: digit, exact: true }).click();
}

async function setKioskNumber(page: Page, label: string, value: string) {
  await page.getByRole('button', { name: new RegExp(`^Set ${label};`) }).click();
  const dialog = page.getByRole('dialog', { name: label, exact: true });
  const clear = dialog.getByRole('button', { name: /^(Clear|Clear value)$/ });
  await clear.click();
  for (const character of value) {
    await dialog.getByRole('button', { name: character, exact: true }).click();
  }
  await dialog.getByRole('button', { name: 'Apply' }).click();
}

test('Pi operator brews, then phone and kiosk tasters rate', async ({ page, browser }) => {
  test.setTimeout(60_000);
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'wakeLock', {
      configurable: true,
      value: {
        request: async () => {
          if (sessionStorage.getItem('wake-lock-fail')) throw new Error('Wake Lock unavailable');
          (
            globalThis as typeof globalThis & { __wakeLockRequested?: boolean }
          ).__wakeLockRequested = true;
          return { release: async () => undefined };
        }
      }
    });
  });
  await page.goto('/?kiosk=1');
  await expect(page).toHaveURL(/\/setup$/);
  await expect(
    page.getByRole('heading', { name: 'Complete setup on a phone or computer.' })
  ).toBeVisible();
  await expect(page.locator(keyboardCapableControls)).toHaveCount(0);
  await page.getByRole('button', { name: 'Check again' }).click();
  await expect(page.getByRole('alert')).toContainText('Setup is not complete yet');

  await page.goto('/setup?kiosk=0');

  await page.getByLabel('Your display name').fill('Ada');
  await page.getByLabel('Four-digit PIN').fill('1234');
  await page.getByLabel('Repeat PIN').fill('1234');
  await page.getByRole('button', { name: 'Create administrator' }).click();
  await expect(page).toHaveURL(/\/admin$/);

  const peopleTab = page.getByRole('tab', { name: 'People' });
  await expect(page.getByRole('tab')).toHaveCount(5);
  await expect(peopleTab).toHaveAttribute('aria-selected', 'true');
  await peopleTab.focus();
  await page.keyboard.press('ArrowRight');
  const equipmentTab = page.getByRole('tab', { name: 'Equipment' });
  await expect(equipmentTab).toHaveAttribute('aria-selected', 'true');
  await expect(equipmentTab).toBeFocused();
  await expect(page.getByRole('heading', { name: 'Grinder', exact: true })).toBeVisible();
  await page.keyboard.press('ArrowLeft');
  await expect(peopleTab).toHaveAttribute('aria-selected', 'true');

  await page.getByRole('tab', { name: 'Presets & flavors' }).click();
  const presetCreator = page.locator('.preset-creator');
  await presetCreator.getByLabel('Name').fill('Club balanced');
  await presetCreator.getByLabel('Ratio').fill('16.5');
  await presetCreator.getByLabel('Minimum setting').fill('24');
  await presetCreator.getByLabel('Maximum setting').fill('28');
  await presetCreator.getByRole('button', { name: 'Add preset' }).click();
  await expect(page.getByText('Preset added.')).toBeVisible();
  await expect(page.getByLabel('Preset name').last()).toHaveValue('Club balanced');
  await peopleTab.click();

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
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth
      )
    )
    .toBe(true);
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
  await page.getByLabel('Photo (optional)', { exact: true }).setInputFiles(ethiopiaPhoto);
  await expect(page.getByRole('img', { name: 'Selected catalog item' })).toBeVisible();
  await page.getByRole('button', { name: 'Save coffee' }).click();
  await expect(page.getByRole('heading', { name: 'Collider Blend' })).toBeVisible();
  const colliderCard = page
    .locator('article[data-testid="catalog-card"]')
    .filter({ has: page.getByRole('heading', { name: 'Collider Blend' }) });
  const colliderPhoto = colliderCard.getByRole('img', { name: 'PSI Roasters Collider Blend' });
  await expect(colliderPhoto).toBeVisible();
  await expect(colliderCard.locator('input, textarea, select')).toHaveCount(0);
  await expect(colliderCard.getByRole('button', { name: /Edit|Clone|Archive|photo/i })).toHaveCount(
    0
  );
  await expect(colliderCard.getByRole('link', { name: 'Brew this' })).toHaveAttribute(
    'href',
    /\/brews\/new\?coffee=\d+/
  );

  const catalogGeometry = await page.evaluate(() => {
    const cards = [...document.querySelectorAll<HTMLElement>('[data-testid="catalog-card"]')];
    const first = cards[0];
    const photo = first?.querySelector<HTMLElement>('.catalog-photo');
    const copy = first?.querySelector<HTMLElement>('.catalog-copy');
    const actionBottoms = cards
      .map((card) => card.querySelector<HTMLElement>('.catalog-actions'))
      .filter((action): action is HTMLElement => Boolean(action))
      .map((action) => action.getBoundingClientRect().bottom);
    return {
      photoTextGap:
        photo && copy
          ? copy.getBoundingClientRect().top - photo.getBoundingClientRect().bottom
          : -1,
      actionBottomSpread:
        actionBottoms.length > 1 ? Math.max(...actionBottoms) - Math.min(...actionBottoms) : 0,
      firstCardUseful:
        Boolean(first) &&
        first.getBoundingClientRect().top < window.innerHeight &&
        first.getBoundingClientRect().bottom > 0,
      noOverflow: document.documentElement.scrollWidth <= document.documentElement.clientWidth
    };
  });
  expect(catalogGeometry.photoTextGap).toBeGreaterThanOrEqual(12);
  expect(catalogGeometry.actionBottomSpread).toBeLessThanOrEqual(1);
  expect(catalogGeometry.firstCardUseful).toBe(true);
  expect(catalogGeometry.noOverflow).toBe(true);

  const firstPhotoPath = await colliderPhoto.getAttribute('src');
  await colliderCard.getByRole('link', { name: 'View details for Collider Blend' }).click();
  await expect(page).toHaveURL(/\/coffees\/\d+$/);
  await expect(page.getByRole('heading', { name: 'About this bag.' })).toBeVisible();
  await expect(page.locator('input, textarea, select')).toHaveCount(0);
  await page.getByRole('button', { name: 'Edit', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Update bag details.' })).toBeVisible();
  await page.getByLabel('Roaster / brand').fill('Temporary roaster');
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'About this bag.' })).toBeVisible();
  await expect(page.getByText('PSI Roasters', { exact: true }).first()).toBeVisible();
  await expect(page.locator('input, textarea, select')).toHaveCount(0);
  await page.getByRole('button', { name: 'Edit', exact: true }).click();
  await page
    .getByLabel('Replacement photo (optional)', { exact: true })
    .setInputFiles(colombiaPhoto);
  await page.getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByRole('heading', { name: 'About this bag.' })).toBeVisible();
  const detailPhoto = page.getByRole('img', { name: 'PSI Roasters Collider Blend' });
  await expect.poll(() => detailPhoto.getAttribute('src')).not.toBe(firstPhotoPath);
  const detailGeometry = await page.evaluate(() => {
    const photo = document.querySelector<HTMLElement>('[data-testid="detail-photo"]');
    const identity = document.querySelector<HTMLElement>('[data-testid="detail-identity"]');
    if (!photo || !identity) return null;
    return {
      horizontalGap: identity.getBoundingClientRect().left - photo.getBoundingClientRect().right,
      noOverflow: document.documentElement.scrollWidth <= document.documentElement.clientWidth
    };
  });
  expect(detailGeometry?.horizontalGap).toBeGreaterThanOrEqual(20);
  expect(detailGeometry?.noOverflow).toBe(true);
  await page.setViewportSize({ width: 393, height: 851 });
  await expect
    .poll(() =>
      page.evaluate(() => {
        const photo = document.querySelector<HTMLElement>('[data-testid="detail-photo"]');
        const identity = document.querySelector<HTMLElement>('[data-testid="detail-identity"]');
        return Boolean(
          photo &&
          identity &&
          identity.getBoundingClientRect().top - photo.getBoundingClientRect().bottom >= 20 &&
          document.documentElement.scrollWidth <= document.documentElement.clientWidth
        );
      })
    )
    .toBe(true);
  await page.setViewportSize({ width: 1024, height: 600 });

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
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Temporary coffee failure' })
      });
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
  await expect(
    page.getByRole('combobox', { name: 'Coffee', exact: true }).locator('option:checked')
  ).toHaveText(
    'Responsive Layout Review Roastery · Ethiopia Guji Hambela Buku Abel Extended Lot Name'
  );

  await page.goto('/?kiosk=1');
  await expect(page.getByRole('link', { name: 'Sign in to brew' })).toBeVisible();
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem('fcc-device-mode')))
    .toBe('kiosk');
  await page.reload();
  await page.getByRole('link', { name: 'Sign in to brew' }).click();
  await expect(page.getByText('Shared touch display')).toBeVisible();
  await expect(page.locator('input[aria-label="PIN"]')).toHaveCount(0);
  let throttleResponse = 0;
  await page.route('**/api/v1/auth/login', async (route) => {
    if (route.request().method() !== 'POST' || throttleResponse >= 2) {
      await route.continue();
      return;
    }
    throttleResponse += 1;
    await route.fulfill({
      status: 429,
      contentType: 'application/json',
      headers: throttleResponse === 2 ? { 'Retry-After': '30' } : {},
      body: JSON.stringify({ detail: 'Login traffic is temporarily limited.' })
    });
  });
  await enterKioskPin(page, '9999');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('alert')).toHaveText('Login traffic is temporarily limited.');
  await enterKioskPin(page, '9999');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('alert')).toContainText('Try again in 30 seconds');
  await expect(
    page.getByRole('group', { name: 'PIN', exact: true }).getByRole('button', { name: '1' })
  ).toBeDisabled();
  await page.getByLabel('Profile').selectOption({ label: 'Bob' });
  await expect(
    page.getByRole('group', { name: 'PIN', exact: true }).getByRole('button', { name: '2' })
  ).toBeEnabled();
  await page.unroute('**/api/v1/auth/login');
  await page.reload();
  await enterKioskPin(page, '9999');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('alert')).toContainText('Invalid profile or PIN');
  await enterKioskPin(page, '1234');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/brews\/new$/);
  await expect(page.locator(keyboardCapableControls)).toHaveCount(0);
  await expect(page.getByRole('button', { name: '+ Coffee' })).toHaveCount(0);
  await page.goto('/coffees');
  const kioskColliderCard = page
    .locator('article[data-testid="catalog-card"]')
    .filter({ has: page.getByRole('heading', { name: 'Collider Blend' }) });
  await expect(
    kioskColliderCard.getByRole('img', { name: 'PSI Roasters Collider Blend' })
  ).toBeVisible();
  await expect(kioskColliderCard.getByLabel('Replace photo')).toHaveCount(0);
  await expect(kioskColliderCard.getByRole('button', { name: 'Remove photo' })).toHaveCount(0);
  await expect(kioskColliderCard.getByRole('button', { name: /Edit|Clone|Archive/ })).toHaveCount(
    0
  );
  await page.goto('/brews/new');
  await page.getByRole('combobox', { name: 'Coffee', exact: true }).selectOption({
    label: 'Responsive Layout Review Roastery · Ethiopia Guji Hambela Buku Abel Extended Lot Name'
  });
  await page.getByRole('button', { name: /Light natural \/ fruity/ }).click();
  await page.getByRole('button', { name: /^Set Coffee dose;/ }).click();
  const doseDialog = page.getByRole('dialog', { name: 'Coffee dose', exact: true });
  await doseDialog.getByRole('button', { name: 'Clear value' }).click();
  await doseDialog.getByRole('button', { name: '0', exact: true }).click();
  await doseDialog.getByRole('button', { name: 'Apply' }).click();
  await expect(doseDialog.getByRole('alert')).toContainText('between 1 and 500');
  await doseDialog.getByRole('button', { name: 'Clear value' }).click();
  for (const character of '40.0') {
    await doseDialog.getByRole('button', { name: character, exact: true }).click();
  }
  await doseDialog.getByRole('button', { name: 'Apply' }).click();
  await page.getByRole('button', { name: /^Set Target flow;/ }).click();
  const flowDialog = page.getByRole('dialog', { name: 'Target flow', exact: true });
  await flowDialog.getByRole('button', { name: 'Unset value' }).click();
  await flowDialog.getByRole('button', { name: 'Apply' }).click();
  await setKioskNumber(page, 'Total water', '600');
  await page.getByRole('button', { name: 'Save and open brew mode' }).click();
  await expect(page.getByText('settings locked on screen')).toBeVisible();
  await expect(page.getByText('Ethiopia Guji Hambela Buku Abel Extended Lot Name')).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(() => {
        const metric = document.querySelector<HTMLElement>('.hero-metric');
        const value = metric?.querySelector<HTMLElement>('strong');
        const label = metric?.querySelector<HTMLElement>('span');
        if (!value || !label) return -1;
        return label.getBoundingClientRect().top - value.getBoundingClientRect().bottom;
      })
    )
    .toBeGreaterThanOrEqual(6);
  await expect
    .poll(() =>
      page.evaluate(() =>
        Boolean(
          (globalThis as typeof globalThis & { __wakeLockRequested?: boolean }).__wakeLockRequested
        )
      )
    )
    .toBe(true);
  await page.evaluate(() => sessionStorage.setItem('wake-lock-fail', '1'));
  await page.reload();
  await expect(page.getByRole('button', { name: 'Finish brew' })).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(() => {
        const finish = [...document.querySelectorAll('button')].find((item) =>
          item.textContent?.includes('Finish brew')
        );
        return Boolean(
          finish &&
          finish.getBoundingClientRect().bottom <= window.innerHeight &&
          document.documentElement.scrollWidth <= document.documentElement.clientWidth
        );
      })
    )
    .toBe(true);

  await page.getByRole('button', { name: 'Finish brew' }).click();
  await expect(page.locator(keyboardCapableControls)).toHaveCount(0);
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
  await setKioskNumber(page, 'Seconds', '5');
  await page.getByRole('button', { name: 'Finalize and invite tasters' }).click();
  await expect(page.getByRole('heading', { name: 'Taste. Scan. Rate.' })).toBeVisible();
  await expect(page.getByAltText(/QR code to rate/)).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth
      )
    )
    .toBe(true);

  const ratingPath = await page
    .getByRole('link', { name: 'Rate on this screen' })
    .getAttribute('href');
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
  for (let index = 0; index < (await flavorDisclosures.count()); index += 1) {
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
  await expect
    .poll(() =>
      phone.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth
      )
    )
    .toBe(true);
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
  await expect(page.locator(keyboardCapableControls)).toHaveCount(0);
  await enterKioskPin(page, '1234');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'How did it land?' })).toBeVisible();
  await page.getByRole('button', { name: 'Submit rating' }).click();
  await expect(page.getByRole('heading', { name: 'Thanks, Ada.' })).toBeVisible();
  await page.getByRole('button', { name: 'Done' }).click();
  await expect(page.getByRole('heading', { name: 'Taste. Scan. Rate.' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Sign in' })).toBeVisible();

  const invitationPath = new URL(page.url()).pathname;
  await page.goto('/coffees');
  await expect(page.locator(keyboardCapableControls)).toHaveCount(0);
  await expect(page.getByRole('button', { name: '+ Add coffee' })).toHaveCount(0);
  const brewedCoffeeCard = page.locator('article[data-testid="catalog-card"]').filter({
    has: page.getByRole('heading', {
      name: 'Ethiopia Guji Hambela Buku Abel Extended Lot Name'
    })
  });
  await brewedCoffeeCard
    .getByRole('link', {
      name: 'View details for Ethiopia Guji Hambela Buku Abel Extended Lot Name'
    })
    .click();
  await expect(page.getByRole('heading', { name: 'Recent completed brews.' })).toBeVisible();
  await expect(page.getByText('Average liking', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Ratings', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Edit', exact: true })).toHaveCount(0);
  await expect(page.locator(keyboardCapableControls)).toHaveCount(0);

  await page.goto('/equipment');
  await enterKioskPin(page, '1234');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'The club rack.' })).toBeVisible();
  await expect(page.locator(keyboardCapableControls)).toHaveCount(0);
  await expect(page.locator('.equipment-sections > .equipment-section')).toHaveCount(3);
  await expect(page.locator('.equipment-section.panel')).toHaveCount(0);
  await expect(page.getByRole('button', { name: /Edit|Archive|photo/i })).toHaveCount(0);
  const grinderCard = page
    .locator('article[data-testid="catalog-card"]')
    .filter({ has: page.getByRole('heading', { name: 'C40', exact: true }) });
  await grinderCard.getByRole('link', { name: 'View details for C40' }).click();
  await expect(page).toHaveURL(/\/equipment\/grinders\/\d+$/);
  await expect(page.getByRole('heading', { name: 'Recent completed brews.' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Edit', exact: true })).toHaveCount(0);
  await expect(page.locator(keyboardCapableControls)).toHaveCount(0);
  await page.goto('/equipment');
  await page.goto('/account/pin');
  await expect(page.locator(keyboardCapableControls)).toHaveCount(0);
  await enterKioskPin(page, '1234', 'Current PIN');
  await page.getByRole('button', { name: 'Continue' }).click();
  await enterKioskPin(page, '4321', 'New PIN');
  await page.getByRole('button', { name: 'Continue' }).click();
  await enterKioskPin(page, '4321', 'Repeat new PIN');
  await page.getByRole('button', { name: 'Change PIN' }).click();
  await expect(page.getByText('Your PIN has been changed.')).toBeVisible();
  await page.goto('/admin');
  await expect(
    page.getByRole('heading', { name: 'Administration is unavailable on this display.' })
  ).toBeVisible();
  await expect(page.locator(keyboardCapableControls)).toHaveCount(0);

  await page.goto(`/login?kiosk=0&next=${encodeURIComponent(invitationPath)}`);
  await expect(page.getByLabel('PIN')).toBeVisible();
  await page.getByLabel('PIN').fill('4321');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Taste. Scan. Rate.' })).toBeVisible();
  const personalRatingPath = await page
    .getByRole('link', { name: 'Rate on this screen' })
    .getAttribute('href');
  expect(personalRatingPath).toMatch(/^\/rate\//);
  await page.getByRole('link', { name: 'Rate on this screen' }).click();
  await expect(page).toHaveURL(/\/rate\//);
  await expect(page.getByRole('heading', { name: 'Thanks, Ada.' })).toBeVisible();
  await page.setViewportSize({ width: 768, height: 1024 });
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth
      )
    )
    .toBe(true);

  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto('/coffees');
  const signedBrewedCard = page.locator('article[data-testid="catalog-card"]').filter({
    has: page.getByRole('heading', {
      name: 'Ethiopia Guji Hambela Buku Abel Extended Lot Name'
    })
  });
  const desktopCatalogGeometry = await page.evaluate(() => {
    const actionBottoms = [...document.querySelectorAll<HTMLElement>('.catalog-actions')].map(
      (action) => action.getBoundingClientRect().bottom
    );
    return {
      actionBottomSpread: Math.max(...actionBottoms) - Math.min(...actionBottoms),
      noOverflow: document.documentElement.scrollWidth <= document.documentElement.clientWidth
    };
  });
  expect(desktopCatalogGeometry.actionBottomSpread).toBeLessThanOrEqual(1);
  expect(desktopCatalogGeometry.noOverflow).toBe(true);
  await signedBrewedCard
    .getByRole('link', {
      name: 'View details for Ethiopia Guji Hambela Buku Abel Extended Lot Name'
    })
    .click();
  await expect(page.getByText('Average liking', { exact: true })).toBeVisible();
  await expect(page.getByText('Ratings', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Recent completed brews.' })).toBeVisible();

  await page.goto('/coffees');
  const personalColliderCard = page
    .locator('article[data-testid="catalog-card"]')
    .filter({ has: page.getByRole('heading', { name: 'Collider Blend' }) })
    .first();
  await personalColliderCard.getByRole('link', { name: 'View details for Collider Blend' }).click();
  await page.getByText('More actions', { exact: true }).click();
  await page.getByRole('button', { name: 'Clone bag' }).click();
  await expect(page).toHaveURL(/\/coffees\/\d+\?edit=1$/);
  const clonedCoffeePath = new URL(page.url()).pathname;
  await expect(page.getByRole('heading', { name: 'Update bag details.' })).toBeVisible();
  await expect(page.getByLabel('Photo (optional)', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(page).not.toHaveURL(/edit=1/);
  await expect(page.getByRole('heading', { name: 'About this bag.' })).toBeVisible();
  await page.getByText('More actions', { exact: true }).click();
  await page.getByRole('button', { name: 'Archive', exact: true }).click();
  const archiveCoffeeDialog = page.getByRole('alertdialog', { name: 'Archive this coffee?' });
  await expect(archiveCoffeeDialog).toBeVisible();
  await archiveCoffeeDialog.getByRole('button', { name: 'Archive coffee' }).click();
  await expect(page).toHaveURL(/\/coffees\?message=/);
  await expect(page.getByRole('heading', { name: 'Collider Blend' })).toHaveCount(1);
  await page.goto(clonedCoffeePath);
  await expect(page.getByText('Archived', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Edit', exact: true })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Brew this' })).toHaveCount(0);

  await page.goto('/equipment');
  const personalGrinderCard = page
    .locator('article[data-testid="catalog-card"]')
    .filter({ has: page.getByRole('heading', { name: 'C40', exact: true }) });
  await personalGrinderCard.getByRole('link', { name: 'View details for C40' }).click();
  await page.getByRole('button', { name: 'Edit', exact: true }).click();
  await expect(page.getByLabel('Photo (optional)', { exact: true })).toBeVisible();
  await page.getByLabel('Guidance').fill('Temporary unsaved guidance');
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(page.getByText('Temporary unsaved guidance')).toHaveCount(0);
  await page.getByRole('button', { name: 'Edit', exact: true }).click();
  await page.getByLabel('Guidance').fill('Use a slightly coarser setting for larger brews.');
  await page.getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByRole('heading', { name: 'About this grinder.' })).toBeVisible();
  await expect(page.getByText('Use a slightly coarser setting for larger brews.')).toBeVisible();

  await page.goto(invitationPath);
  await page.getByRole('link', { name: 'Correct brew' }).click();
  await expect(page.getByRole('heading', { name: 'Correct the recorded brew.' })).toBeVisible();
  await page.getByRole('spinbutton', { name: 'Temperature' }).fill('93');
  await page.getByLabel('Seconds').fill('6');
  await page.getByRole('button', { name: 'Save correction' }).click();
  await expect(page.getByRole('heading', { name: 'Taste. Scan. Rate.' })).toBeVisible();
  await expect(page.getByText('93 °C', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Void brew' }).click();
  const voidDialog = page.getByRole('dialog', { name: 'Void this completed brew?' });
  await expect(voidDialog).toBeVisible();
  await voidDialog.getByRole('button', { name: 'Void completed brew' }).click();
  await expect(page.getByRole('heading', { name: 'This brew is voided.' })).toBeVisible();

  await page.goto('/brews/new');
  await page.getByRole('button', { name: 'Save and open brew mode' }).click();
  await page.getByRole('button', { name: 'Cancel brew' }).click();
  const cancelDialog = page.getByRole('dialog', { name: 'Cancel this draft?' });
  await expect(cancelDialog).toBeVisible();
  await cancelDialog.getByRole('button', { name: 'Cancel draft' }).click();
  await expect(page.getByRole('heading', { name: 'This brew is cancelled.' })).toBeVisible();

  await page.goto('/login?mode=kiosk');
  await expect(page.locator('input[aria-label="PIN"]')).toHaveCount(0);
  await expect(page.getByRole('group', { name: 'PIN', exact: true })).toBeVisible();
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem('fcc-device-mode')))
    .toBe('kiosk');
});
