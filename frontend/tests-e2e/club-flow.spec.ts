import { expect, test, type Page, type Route } from '@playwright/test';
import type {
  ActiveBrews,
  AppSettings,
  BrewActivityItem,
  Coffee,
  MattermostSettings,
  ProfileIdentity,
  Session
} from '../src/lib/types';

const e2eBaseURL = `http://127.0.0.1:${process.env.E2E_PORT ?? 8000}`;
import { fileURLToPath } from 'node:url';

const ethiopiaPhoto = fileURLToPath(
  new URL('../../backend/app/demo_assets/catalog/demo-coffee-ethiopia.webp', import.meta.url)
);
const colombiaPhoto = fileURLToPath(
  new URL('../../backend/app/demo_assets/catalog/demo-coffee-colombia.webp', import.meta.url)
);

const keyboardCapableControls =
  'input:not([type="range"]):not([type="radio"]):not([type="checkbox"]), textarea';

interface EditableFlavorTag {
  id: number;
  name: string;
  parent_id: number | null;
  active: boolean;
  sort_order: number;
}

interface CoffeeRatingInsightsFixture {
  coffee_id: number;
  aggregate: Record<string, unknown>;
  rated_brew_count: number;
  rated_brews: Array<{
    brew: { id: number; completed_at: string | null; [key: string]: unknown };
    aggregate: Record<string, unknown>;
  }>;
  next_offset: number | null;
}

const publicAppSettings: AppSettings = {
  app_name: 'Filter Coffee Club',
  app_version: 'v2026.08.5',
  subtitle: 'Brew activity test',
  public_base_url: null,
  logo_path: null,
  brewing_logo_path: '/brand/filter-coffee-club-brewing.svg',
  color_cream: '#f6f1e8',
  color_surface: '#fffdfc',
  color_ink: '#241c19',
  color_coffee: '#6b3f2a',
  color_cyan: '#00728f',
  color_amber: '#d88700',
  max_active_brews: 2,
  public_url_needs_configuration: false,
  demo_mode: false,
  demo_notice: null,
  demo_pin: null,
  demo_profile_names: []
};

const patMattermostSettings: MattermostSettings = {
  enabled: false,
  server_url: 'https://mattermost.web.cern.ch',
  auth_mode: 'pat',
  credential_configured: false,
  encryption_available: true,
  credential_status: 'not_configured',
  account_user_id: null,
  account_username: null,
  team_id: null,
  team_name: null,
  channel_id: null,
  channel_name: null,
  channel_display_name: null,
  announce_brew_started: false,
  mention_channel_on_started: false,
  announce_ready_to_rate: false,
  mention_channel_on_ready: false,
  last_tested_at: null,
  last_delivery_at: null,
  last_error_at: null,
  last_error: null,
  pending_count: 0,
  failed_count: 0
};

function fulfillJson(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body)
  });
}

async function mockSignedOutHome(page: Page, appSettings: AppSettings = publicAppSettings) {
  await page.route('**/api/v1/settings', (route) => fulfillJson(route, appSettings));
  await page.route('**/api/v1/auth/bootstrap-status', (route) =>
    fulfillJson(route, { required: false })
  );
  await page.route('**/api/v1/auth/me', (route) =>
    fulfillJson(route, { detail: 'Not authenticated' }, 401)
  );
  await page.route('**/api/v1/brews?*', (route) => fulfillJson(route, []));
}

function railBrew(id: number, coffeeName: string, token: string | null = null): BrewActivityItem {
  return {
    id,
    coffee_name: coffeeName,
    coffee_roaster: 'Test Roaster',
    operators: [{ id: 1, display_name: 'Ada' }],
    status: token ? 'completed' : 'draft',
    rating_token: token
  };
}

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

async function completeRequiredRatingScales(page: Page) {
  const responses: [string, string][] = [
    ['Overall liking', '8'],
    ['Acidity', '3'],
    ['Bitterness', '2'],
    ['Sweetness', '4'],
    ['Body', '3']
  ];
  for (const [name, value] of responses) {
    await page.getByRole('slider', { name, exact: true }).fill(value);
  }
}

async function loginAda(page: Page, deviceMode: 'personal' | 'kiosk' = 'personal') {
  const bootstrapStatus = await page.context().request.get('/api/v1/auth/bootstrap-status');
  expect(bootstrapStatus.ok()).toBeTruthy();
  if (((await bootstrapStatus.json()) as { required: boolean }).required) {
    const response = await page.context().request.post('/api/v1/auth/bootstrap', {
      data: { display_name: 'Ada', pin: '4321', device_mode: deviceMode }
    });
    expect(response.ok()).toBeTruthy();
    return (await response.json()) as Session;
  }

  const profilesResponse = await page.context().request.get('/api/v1/auth/profiles');
  expect(profilesResponse.ok()).toBeTruthy();
  const profiles = (await profilesResponse.json()) as ProfileIdentity[];
  const ada = profiles.find((profile) => profile.display_name === 'Ada');
  if (!ada) throw new Error('The Ada test profile is unavailable.');

  for (const pin of ['4321', '1234']) {
    const response = await page.context().request.post('/api/v1/auth/login', {
      data: { profile_id: ada.id, pin, device_mode: deviceMode }
    });
    if (response.ok()) return (await response.json()) as Session;
  }
  throw new Error('The Ada test profile could not be authenticated.');
}

async function createLifecycleCoffee(page: Page, session: Session, name: string) {
  const response = await page.context().request.post('/api/v1/coffees', {
    headers: { 'X-CSRF-Token': session.csrf_token },
    data: { roaster: 'Lifecycle Roasters', name }
  });
  expect(response.ok()).toBeTruthy();
  return (await response.json()) as Coffee;
}

test('Pi operator brews, then phone and kiosk tasters rate', async ({ page, browser }) => {
  test.setTimeout(120_000);
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'wakeLock', {
      configurable: true,
      value: {
        request: async () => {
          if (sessionStorage.getItem('wake-lock-fail')) throw new Error('Wake Lock unavailable');
          (
            globalThis as typeof globalThis & { __wakeLockRequested?: boolean }
          ).__wakeLockRequested = true;
          return {
            release: async () => {
              if (sessionStorage.getItem('wake-lock-release-fail')) {
                throw new Error('Wake Lock release failed');
              }
            }
          };
        }
      }
    });
  });
  await page.goto('/?kiosk=1');
  await expect(page).toHaveURL(/\/setup$/);
  await expect(
    page.getByRole('heading', { name: 'Complete setup on a phone or computer.' })
  ).toBeVisible();
  await expect(page.getByTestId('brew-activity-rail')).toHaveCount(0);
  await expect(page.locator(keyboardCapableControls)).toHaveCount(0);
  await page.getByRole('button', { name: 'Check again' }).click();
  await expect(page.getByRole('alert')).toContainText('Setup is not complete yet');

  await page.goto('/setup?kiosk=0');

  await page.getByLabel('Your display name').fill('Ada');
  await page.getByLabel('Four-digit PIN').fill('1234');
  await page.getByLabel('Repeat PIN').fill('1234');
  await page.getByRole('button', { name: 'Create administrator' }).click();
  await expect(page).toHaveURL(/\/admin$/);
  await expect(page.getByTestId('start-brew-chip')).toContainText('Start a brew');

  const peopleTab = page.getByRole('tab', { name: 'People' });
  await page.goto('/admin?tab=unknown');
  await expect(page).toHaveURL(/\/admin$/);
  await expect(peopleTab).toHaveAttribute('aria-selected', 'true');
  await page.goto('/admin?tab=people');
  await expect(page).toHaveURL(/\/admin$/);
  await expect(peopleTab).toHaveAttribute('aria-selected', 'true');
  await page.goto('/admin?tab=data');
  await expect(page.getByRole('tab', { name: 'Data' })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('heading', { name: 'Exports' })).toBeVisible();
  await peopleTab.click();
  await expect(page).toHaveURL(/\/admin$/);
  await expect(page.getByRole('tab')).toHaveCount(5);
  await expect(peopleTab).toHaveAttribute('aria-selected', 'true');
  await peopleTab.focus();
  await page.keyboard.press('ArrowRight');
  const equipmentTab = page.getByRole('tab', { name: 'Equipment' });
  await expect(page).toHaveURL(/\/admin\?tab=equipment$/);
  await expect(equipmentTab).toHaveAttribute('aria-selected', 'true');
  await expect(equipmentTab).toBeFocused();
  await expect(page.getByRole('heading', { name: 'Add grinder', exact: true })).toBeVisible();
  const grinderModel = page.getByRole('combobox', { name: 'Grinder model' });
  await expect(grinderModel.getByRole('option', { name: 'Comandante C40' })).toBeAttached();
  await expect(grinderModel.getByRole('option', { name: 'KINGrinder K6' })).toBeAttached();
  await expect(grinderModel.getByRole('option', { name: 'Custom' })).toBeAttached();
  await grinderModel.selectOption('kingrinder_k6');
  await expect(page.getByText(/C40 × 3.2/)).toBeVisible();
  await grinderModel.selectOption('custom');
  await expect(page.getByLabel('Setting unit')).toBeVisible();
  const firstOptionalRange = page.locator('.custom-ranges .preset-range').first();
  const optionalMinimum = firstOptionalRange.getByRole('spinbutton', { name: 'Minimum' });
  const optionalMaximum = firstOptionalRange.getByRole('spinbutton', { name: 'Maximum' });
  await optionalMinimum.fill('20');
  await expect(optionalMaximum).toHaveAttribute('required', '');
  await optionalMaximum.fill('30');
  await optionalMinimum.fill('');
  await expect(optionalMinimum).toHaveAttribute('required', '');
  await optionalMaximum.fill('');
  await expect(optionalMinimum).not.toHaveAttribute('required', '');
  await expect(optionalMaximum).not.toHaveAttribute('required', '');
  await peopleTab.click();
  await expect(page).toHaveURL(/\/admin$/);
  await expect(peopleTab).toHaveAttribute('aria-selected', 'true');

  const settingsTab = page.getByRole('tab', { name: 'Settings' });
  const historyLengthBeforeTabSwitch = await page.evaluate(() => history.length);
  await settingsTab.click();
  await expect(page).toHaveURL(/\/admin\?tab=settings$/);
  expect(await page.evaluate(() => history.length)).toBe(historyLengthBeforeTabSwitch);
  await page.reload();
  await expect(settingsTab).toHaveAttribute('aria-selected', 'true');
  const parallelBrews = page.getByLabel('Maximum parallel brews');
  await expect(parallelBrews).toHaveValue('2');
  await parallelBrews.fill('3');
  const raisedParallelBrews = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/v1/settings') &&
      response.request().method() === 'PUT' &&
      response.ok()
  );
  await page.getByRole('button', { name: 'Save settings' }).click();
  await raisedParallelBrews;
  await expect(page.getByText('Settings saved.')).toBeVisible();
  await parallelBrews.fill('2');
  const resetParallelBrews = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/v1/settings') &&
      response.request().method() === 'PUT' &&
      response.ok()
  );
  await page.getByRole('button', { name: 'Save settings' }).click();
  await resetParallelBrews;

  const mattermostForm = page.locator('.mattermost-form');
  await expect(mattermostForm.getByRole('heading', { name: 'Mattermost' })).toBeVisible();
  await expect(mattermostForm.getByLabel('Authentication')).toHaveValue('webhook');
  const mattermostServer = mattermostForm.getByRole('textbox', {
    name: /^Mattermost server/
  });
  await expect(mattermostServer).toHaveValue('https://mattermost.web.cern.ch');
  await mattermostServer.fill(e2eBaseURL);
  const webhookInput = mattermostForm.getByLabel('Incoming webhook URL');
  await webhookInput.fill(`${e2eBaseURL}/hooks/e2e-webhook-secret`);
  await mattermostForm.getByLabel('Enabled').check();
  await mattermostForm.getByLabel('Post when a brew starts').check();
  const saveMattermost = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/v1/settings/mattermost') &&
      response.request().method() === 'PUT' &&
      response.ok()
  );
  await mattermostForm.getByRole('button', { name: 'Save Mattermost settings' }).click();
  const mattermostResponse = await saveMattermost;
  expect(JSON.stringify(await mattermostResponse.json())).not.toContain('e2e-webhook-secret');
  await expect(page.getByText('Mattermost settings saved.')).toBeVisible();
  await expect(webhookInput).toHaveValue('');
  await expect(webhookInput).toHaveAttribute('placeholder', /Stored securely/);
  const sendMattermostTest = mattermostForm.getByRole('button', { name: 'Send test message' });
  await expect(sendMattermostTest).toBeEnabled();
  await mattermostServer.fill('http://localhost:8000');
  await expect(sendMattermostTest).toBeDisabled();
  await expect(
    page.getByText('Save destination or credential changes before testing.')
  ).toBeVisible();
  await expect(
    page.getByText('Re-enter the credential when changing the Mattermost server.')
  ).toBeVisible();
  await mattermostServer.fill(e2eBaseURL);
  await expect(sendMattermostTest).toBeEnabled();
  const clearMattermost = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/v1/settings/mattermost/credential') &&
      response.request().method() === 'DELETE' &&
      response.ok()
  );
  await mattermostForm.getByRole('button', { name: 'Remove credential' }).click();
  await clearMattermost;
  await expect(page.getByText(/credential removed and notifications disabled/i)).toBeVisible();
  await peopleTab.click();

  await page.getByRole('tab', { name: 'Presets & flavors' }).click();
  const presetCreator = page.locator('.preset-creator');
  await presetCreator.getByLabel('Name').fill('Club balanced');
  await presetCreator.getByLabel('Ratio').fill('16.5');
  await presetCreator.getByLabel('Comandante C40 reference minimum clicks').fill('24');
  await presetCreator.getByLabel('Comandante C40 reference maximum clicks').fill('28');
  await presetCreator.getByRole('button', { name: 'Add preset' }).click();
  await expect(page.getByText('Preset added.')).toBeVisible();
  await expect(page.getByLabel('Preset name').last()).toHaveValue('Club balanced');
  await peopleTab.click();

  await page.setViewportSize({ width: 393, height: 851 });
  await expect(page.getByTestId('start-brew-chip')).toBeVisible();
  const mobileRailLayout = await page.getByTestId('brew-activity-rail').evaluate((rail) => {
    const chip = rail.querySelector<HTMLElement>('[data-testid="start-brew-chip"]');
    const track = rail.firstElementChild as HTMLElement | null;
    return {
      chipHeight: chip?.getBoundingClientRect().height ?? 0,
      chipFits: Boolean(track && track.scrollWidth <= track.clientWidth),
      pageFits: document.documentElement.scrollWidth <= document.documentElement.clientWidth
    };
  });
  expect(mobileRailLayout.chipHeight).toBeGreaterThanOrEqual(44);
  expect(mobileRailLayout.chipFits).toBe(true);
  expect(mobileRailLayout.pageFits).toBe(true);
  const menuButton = page.getByRole('button', { name: 'Menu' });
  const mainNavigation = page.getByRole('navigation', { name: 'Main navigation' });
  await expect(menuButton).toBeVisible();
  await expect(mainNavigation).toBeHidden();
  await menuButton.click();
  await expect(menuButton).toHaveAttribute('aria-expanded', 'true');
  await expect(page.getByRole('link', { name: 'Members' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Admin' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Ada', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Sign out', exact: true })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(menuButton).toHaveAttribute('aria-expanded', 'false');
  await expect(menuButton).toBeFocused();
  const adminSectionSelect = page.getByRole('combobox', { name: 'Admin section', exact: true });
  await expect(adminSectionSelect).toBeVisible();
  await adminSectionSelect.selectOption('equipment');
  await expect(page).toHaveURL(/\/admin\?tab=equipment$/);
  await expect(page.getByRole('heading', { name: 'Add grinder', exact: true })).toBeVisible();
  await adminSectionSelect.selectOption('people');
  await expect(page).toHaveURL(/\/admin$/);
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
  const bobAdminRow = page.locator('.item-list article').filter({
    has: page.getByLabel('Require PIN change for Bob')
  });
  await expect(bobAdminRow.getByRole('link', { name: 'View profile' })).toHaveAttribute(
    'href',
    /\/profiles\/\d+/
  );
  await expect(bobAdminRow.getByLabel('Display name for Bob')).toBeVisible();
  await expect(bobAdminRow.getByLabel('Role for Bob')).toBeVisible();
  await expect(bobAdminRow.getByLabel('New PIN for Bob')).toBeVisible();
  await expect(bobAdminRow.getByLabel('Require PIN change for Bob')).toBeVisible();
  await expect(bobAdminRow.getByRole('button', { name: 'Save' })).toBeEnabled();
  await expect(bobAdminRow.getByRole('button', { name: 'Deactivate' })).toBeEnabled();
  const longDisplayName = 'B'.repeat(80);
  await page.getByLabel('Display name for Bob', { exact: true }).fill(longDisplayName);
  for (const viewport of [
    { width: 1280, height: 720 },
    { width: 1024, height: 600 },
    { width: 901, height: 800 },
    { width: 900, height: 800 },
    { width: 393, height: 851 },
    { width: 320, height: 568 }
  ]) {
    await page.setViewportSize(viewport);
    await expect
      .poll(() =>
        page.locator('.profiles-panel').evaluate((panel) => {
          const panelBounds = panel.getBoundingClientRect();
          const controls = panel.querySelectorAll<HTMLElement>(
            '.profile-row input, .profile-row select, .profile-row button, .profile-row a, .pin-required'
          );
          return {
            pageFits: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
            controlsFit: [...controls].every((control) => {
              const bounds = control.getBoundingClientRect();
              return bounds.left >= panelBounds.left && bounds.right <= panelBounds.right + 0.5;
            })
          };
        })
      )
      .toEqual({ pageFits: true, controlsFit: true });
  }
  await page.setViewportSize({ width: 1024, height: 600 });
  await page.getByLabel(`Display name for ${longDisplayName}`, { exact: true }).fill('Bob');

  await page.goto('/profiles');
  await expect(page.getByRole('heading', { name: 'Members', exact: true })).toBeVisible();
  const adaMemberCard = page.locator('.member-card').filter({ hasText: 'Ada' });
  const bobMemberCard = page.locator('.member-card').filter({ hasText: 'Bob' });
  await expect(adaMemberCard.getByText('You', { exact: true })).toBeVisible();
  await expect(adaMemberCard.getByText('No ratings yet', { exact: true })).toBeVisible();
  await expect(bobMemberCard.getByText('No ratings yet', { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 393, height: 851 });
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth
      )
    )
    .toBe(true);
  await page.setViewportSize({ width: 1024, height: 600 });
  await page.route('**/api/v1/profiles', async (route) => {
    await route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Directory temporarily unavailable' })
    });
  });
  await page.reload();
  await expect(
    page.getByRole('heading', { name: 'Profiles are temporarily unavailable.' })
  ).toBeVisible();
  await page.unroute('**/api/v1/profiles');
  await page.getByRole('button', { name: 'Try again' }).click();
  await expect(bobMemberCard).toBeVisible();

  await page.goto('/coffees');
  await page.getByRole('button', { name: '+ Add coffee' }).click();
  await page.getByLabel('Roaster / brand').fill('PSI Roasters');
  await page.getByLabel('Coffee name').fill('Collider Blend');
  await page.getByLabel('Purchased from').fill('CERN Restaurant 1, Meyrin');
  await expect(page.getByRole('button', { name: 'Automatic' })).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  await page.getByLabel('Custom chart color').fill('#fffdfc');
  await expect(page.getByText(/difficult to see against the current surface color/)).toBeVisible();
  await page.getByLabel('Photo (optional)', { exact: true }).setInputFiles(ethiopiaPhoto);
  await expect(page.getByRole('img', { name: 'Selected catalog item' })).toBeVisible();
  await page.getByRole('button', { name: 'Edit framing' }).click();
  const uploadFramingDialog = page.getByRole('dialog', { name: 'Adjust framing' });
  await expect(uploadFramingDialog).toBeVisible();
  await expect(uploadFramingDialog.getByText('Gallery preview')).toBeVisible();
  await expect(uploadFramingDialog.getByText('Detail preview')).toBeVisible();
  await uploadFramingDialog.getByRole('button', { name: 'Use full image' }).click();
  await expect(uploadFramingDialog.getByLabel('Zoom')).toBeDisabled();
  await uploadFramingDialog.getByRole('button', { name: 'Center and fill' }).click();
  await expect(uploadFramingDialog.getByLabel('Zoom')).toBeEnabled();
  const galleryFramingArea = uploadFramingDialog.getByRole('button', {
    name: /Gallery photo framing area/
  });
  const horizontalPosition = uploadFramingDialog.getByLabel('Horizontal position');
  await galleryFramingArea.focus();
  await page.keyboard.press('ArrowRight');
  expect(Number(await horizontalPosition.inputValue())).toBeGreaterThan(0.5);
  await uploadFramingDialog.getByLabel('Zoom').fill('1.45');
  await horizontalPosition.fill('0.22');
  await uploadFramingDialog.getByLabel('Vertical position').fill('0.68');
  const framingBox = await galleryFramingArea.boundingBox();
  expect(framingBox).not.toBeNull();
  if (framingBox) {
    await page.mouse.move(
      framingBox.x + framingBox.width / 2,
      framingBox.y + framingBox.height / 2
    );
    await page.mouse.down();
    await page.mouse.move(
      framingBox.x + framingBox.width / 2 + 30,
      framingBox.y + framingBox.height / 2 - 20
    );
    await page.mouse.up();
  }
  expect(Number(await horizontalPosition.inputValue())).not.toBe(0.22);
  await uploadFramingDialog.getByRole('button', { name: 'Apply framing' }).click();
  await expect(page.getByText('Custom framing applied')).toBeVisible();
  let coffeeCreateRequests = 0;
  let coffeeCreationKey = '';
  await page.route('**/api/v1/coffees', async (route) => {
    if (route.request().method() === 'POST') {
      coffeeCreateRequests += 1;
      coffeeCreationKey = route.request().headers()['idempotency-key'] ?? '';
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    await route.continue();
  });
  await page.getByRole('button', { name: 'Save coffee' }).click();
  await page.locator('form.create-panel').dispatchEvent('submit');
  await expect(page.getByRole('button', { name: 'Saving coffee…' })).toBeDisabled();
  await expect(page.getByRole('heading', { name: 'Collider Blend' })).toBeVisible();
  await page.unroute('**/api/v1/coffees');
  expect(coffeeCreateRequests).toBe(1);
  expect(coffeeCreationKey).toMatch(/^[0-9a-f-]{36}$/);
  const colliderCard = page
    .locator('article[data-testid="catalog-card"]')
    .filter({ has: page.getByRole('heading', { name: 'Collider Blend' }) });
  const colliderPhoto = colliderCard.getByRole('img', { name: 'PSI Roasters Collider Blend' });
  await expect(colliderPhoto).toBeVisible();
  await expect(colliderCard.getByText('Purchased from CERN Restaurant 1, Meyrin')).toBeVisible();
  await expect(colliderPhoto).toHaveClass(/framed/);
  await expect(colliderPhoto).toHaveAttribute('style', /scale\(1\.45\)/);
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
  await page.route(/\/api\/v1\/coffees\?include_archived=true$/, (route) =>
    route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Temporary color peer failure' })
    })
  );
  await colliderCard.getByRole('link', { name: 'View details for Collider Blend' }).click();
  await expect(page).toHaveURL(/\/coffees\/\d+$/);
  await expect(page.getByRole('heading', { name: 'About this bag.' })).toBeVisible();
  await expect(page.getByText('CERN Restaurant 1, Meyrin', { exact: true })).toBeVisible();
  await expect(
    page.getByTestId('detail-photo').getByRole('img', { name: 'PSI Roasters Collider Blend' })
  ).toHaveAttribute('style', /scale\(1\.45\)/);
  await page.unroute(/\/api\/v1\/coffees\?include_archived=true$/);
  await expect(page.locator('input, textarea, select')).toHaveCount(0);
  await page.getByRole('button', { name: 'Edit', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Update bag details.' })).toBeVisible();
  await expect(page.getByLabel('Custom chart color')).toHaveValue('#fffdfc');
  await page.getByLabel('Roaster / brand').fill('Temporary roaster');
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'About this bag.' })).toBeVisible();
  await expect(page.getByText('PSI Roasters', { exact: true }).first()).toBeVisible();
  await expect(page.locator('input, textarea, select')).toHaveCount(0);
  await page.getByRole('button', { name: 'Edit', exact: true }).click();
  await page.getByLabel('Purchased from').fill('PSI West Cafeteria, Villigen');
  await page
    .getByLabel('Replacement photo (optional)', { exact: true })
    .setInputFiles(colombiaPhoto);
  await page.getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByRole('heading', { name: 'About this bag.' })).toBeVisible();
  await expect(page.getByText('PSI West Cafeteria, Villigen', { exact: true })).toBeVisible();
  const detailPhoto = page
    .getByTestId('detail-photo')
    .getByRole('img', { name: 'PSI Roasters Collider Blend', exact: true });
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

  await page.getByRole('button', { name: 'Edit', exact: true }).click();
  await page.setViewportSize({ width: 393, height: 851 });
  await page.getByRole('button', { name: 'Edit framing' }).click();
  const mobileFramingDialog = page.getByRole('dialog', { name: 'Adjust framing' });
  await expect(mobileFramingDialog).toBeVisible();
  const mobileEditorGeometry = await mobileFramingDialog.evaluate((dialog) => {
    const box = dialog.getBoundingClientRect();
    const controls = [...dialog.querySelectorAll<HTMLElement>('button, input')];
    const visibleActions = [...dialog.querySelectorAll<HTMLButtonElement>('.editor-actions button')]
      .map((button) => button.getBoundingClientRect())
      .every((action) => action.top >= 0 && action.bottom <= window.innerHeight);
    return {
      fitsViewport: box.left >= 0 && box.right <= window.innerWidth,
      noPageOverflow: document.documentElement.scrollWidth <= window.innerWidth,
      visibleActions,
      touchSizedActions: controls
        .filter((control) => control instanceof HTMLButtonElement)
        .every((control) => control.getBoundingClientRect().height >= 44)
    };
  });
  expect(mobileEditorGeometry.fitsViewport).toBe(true);
  expect(mobileEditorGeometry.noPageOverflow).toBe(true);
  expect(mobileEditorGeometry.visibleActions).toBe(true);
  expect(mobileEditorGeometry.touchSizedActions).toBe(true);
  await mobileFramingDialog.getByLabel('Zoom').fill('1.7');
  await mobileFramingDialog.getByLabel('Horizontal position').fill('0.72');
  await mobileFramingDialog.getByLabel('Vertical position').fill('0.3');
  await mobileFramingDialog.getByRole('button', { name: 'Apply framing' }).click();
  await page.getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByRole('heading', { name: 'About this bag.' })).toBeVisible();
  await expect(detailPhoto).toHaveClass(/framed/);
  await expect(detailPhoto).toHaveAttribute('style', /scale\(1\.7\)/);
  await page.reload();
  await expect(detailPhoto).toHaveAttribute('style', /scale\(1\.7\)/);
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
  await page.getByLabel('Purchased from').fill('  MAME, Zurich  ');
  await page.getByLabel('Custom chart color').fill('#fffdfc');
  await expect(page.getByText(/Also used by PSI Roasters · Collider Blend/)).toBeVisible();
  let failInlineCoffee = true;
  const inlineCoffeeCreationKeys: string[] = [];
  await page.route('**/api/v1/coffees', async (route) => {
    if (route.request().method() === 'POST') {
      inlineCoffeeCreationKeys.push(route.request().headers()['idempotency-key'] ?? '');
      if (failInlineCoffee) {
        failInlineCoffee = false;
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Temporary coffee failure' })
        });
        return;
      }
    }
    await route.continue();
  });
  await inlineSave.click();
  await expect(page.getByRole('alert')).toHaveText('Temporary coffee failure');
  await expect(inlineRoaster).toHaveValue('Responsive Layout Review Roastery');
  await expect(inlineCoffeeName).toHaveValue('Ethiopia Guji Hambela Buku Abel Extended Lot Name');
  await inlineSave.click();
  await expect(
    page.getByRole('combobox', { name: 'Coffee', exact: true }).locator('option:checked')
  ).toHaveText(
    'Responsive Layout Review Roastery · Ethiopia Guji Hambela Buku Abel Extended Lot Name'
  );
  await page.unroute('**/api/v1/coffees');
  expect(inlineCoffeeCreationKeys).toHaveLength(2);
  expect(inlineCoffeeCreationKeys[0]).toMatch(/^[0-9a-f-]{36}$/);
  expect(new Set(inlineCoffeeCreationKeys).size).toBe(1);

  await page.goto('/coffees');
  const inlineCoffeeCard = page.locator('article[data-testid="catalog-card"]').filter({
    has: page.getByRole('heading', {
      name: 'Ethiopia Guji Hambela Buku Abel Extended Lot Name'
    })
  });
  await expect(inlineCoffeeCard.getByText('Purchased from MAME, Zurich')).toBeVisible();

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
  await page.getByRole('button', { name: /^Set Total coffee dose;/ }).click();
  const doseDialog = page.getByRole('dialog', { name: 'Total coffee dose', exact: true });
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
  await expect(
    page.getByRole('heading', {
      name: 'Ethiopia Guji Hambela Buku Abel Extended Lot Name',
      exact: true
    })
  ).toBeVisible();
  await expect(page.getByTestId('active-brew-chip')).toContainText(
    'Ethiopia Guji Hambela Buku Abel Extended Lot Name'
  );
  await expect(page.getByTestId('start-brew-chip')).toContainText('+ New brew');
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
  const operatorDialogTrigger = page.getByRole('button', { name: 'Change primary operator' });
  await operatorDialogTrigger.click();
  const kioskOperatorDialog = page.getByRole('dialog', { name: 'Change primary operator' });
  await expect(kioskOperatorDialog).toBeVisible();
  const operatorSelect = kioskOperatorDialog.getByLabel('New operator');
  await expect(operatorSelect).toHaveValue('1');
  await expect(operatorSelect).toBeFocused();
  await kioskOperatorDialog.getByRole('button', { name: 'Keep current operator' }).click();
  await expect(operatorDialogTrigger).toBeFocused();
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
  await expect(page.getByTestId('active-brew-chip')).toHaveCount(0);
  await expect(page.getByTestId('rating-brew-chip')).toContainText(
    'Ethiopia Guji Hambela Buku Abel Extended Lot Name'
  );
  await expect(page.getByTestId('rating-brew-chip')).toHaveAttribute('href', /\/rate\//);
  await expect(page.getByTestId('start-brew-chip')).toContainText('+ New brew');
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
  const mobileRatingPath = new URL(ratingPath!, e2eBaseURL).searchParams.get('next');
  expect(mobileRatingPath).toContain('/rate/');
  const phoneContext = await browser.newContext({
    baseURL: e2eBaseURL,
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
  await expect(phone.getByRole('button', { name: 'Submit rating' })).toBeDisabled();
  const unchangedMidpoint = phone.getByRole('slider', { name: 'Overall liking', exact: true });
  await unchangedMidpoint.focus();
  await unchangedMidpoint.press('Space');
  await expect(phone.locator('output[for="rating-liking"]')).toHaveText('5 / 9');
  await expect(phone.getByRole('button', { name: 'Submit rating' })).toBeDisabled();
  await completeRequiredRatingScales(phone);
  await phone.getByRole('button', { name: 'Submit rating' }).click();
  await expect(phone.getByRole('heading', { name: 'Thanks, Bob.' })).toBeVisible();
  const phoneRadar = phone.getByRole('img', { name: /Broad flavour profile/ });
  await expect(phoneRadar).toHaveAttribute('aria-label', /Fruity: 1 of 1 taster \(100%\)/);
  await expect(phone.locator('[data-testid="flavor-radar"] .axis-label')).toHaveCount(8);
  await expect(phone.locator('.result-panel .tags')).toContainText('Grape · 1');
  const mobileRadarLayout = await phone
    .locator('[data-testid="flavor-radar"]')
    .evaluate((radar) => {
      const svg = radar.querySelector('svg');
      const panel = radar.closest<HTMLElement>('.result-panel');
      if (!svg || !panel) return null;
      const svgBox = svg.getBoundingClientRect();
      const panelBox = panel.getBoundingClientRect();
      return {
        contained: svgBox.left >= panelBox.left && svgBox.right <= panelBox.right + 1,
        pageFits: document.documentElement.scrollWidth <= document.documentElement.clientWidth
      };
    });
  expect(mobileRadarLayout).toEqual({ contained: true, pageFits: true });

  const adminApiContext = await browser.newContext({ baseURL: e2eBaseURL });
  const profilesResponse = await adminApiContext.request.get('/api/v1/auth/profiles');
  expect(profilesResponse.ok()).toBe(true);
  const adminProfiles = (await profilesResponse.json()) as { id: number; display_name: string }[];
  const ada = adminProfiles.find((profile) => profile.display_name === 'Ada');
  const bob = adminProfiles.find((profile) => profile.display_name === 'Bob');
  expect(ada).toBeDefined();
  expect(bob).toBeDefined();
  const adminLoginResponse = await adminApiContext.request.post('/api/v1/auth/login', {
    data: { profile_id: ada!.id, pin: '1234', device_mode: 'personal' }
  });
  expect(adminLoginResponse.ok()).toBe(true);
  const adminSession = (await adminLoginResponse.json()) as { csrf_token: string };
  const allFlavorTagsResponse = await adminApiContext.request.get(
    '/api/v1/flavor-tags?active_only=false'
  );
  expect(allFlavorTagsResponse.ok()).toBe(true);
  const allFlavorTags = (await allFlavorTagsResponse.json()) as EditableFlavorTag[];
  const updateFlavorTag = async (
    tag: EditableFlavorTag,
    updates: Partial<Pick<EditableFlavorTag, 'name' | 'active'>>
  ) => {
    const response = await adminApiContext.request.put(`/api/v1/flavor-tags/${tag.id}`, {
      headers: { 'X-CSRF-Token': adminSession.csrf_token },
      data: {
        name: updates.name ?? tag.name,
        parent_id: tag.parent_id,
        active: updates.active ?? tag.active,
        sort_order: tag.sort_order
      }
    });
    expect(response.ok()).toBe(true);
  };

  const grapeTag = allFlavorTags.find((tag) => tag.name === 'Grape');
  expect(grapeTag).toBeDefined();
  await updateFlavorTag(grapeTag!, { active: false });
  await phone.reload();
  await expect(phone.getByRole('img', { name: /Broad flavour profile/ })).toHaveAttribute(
    'aria-label',
    /Fruity: 1 of 1 taster \(100%\)/
  );
  await expect(phone.locator('.result-panel .tags')).toContainText('Grape · 1');
  await phone.getByRole('button', { name: 'Edit my rating' }).click();
  await expect(phone.getByRole('button', { name: 'Grape', exact: true })).toHaveCount(0);
  await updateFlavorTag(grapeTag!, { active: true });
  await phone.reload();

  await phone.getByRole('button', { name: 'Edit my rating' }).click();
  for (const flavor of ['Fruity · general', 'Grape', 'Citrus', 'Stone fruit']) {
    await phone.getByRole('button', { name: flavor, exact: true }).click();
  }
  await phone.getByRole('button', { name: 'Submit rating' }).click();
  await expect(phone.getByText('No broad flavour notes yet.', { exact: true })).toBeVisible();
  await expect(phone.getByRole('img', { name: /Broad flavour profile/ })).toHaveAttribute(
    'aria-label',
    /Fruity: 0 of 1 taster \(0%\)/
  );

  await phone.getByRole('button', { name: 'Edit my rating' }).click();
  await phone.getByRole('button', { name: 'Fruity · general', exact: true }).click();
  await phone.getByRole('button', { name: 'Submit rating' }).click();
  await expect(phone.getByRole('img', { name: /Broad flavour profile/ })).toHaveAttribute(
    'aria-label',
    /Fruity: 1 of 1 taster \(100%\)/
  );
  await expect(phone.locator('.result-panel .tags')).toContainText('Fruity · 1');

  const sweetCategory = allFlavorTags.find((tag) => tag.parent_id === null && tag.name === 'Sweet');
  expect(sweetCategory).toBeDefined();
  const longCategoryName =
    'An exceptionally descriptive broad flavour category used for layout testing';
  await updateFlavorTag(sweetCategory!, { name: longCategoryName });
  await phone.reload();
  const longLabelRadar = phone.getByRole('img', { name: /Broad flavour profile/ });
  expect(await longLabelRadar.getAttribute('aria-label')).toContain(longCategoryName);
  const visibleAxisLabels = await phone
    .locator('[data-testid="flavor-radar"] .axis-label')
    .allTextContents();
  expect(visibleAxisLabels).not.toContain(longCategoryName);
  expect(visibleAxisLabels.join('')).toContain('…');
  await expect
    .poll(() =>
      phone.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth
      )
    )
    .toBe(true);
  await updateFlavorTag(sweetCategory!, { name: sweetCategory!.name });

  const parentTags = allFlavorTags
    .filter((tag) => tag.parent_id === null)
    .sort(
      (left, right) => left.sort_order - right.sort_order || left.name.localeCompare(right.name)
    );
  for (const tag of parentTags.slice(2)) await updateFlavorTag(tag, { active: false });
  await phone.reload();
  await expect(phone.locator('[data-testid="flavor-radar"] .category-bar')).toHaveCount(2);
  await expect(phone.locator('[data-testid="flavor-radar"] svg')).toHaveCount(0);
  await updateFlavorTag(parentTags[1], { active: false });
  await phone.reload();
  await expect(phone.locator('[data-testid="flavor-radar"] .category-bar')).toHaveCount(1);
  await updateFlavorTag(parentTags[0], { active: false });
  await phone.reload();
  await expect(
    phone.getByText('No broad flavour categories configured.', { exact: true })
  ).toBeVisible();
  await expect(phone.locator('[data-testid="flavor-radar"] [role="img"]')).toHaveAttribute(
    'aria-label',
    /Broad flavour profile for .+\. No broad flavour categories are configured\./
  );
  for (const tag of parentTags) await updateFlavorTag(tag, { active: true });
  await phone.reload();
  await expect(phone.locator('[data-testid="flavor-radar"] .axis-label')).toHaveCount(8);
  await adminApiContext.close();

  await phone.setViewportSize({ width: 768, height: 1024 });
  await expect
    .poll(() =>
      phone.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth
      )
    )
    .toBe(true);
  await phone.setViewportSize({ width: 360, height: 800 });
  await phone.goto('/profiles');
  const bobOwnMemberCard = phone.locator('.member-card').filter({ hasText: 'Bob' });
  const adaUnsharedMemberCard = phone.locator('.member-card').filter({ hasText: 'Ada' });
  await expect(bobOwnMemberCard.getByText('You', { exact: true })).toBeVisible();
  await expect(bobOwnMemberCard.getByText('1 brew rated', { exact: true })).toBeVisible();
  await expect(
    adaUnsharedMemberCard.getByText('No shared ratings yet', { exact: true })
  ).toBeVisible();
  await expect
    .poll(() =>
      phone.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth
      )
    )
    .toBe(true);
  await phone.goto('/analytics');
  await expect(phone.getByRole('heading', { name: 'Find the useful signal.' })).toBeVisible();
  await expect(
    phone.locator('.operator-list').getByRole('link', { name: 'Ada', exact: true })
  ).toBeVisible();
  const settingsChart = phone.locator('.chart-panel').filter({
    has: phone.getByRole('heading', { name: 'Settings versus liking' })
  });
  await expect(settingsChart.locator('.x-tick')).not.toHaveCount(0);
  await expect(settingsChart.getByText('Brew ratio (1:x)', { exact: true })).toBeVisible();
  await expect(settingsChart.getByText('Liking (1–9)', { exact: true })).toBeVisible();
  await expect(settingsChart.locator('option[value="overall_throughput_g_s"]')).toHaveText(
    'Overall throughput'
  );

  const recipeMap = phone.locator('.recipe-map');
  await expect(recipeMap.getByRole('heading', { name: 'Recipe map' })).toBeVisible();
  const mapCoffee = recipeMap.getByRole('combobox', { name: 'Map coffee', exact: true });
  const mapXAxis = recipeMap.getByRole('combobox', { name: 'X axis', exact: true });
  const mapYAxis = recipeMap.getByRole('combobox', { name: 'Y axis', exact: true });
  const mapColour = recipeMap.getByRole('combobox', { name: 'Colour', exact: true });
  await expect(mapCoffee).toHaveValue(/^\d+$/);
  const selectedMapCoffee = await mapCoffee.inputValue();
  await mapCoffee.selectOption('');
  await expect(
    recipeMap.getByText('Choose one coffee to compare recipes without mixing different beans.', {
      exact: true
    })
  ).toBeVisible();
  await mapCoffee.selectOption(selectedMapCoffee);
  await expect(mapXAxis).toHaveValue('ratio');
  await expect(mapYAxis).toHaveValue('temperature_c');
  await expect(mapColour).toHaveValue('liking');
  await expect(mapXAxis.locator('option[value="temperature_c"]')).toHaveAttribute('disabled', '');
  await expect(mapYAxis.locator('option[value="ratio"]')).toHaveAttribute('disabled', '');
  const mapLegend = recipeMap.getByTestId('color-legend');
  await expect(mapLegend).toContainText('1');
  await expect(mapLegend).toContainText('9');
  await expect(mapLegend).toContainText('Liking average');
  const mapPoint = recipeMap.locator('.plot-point').first();
  await mapPoint.tap();
  await expect(phone).toHaveURL(/\/analytics$/);
  await expect(recipeMap.getByTestId('point-details')).toContainText('Selected brew');
  await expect(recipeMap.getByTestId('point-details')).toContainText(/range · 1 rating/);
  await expect(recipeMap.getByRole('link', { name: 'Open brew' })).toHaveAttribute(
    'href',
    /\/brews\/\d+/
  );
  await mapColour.selectOption('acidity');
  await expect(mapLegend).toContainText('0');
  await expect(mapLegend).toContainText('5');
  await expect(mapLegend).toContainText('Acidity average');

  await mapXAxis.selectOption('grinder_setting');
  await expect(
    recipeMap.getByText('Choose one grinder before comparing grinder settings.', { exact: true })
  ).toBeVisible();
  const mapGrinder = recipeMap.getByRole('combobox', { name: 'Map grinder', exact: true });
  await mapGrinder.selectOption({ index: 1 });
  await expect(recipeMap.locator('.plot-point')).not.toHaveCount(0);
  await expect(mapYAxis.locator('option[value="grinder_setting"]')).toHaveAttribute('disabled', '');

  const coffeeFilter = phone.getByRole('combobox', { name: 'Coffee', exact: true });
  const axisFilter = phone.getByRole('combobox', { name: 'Horizontal axis', exact: true });
  const mobileCoffeeBox = await coffeeFilter.boundingBox();
  const mobileAxisBox = await axisFilter.boundingBox();
  expect(mobileCoffeeBox).not.toBeNull();
  expect(mobileAxisBox).not.toBeNull();
  expect(Math.abs(mobileCoffeeBox!.x - mobileAxisBox!.x)).toBeLessThanOrEqual(1);
  expect(Math.abs(mobileCoffeeBox!.width - mobileAxisBox!.width)).toBeLessThanOrEqual(1);
  expect(mobileAxisBox!.y).toBeGreaterThan(mobileCoffeeBox!.y + mobileCoffeeBox!.height);
  const mobileMapCoffeeBox = await mapCoffee.boundingBox();
  const mobileMapXAxisBox = await mapXAxis.boundingBox();
  expect(mobileMapCoffeeBox).not.toBeNull();
  expect(mobileMapXAxisBox).not.toBeNull();
  expect(Math.abs(mobileMapCoffeeBox!.x - mobileMapXAxisBox!.x)).toBeLessThanOrEqual(1);
  expect(mobileMapXAxisBox!.y).toBeGreaterThan(mobileMapCoffeeBox!.y + mobileMapCoffeeBox!.height);
  await expect
    .poll(() =>
      phone.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth
      )
    )
    .toBe(true);
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
  await completeRequiredRatingScales(page);
  await page.getByRole('button', { name: 'Submit rating' }).click();
  await expect(page.getByRole('heading', { name: 'Thanks, Ada.' })).toBeVisible();
  await expect(page.getByRole('img', { name: /Broad flavour profile/ })).toHaveAttribute(
    'aria-label',
    /Fruity: 1 of 2 tasters \(50%\)/
  );
  await expect(page.locator('.result-panel .tags')).toContainText('Fruity · 1');

  const memberContext = await browser.newContext({
    baseURL: e2eBaseURL,
    viewport: { width: 393, height: 851 }
  });
  const memberLoginResponse = await memberContext.request.post('/api/v1/auth/login', {
    data: { profile_id: bob!.id, pin: '1357', device_mode: 'personal' }
  });
  expect(memberLoginResponse.ok()).toBe(true);
  const memberPage = await memberContext.newPage();
  await memberPage.goto('/profiles');
  const adaSharedMemberCard = memberPage.locator('.member-card').filter({ hasText: 'Ada' });
  await expect(adaSharedMemberCard.getByText('1 shared brew', { exact: true })).toBeVisible();
  await adaSharedMemberCard.click();
  await expect(memberPage.getByRole('heading', { name: 'Ada', exact: true })).toBeVisible();
  await expect(memberPage.locator('.profile-hero .lede')).toContainText(
    '1 brew rated in common with you.'
  );
  await memberContext.close();

  await page.getByRole('button', { name: 'Done' }).click();
  await expect(page.getByRole('heading', { name: 'Taste. Scan. Rate.' })).toBeVisible();
  await expect(
    page.getByLabel('Main navigation').getByRole('link', { name: 'Sign in' })
  ).toBeVisible();
  const signedOutNavTypography = await page.getByLabel('Main navigation').evaluate((navigation) => {
    const links = [...navigation.querySelectorAll('a')];
    const coffees = links.find((link) => link.textContent?.trim() === 'Coffees');
    const signIn = links.find((link) => link.textContent?.trim() === 'Sign in');
    if (!coffees || !signIn) return null;
    const coffeeStyle = getComputedStyle(coffees);
    const signInStyle = getComputedStyle(signIn);
    return {
      coffee: [coffeeStyle.fontSize, coffeeStyle.fontWeight, coffeeStyle.padding],
      signIn: [signInStyle.fontSize, signInStyle.fontWeight, signInStyle.padding]
    };
  });
  expect(signedOutNavTypography?.signIn).toEqual(signedOutNavTypography?.coffee);

  const invitationPath = new URL(page.url()).pathname;
  await page.goto('/profiles');
  await expect(page).toHaveURL(/\/login\?.*next=%2Fprofiles/);
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
  await expect(
    page.locator('.recent-section').getByRole('link', { name: 'Ada', exact: true })
  ).toHaveCount(0);
  await expect(
    page.getByRole('heading', { name: 'Sign in to see the club’s tasting analysis.' })
  ).toBeVisible();
  await expect(page.getByRole('heading', { name: 'What the club tasted.' })).toHaveCount(0);
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
  await expect(page.getByText('Average ratio', { exact: true })).toBeVisible();
  await expect(page.getByText('Average temperature', { exact: true })).toBeVisible();
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
  await expect(
    page.locator('.invitation').getByRole('link', { name: 'Ada', exact: true })
  ).toHaveAttribute('href', '/profiles/1');
  await expect(page.getByRole('heading', { name: 'How this brew landed.' })).toBeVisible();
  await expect(page.getByRole('img', { name: /Broad flavour profile for brew/ })).toHaveAttribute(
    'aria-label',
    /Fruity: 1 of 2 tasters \(50%\)/
  );
  await page.route('**/api/v1/brews/*/rating-insights', async (route) => {
    const response = await route.fetch();
    const body = (await response.json()) as {
      flavor_axes: Array<{ id: number; label: string; mentions: number; total: number }>;
    };
    await route.fulfill({
      response,
      json: {
        ...body,
        count: 0,
        averages: {},
        flavor_axes: body.flavor_axes.map((axis) => ({ ...axis, mentions: 0, total: 0 }))
      }
    });
  });
  await page.reload();
  await expect(page.locator('.group-results .radar-zero-label')).toHaveText(
    'No broad flavour notes yet.'
  );
  await expect(page.getByRole('img', { name: /Broad flavour profile for brew/ })).toHaveAttribute(
    'aria-label',
    /Fruity: 0 of 0 tasters \(0%\)/
  );
  await page.unroute('**/api/v1/brews/*/rating-insights');
  await page.reload();
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

  await page.route('**/api/v1/ratings/me/comparisons*', async (route) => {
    await route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Temporary comparison failure' })
    });
  });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Past brews' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'My rating profile' })).toBeVisible();
  await expect(
    page.getByText('Past brews are available, but your comparisons could not load.')
  ).toBeVisible();
  await expect(page.getByText('Your rating vs other tasters')).toHaveCount(0);
  await page.unroute('**/api/v1/ratings/me/comparisons*');
  await page.reload();
  const ratedBrewCard = page.locator('.brew-card').filter({
    has: page.getByRole('heading', {
      name: 'Ethiopia Guji Hambela Buku Abel Extended Lot Name'
    })
  });
  await expect(ratedBrewCard.getByText('Your rating vs other tasters')).toBeVisible();
  for (const metric of ['Liking', 'Acidity', 'Bitterness', 'Sweetness', 'Body']) {
    await expect(ratedBrewCard.getByText(metric, { exact: true })).toBeVisible();
  }
  const compactComparisonLayout = await ratedBrewCard.evaluate((card) => {
    const comparison = card.querySelector<HTMLElement>('.rating-comparison');
    const cells = [...card.querySelectorAll<HTMLElement>('.comparison-cell')];
    const supportingText = card.querySelector<HTMLElement>('.comparison-cell small');
    if (!comparison || cells.length !== 5 || !supportingText) return null;
    const comparisonBox = comparison.getBoundingClientRect();
    const firstBox = cells[0].getBoundingClientRect();
    const secondBox = cells[1].getBoundingClientRect();
    const thirdBox = cells[2].getBoundingClientRect();
    return {
      likingSpansWidth: Math.abs(firstBox.width - comparisonBox.width) <= 1,
      twoColumnRows: Math.abs(secondBox.y - thirdBox.y) <= 1,
      supportingTextSize: Number.parseFloat(getComputedStyle(supportingText).fontSize),
      contained: cells.every((cell) => {
        const box = cell.getBoundingClientRect();
        return box.left >= comparisonBox.left && box.right <= comparisonBox.right + 1;
      }),
      overflowingElements: [...document.querySelectorAll<HTMLElement>('body *')]
        .filter((element) => {
          const box = element.getBoundingClientRect();
          return box.left < -1 || box.right > document.documentElement.clientWidth + 1;
        })
        .slice(0, 10)
        .map((element) => `${element.tagName.toLowerCase()}.${String(element.className)}`)
    };
  });
  expect(compactComparisonLayout?.likingSpansWidth).toBe(true);
  expect(compactComparisonLayout?.twoColumnRows).toBe(true);
  expect(compactComparisonLayout?.supportingTextSize).toBeGreaterThanOrEqual(11.5);
  expect(compactComparisonLayout?.contained).toBe(true);
  expect(compactComparisonLayout?.overflowingElements).toEqual([]);

  let firstProfileRating: Record<string, unknown> | null = null;
  await page.route('**/api/v1/profiles/*/ratings?*', async (route) => {
    const response = await route.fetch();
    const body = (await response.json()) as {
      rating_count: number;
      next_offset: number | null;
      ratings: Record<string, unknown>[];
    };
    const offset = new URL(route.request().url()).searchParams.get('offset');
    if (offset === '0' && body.ratings.length > 0) {
      firstProfileRating = body.ratings[0];
      await route.fulfill({
        response,
        json: { ...body, rating_count: 2, next_offset: 1 }
      });
      return;
    }
    if (offset === '1' && firstProfileRating) {
      const olderRating = structuredClone(firstProfileRating) as {
        brew: { id: number; coffee_name: string };
      };
      olderRating.brew.id += 10_000;
      olderRating.brew.coffee_name = 'Earlier test brew';
      await route.fulfill({
        response,
        json: { ...body, rating_count: 2, ratings: [olderRating], next_offset: null }
      });
      return;
    }
    await route.fulfill({ response });
  });
  await ratedBrewCard.getByRole('link', { name: 'Full details' }).click();
  await expect(page.getByRole('heading', { name: 'Ada', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Most-liked coffees.' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Rating history.' })).toBeVisible();
  await expect(page.getByText('You chose')).toBeVisible();
  await expect(page.getByText('Other tasters chose')).toBeVisible();
  await page.getByRole('button', { name: 'Load more ratings' }).click();
  await expect(page.getByRole('heading', { name: 'Earlier test brew' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Load more ratings' })).toHaveCount(0);
  await page.unroute('**/api/v1/profiles/*/ratings?*');

  await page.goto('/profiles');
  const ratedBobCard = page.locator('.member-card').filter({ hasText: 'Bob' });
  await expect(ratedBobCard.getByText('1 brew rated', { exact: true })).toBeVisible();
  await ratedBobCard.click();
  await expect(page.getByRole('heading', { name: 'Bob', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Menu' }).click();
  await expect(page.getByRole('link', { name: 'Members' })).toHaveClass(/active/);
  await expect(page.getByRole('link', { name: 'Ada', exact: true })).not.toHaveClass(/active/);
  await page.getByRole('link', { name: 'Ada', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Ada', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Menu' }).click();
  await expect(page.getByRole('link', { name: 'Ada', exact: true })).toHaveClass(/active/);
  await expect(page.getByRole('link', { name: 'Members' })).not.toHaveClass(/active/);

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

  let firstCoffeeBrewInsight: CoffeeRatingInsightsFixture['rated_brews'][number] | null = null;
  await page.route('**/api/v1/coffees/*/rating-insights?*', async (route) => {
    const response = await route.fetch();
    const body = (await response.json()) as CoffeeRatingInsightsFixture;
    const offset = new URL(route.request().url()).searchParams.get('offset');
    if (offset === '0' && body.rated_brews.length > 0) {
      firstCoffeeBrewInsight = body.rated_brews[0];
      await route.fulfill({
        response,
        json: { ...body, rated_brew_count: 2, next_offset: 1 }
      });
      return;
    }
    if (offset === '1' && firstCoffeeBrewInsight) {
      const older = structuredClone(firstCoffeeBrewInsight);
      older.brew.id += 10_000;
      older.brew.completed_at = '2026-07-01T12:00:00Z';
      await route.fulfill({
        response,
        json: { ...body, rated_brews: [older], rated_brew_count: 2, next_offset: null }
      });
      return;
    }
    await route.fulfill({ response });
  });
  await signedBrewedCard
    .getByRole('link', {
      name: 'View details for Ethiopia Guji Hambela Buku Abel Extended Lot Name'
    })
    .click();
  const tastingSection = page.locator('.tasting-section');
  await expect(page.getByRole('heading', { name: 'What the club tasted.' })).toBeVisible();
  for (const metric of ['Liking', 'Acidity', 'Bitterness', 'Sweetness', 'Body', 'Ratings']) {
    await expect(tastingSection.getByText(metric, { exact: true })).toBeVisible();
  }
  const aggregateMetrics = tastingSection.getByTestId('rating-metrics');
  await expect(
    aggregateMetrics.locator('.rating-metric').filter({ hasText: 'Liking' })
  ).toContainText('/9');
  for (const metric of ['Acidity', 'Bitterness', 'Sweetness', 'Body']) {
    await expect(
      aggregateMetrics.locator('.rating-metric').filter({ hasText: metric })
    ).toContainText('/5');
  }
  for (const removedMetric of [
    'Average ratio',
    'Average temperature',
    'Average brew time',
    'Average throughput'
  ]) {
    await expect(page.getByText(removedMetric, { exact: true })).toHaveCount(0);
  }
  await expect(tastingSection.getByRole('img', { name: /Broad flavour profile/ })).toHaveAttribute(
    'aria-label',
    /Fruity: 1 of 2 responses \(50%\)/
  );
  const comparisonGrid = page.locator('[data-testid="brew-comparison-grid"]');
  await expect(page.locator('[data-testid="brew-comparison-card"]')).toHaveCount(1);
  const firstComparisonCard = page.locator('[data-testid="brew-comparison-card"]').first();
  await expect(firstComparisonCard.getByRole('link', { name: 'Ada', exact: true })).toHaveAttribute(
    'href',
    '/profiles/1'
  );
  for (const contextLabel of ['Ratio', 'Temperature', 'Grinder', 'Brew time', 'Throughput']) {
    await expect(firstComparisonCard.getByText(contextLabel, { exact: true })).toBeVisible();
  }
  await expect(
    firstComparisonCard.getByRole('img', { name: /Broad flavour profile for brew/ })
  ).toHaveAttribute('aria-label', /Fruity: 1 of 2 tasters \(50%\)/);
  const firstBrewLink = firstComparisonCard.getByRole('link', { name: 'View brew' });
  const loadMoreBrews = page.getByRole('button', { name: 'Load more brews' });
  await firstBrewLink.focus();
  await page.keyboard.press('Tab');
  await expect(loadMoreBrews).toBeFocused();
  expect(
    await comparisonGrid.evaluate(
      (grid) => getComputedStyle(grid).gridTemplateColumns.split(' ').length
    )
  ).toBe(2);
  await loadMoreBrews.click();
  await expect(page.locator('[data-testid="brew-comparison-card"]')).toHaveCount(2);
  await expect(page.getByRole('button', { name: 'Load more brews' })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Recent completed brews.' })).toBeVisible();
  await expect(
    page.locator('.recent-section').getByRole('link', { name: 'Ada', exact: true }).first()
  ).toHaveAttribute('href', '/profiles/1');
  for (const viewport of [
    { width: 768, height: 1024 },
    { width: 393, height: 851 }
  ]) {
    await page.setViewportSize(viewport);
    expect(
      await comparisonGrid.evaluate(
        (grid) => getComputedStyle(grid).gridTemplateColumns.split(' ').length
      )
    ).toBe(1);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth
      )
    ).toBe(true);
  }
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.unroute('**/api/v1/coffees/*/rating-insights?*');

  await page.goto('/coffees');
  const personalColliderCard = page
    .locator('article[data-testid="catalog-card"]')
    .filter({ has: page.getByRole('heading', { name: 'Collider Blend' }) })
    .first();
  await personalColliderCard.getByRole('link', { name: 'View details for Collider Blend' }).click();

  const coffeeMoreActions = page.locator('details.more-actions');
  if ((await coffeeMoreActions.getAttribute('open')) === null) {
    await page.getByText('More actions', { exact: true }).click();
  }
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
  await expect(
    page.getByText(/predefined grinder’s identity and adjustment specifications/)
  ).toBeVisible();
  await expect(page.getByLabel('Guidance')).toHaveCount(0);
  await page.getByLabel('Photo (optional)', { exact: true }).setInputFiles(colombiaPhoto);
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await page.getByRole('button', { name: 'Edit', exact: true }).click();
  await page.getByLabel('Photo (optional)', { exact: true }).setInputFiles(colombiaPhoto);
  await page.getByRole('button', { name: 'Edit framing' }).click();
  const equipmentFramingDialog = page.getByRole('dialog', { name: 'Adjust framing' });
  await equipmentFramingDialog.getByLabel('Zoom').fill('1.3');
  await equipmentFramingDialog.getByRole('button', { name: 'Apply framing' }).click();
  await page.getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByRole('heading', { name: 'About this grinder.' })).toBeVisible();
  await expect(page.getByText('Predefined', { exact: true })).toBeVisible();
  await expect(
    page.getByTestId('detail-photo').getByRole('img', { name: 'Comandante C40' })
  ).toHaveClass(/framed/);

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
  await expect(page.getByRole('main')).toBeFocused();

  await page.evaluate(() => sessionStorage.removeItem('wake-lock-fail'));
  await page.goto(`/login?kiosk=0&next=${encodeURIComponent('/brews/new')}`);
  await page.getByLabel('Profile').selectOption({ label: 'Bob' });
  await page.getByLabel('PIN').fill('1357');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/brews\/new$/);
  await page.getByRole('button', { name: /Medium washed \/ balanced/ }).click();
  await page.getByRole('button', { name: 'Save and open brew mode' }).click();
  await expect(page).toHaveURL(/\/brews\/\d+$/);
  const reassignmentPath = new URL(page.url()).pathname;
  await expect(
    page.getByRole('main').getByRole('link', { name: 'Bob', exact: true })
  ).toBeVisible();
  await page.getByRole('button', { name: 'Change primary operator' }).click();
  const memberHandoffDialog = page.getByRole('dialog', { name: 'Change primary operator' });
  await memberHandoffDialog.getByLabel('New operator').selectOption({ label: 'Ada' });
  await memberHandoffDialog.getByRole('button', { name: 'Change primary operator' }).click();
  await expect(page).toHaveURL(new RegExp(`${reassignmentPath}$`));
  await expect(
    page.getByRole('main').getByRole('link', { name: 'Ada', exact: true })
  ).toBeVisible();
  await expect(
    page.getByRole('main').getByRole('link', { name: 'Bob', exact: true })
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Change primary operator' })).toHaveCount(0);
  await expect(page.getByRole('main')).toBeFocused();
  await page.getByRole('button', { name: 'Finish brew' }).click();
  await page.getByRole('button', { name: 'Finalize and invite tasters' }).click();
  const reassignedInvitationPath = new URL(page.url()).pathname;
  await expect(
    page.getByRole('main').getByRole('link', { name: 'Ada', exact: true })
  ).toBeVisible();
  await expect(
    page.getByRole('main').getByRole('link', { name: 'Bob', exact: true })
  ).toBeVisible();

  await page.goto(`/login?kiosk=0&next=${encodeURIComponent(reassignedInvitationPath)}`);
  await page.getByLabel('Profile').selectOption({ label: 'Ada' });
  await page.getByLabel('PIN').fill('4321');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(new RegExp(`${reassignedInvitationPath}$`));

  const bobProfileId = await page.evaluate(async () => {
    const response = await fetch('/api/v1/auth/profiles');
    const activeProfiles = (await response.json()) as { id: number; display_name: string }[];
    return activeProfiles.find((profile) => profile.display_name === 'Bob')?.id ?? 0;
  });
  expect(bobProfileId).toBeGreaterThan(0);
  const setBobActive = async (active: boolean) => {
    const status = await page.evaluate(
      async ({ profileId, nextActive }) => {
        const sessionResponse = await fetch('/api/v1/auth/me');
        const session = (await sessionResponse.json()) as { csrf_token: string };
        const response = await fetch(`/api/v1/people/${profileId}`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': session.csrf_token
          },
          body: JSON.stringify({ active: nextActive })
        });
        return response.status;
      },
      { profileId: bobProfileId, nextActive: active }
    );
    expect(status).toBe(200);
  };
  await setBobActive(false);
  await page.reload();
  await expect(
    page.locator('.invitation').getByRole('link', { name: 'Bob', exact: true })
  ).toHaveAttribute('href', `/profiles/${bobProfileId}`);
  await page.goto('/profiles');
  await expect(page.locator('.member-card').filter({ hasText: 'Bob' })).toHaveCount(0);
  await setBobActive(true);

  await page.goto(`/login?kiosk=0&next=${encodeURIComponent(reassignedInvitationPath)}`);
  await page.getByLabel('Profile').selectOption({ label: 'Bob' });
  await page.getByLabel('PIN').fill('1357');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('link', { name: 'Correct brew' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Void brew' })).toHaveCount(0);

  await page.goto(`/login?kiosk=0&next=${encodeURIComponent('/brews/new')}`);
  await page.getByLabel('Profile').selectOption({ label: 'Ada' });
  await page.getByLabel('PIN').fill('4321');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/brews\/new$/);
  await page.getByRole('button', { name: /Medium washed \/ balanced/ }).click();
  await page.getByRole('button', { name: 'Save and open brew mode' }).click();
  await page.getByRole('button', { name: 'Cancel brew' }).click();
  const cancelDialog = page.getByRole('dialog', { name: 'Cancel this draft?' });
  await expect(cancelDialog).toBeVisible();
  await cancelDialog.getByRole('button', { name: 'Cancel draft' }).click();
  await expect(page.getByRole('heading', { name: 'This brew is cancelled.' })).toBeVisible();
  await expect(page.getByRole('main')).toBeFocused();
  await expect(page.getByTestId('active-brew-chip')).toHaveCount(0);
  await expect(page.getByTestId('start-brew-chip')).toContainText('+ New brew');

  await page.goto('/brews/new');
  await page.getByRole('button', { name: /Medium washed \/ balanced/ }).click();
  await page.getByRole('button', { name: 'Save and open brew mode' }).click();
  await expect(page).toHaveURL(/\/brews\/\d+$/);
  await expect(
    page.getByRole('main').getByRole('link', { name: 'Ada', exact: true })
  ).toBeVisible();
  await expect(page.getByTestId('active-brew-chip')).toHaveCount(1);
  await expect(page.getByTestId('start-brew-chip')).toContainText('+ New brew');
  const collaborativeBrewPath = new URL(page.url()).pathname;
  const bobContext = await browser.newContext({ viewport: { width: 393, height: 851 } });
  const bobPhone = await bobContext.newPage();
  await bobPhone.goto(`/login?kiosk=0&next=${encodeURIComponent(collaborativeBrewPath)}`);
  await bobPhone.getByLabel('Profile').selectOption({ label: 'Bob' });
  await bobPhone.getByLabel('PIN').fill('1357');
  const bobLogin = bobPhone.waitForResponse(
    (response) =>
      response.url().endsWith('/api/v1/auth/login') &&
      response.request().method() === 'POST' &&
      response.ok()
  );
  const bobBrewLoad = bobPhone.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1${collaborativeBrewPath}`) &&
      response.request().method() === 'GET' &&
      response.ok()
  );
  await bobPhone.getByRole('button', { name: 'Sign in' }).click();
  await Promise.all([bobLogin, bobBrewLoad]);
  await expect(bobPhone).toHaveURL(new RegExp(`${collaborativeBrewPath}$`));
  await expect(bobPhone.getByRole('button', { name: 'Join brew' })).toBeVisible();
  await bobPhone.getByRole('button', { name: 'Join brew' }).click();
  await expect(bobPhone.getByRole('button', { name: 'Finish brew' })).toBeVisible();
  await bobPhone.getByRole('link', { name: 'Edit recipe' }).click();
  await bobPhone.getByRole('spinbutton', { name: 'Temperature' }).fill('91');
  await bobPhone.getByRole('button', { name: 'Save and return to brew mode' }).click();
  await expect(page.getByText('91 °C', { exact: true })).toBeVisible({ timeout: 8_000 });

  await page.getByRole('link', { name: 'Edit recipe' }).click();
  await bobPhone.getByRole('link', { name: 'Edit recipe' }).click();
  await bobPhone.getByRole('spinbutton', { name: 'Temperature' }).fill('92');
  await bobPhone.getByRole('button', { name: 'Save and return to brew mode' }).click();
  await expect(page.getByText('This brew changed on another device.')).toBeVisible({
    timeout: 8_000
  });

  await bobPhone.goto('/brews/new');
  await bobPhone.getByRole('button', { name: /Medium washed \/ balanced/ }).click();
  await bobPhone.getByRole('button', { name: 'Save and open brew mode' }).click();
  await expect(bobPhone).toHaveURL(/\/brews\/\d+$/);
  await expect(bobPhone.getByTestId('active-brew-chip')).toHaveCount(2);
  await expect(bobPhone.getByTestId('start-brew-chip')).toHaveCount(0);
  const secondParallelBrewPath = new URL(bobPhone.url()).pathname;
  await page.goto('/');
  await expect(page.getByRole('heading', { name: '2 of 2 active' })).toBeVisible();
  await expect(page.getByTestId('active-brew-chip')).toHaveCount(2);
  await expect(page.getByTestId('start-brew-chip')).toHaveCount(0);
  await expect(page.getByText('Brew capacity reached', { exact: true })).toBeVisible();
  await expect(page.locator('.brew-card .status.draft')).toHaveCount(0);
  await page.goto('/brews/new');
  await expect(page.getByRole('heading', { name: '2 of 2 brews are active.' })).toBeVisible();

  await bobPhone.goto(secondParallelBrewPath);
  await bobPhone.getByRole('button', { name: 'Cancel brew' }).click();
  await bobPhone
    .getByRole('dialog', { name: 'Cancel this draft?' })
    .getByRole('button', { name: 'Cancel draft' })
    .click();
  await expect(page.getByRole('button', { name: 'Save and open brew mode' })).toBeVisible({
    timeout: 8_000
  });
  await expect(page.getByTestId('active-brew-chip')).toHaveCount(1);
  await expect(page.getByTestId('start-brew-chip')).toContainText('+ New brew');

  await bobPhone.goto(collaborativeBrewPath);
  await expect(bobPhone.getByRole('button', { name: 'Finish brew' })).toBeVisible();
  await page.goto(collaborativeBrewPath);
  await page.getByRole('button', { name: 'Cancel brew' }).click();
  await page
    .getByRole('dialog', { name: 'Cancel this draft?' })
    .getByRole('button', { name: 'Cancel draft' })
    .click();
  await expect(bobPhone.getByRole('heading', { name: 'This brew is cancelled.' })).toBeVisible({
    timeout: 8_000
  });
  await expect(page.getByTestId('active-brew-chip')).toHaveCount(0);
  await expect(page.getByTestId('start-brew-chip')).toContainText('+ New brew');
  await bobContext.close();

  await page.goto('/');
  await page.getByRole('button', { name: 'Repeat' }).first().click();
  await expect(page).toHaveURL(/\/brews\/\d+$/);
  await expect(page.getByTestId('active-brew-chip')).toHaveCount(1);
  await expect(page.getByTestId('start-brew-chip')).toContainText('+ New brew');
  await page.getByRole('button', { name: 'Cancel brew' }).click();
  await page
    .getByRole('dialog', { name: 'Cancel this draft?' })
    .getByRole('button', { name: 'Cancel draft' })
    .click();
  await expect(page.getByRole('heading', { name: 'This brew is cancelled.' })).toBeVisible();
  await expect(page.getByTestId('active-brew-chip')).toHaveCount(0);
  await expect(page.getByTestId('start-brew-chip')).toContainText('+ New brew');

  await page.goto('/login?mode=kiosk');
  await expect(page.locator('input[aria-label="PIN"]')).toHaveCount(0);
  await expect(page.getByRole('group', { name: 'PIN', exact: true })).toBeVisible();
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem('fcc-device-mode')))
    .toBe('kiosk');
});

test('members can finish and restore coffee while kiosk details stay read-only', async ({
  page
}) => {
  const personalSession = await loginAda(page);
  const coffee = await createLifecycleCoffee(page, personalSession, 'Detail lifecycle bag');

  await page.goto(`/coffees/${coffee.id}`);
  await page.getByText('More actions', { exact: true }).click();
  await page.getByRole('button', { name: 'Mark bag empty' }).click();
  const finishDialog = page.getByRole('alertdialog', { name: 'Mark this bag empty?' });
  await finishDialog.getByRole('button', { name: 'Mark bag empty' }).click();
  await expect(page.getByText('Finished', { exact: true }).first()).toBeVisible();
  await expect(page.getByRole('link', { name: 'Brew this' })).toHaveCount(0);

  await page.goto('/coffees');
  const finishedSection = page.locator('details.finished-section');
  await finishedSection.getByText('Finished bags', { exact: true }).click();
  const finishedCard = finishedSection.locator('article[data-testid="catalog-card"]').filter({
    has: page.getByRole('heading', { name: coffee.name, exact: true })
  });
  await expect(finishedCard.getByText('Finished', { exact: true })).toBeVisible();

  await page.evaluate(() => localStorage.setItem('fcc-device-mode', 'kiosk'));
  await loginAda(page, 'kiosk');
  await page.goto(`/coffees/${coffee.id}`);
  await expect(page.getByText('More actions', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Brew this' })).toHaveCount(0);

  await page.evaluate(() => localStorage.setItem('fcc-device-mode', 'personal'));
  await loginAda(page);
  await page.goto(`/coffees/${coffee.id}`);
  await page.getByText('More actions', { exact: true }).click();
  await page.getByRole('button', { name: 'Make available again' }).click();
  const restoreDialog = page.getByRole('alertdialog', {
    name: 'Make this bag available again?'
  });
  await restoreDialog.getByRole('button', { name: 'Make available' }).click();
  await expect(page.getByRole('link', { name: 'Brew this' })).toBeVisible();
});

test('brew finalization can finish the selected coffee bag', async ({ page }) => {
  const session = await loginAda(page);
  const coffee = await createLifecycleCoffee(page, session, 'Final Cup');

  await page.goto(`/coffees/${coffee.id}`);
  await page.getByRole('link', { name: 'Brew this' }).click();
  await page.getByRole('button', { name: /Medium washed \/ balanced/ }).click();
  await page.getByRole('button', { name: 'Save and open brew mode' }).click();
  await page.getByRole('button', { name: 'Finish brew' }).click();
  const lastBrewCheckbox = page.getByRole('checkbox', {
    name: /This was the last brew from this bag/
  });
  await expect(lastBrewCheckbox).not.toBeChecked();
  await lastBrewCheckbox.check();
  await page.getByRole('button', { name: 'Finalize and invite tasters' }).click();
  await expect(page.getByRole('heading', { name: 'Taste. Scan. Rate.' })).toBeVisible();

  await page.goto('/brews/new');
  await expect(page.getByLabel('Coffee').getByRole('option', { name: /Final Cup/ })).toHaveCount(0);
  await page.goto('/coffees');
  await expect(
    page
      .locator('section[aria-label="Coffee bags"]')
      .getByRole('heading', { name: coffee.name, exact: true })
  ).toHaveCount(0);
  const finishedSection = page.locator('details.finished-section');
  await finishedSection.getByText('Finished bags', { exact: true }).click();
  await expect(
    finishedSection.getByRole('heading', { name: coffee.name, exact: true })
  ).toBeVisible();
});

test('active brews use the configured brewing logo with regular-logo fallback', async ({
  page
}) => {
  const settings: AppSettings = {
    ...publicAppSettings,
    logo_path: '/brand/filter-coffee-club-logo-256.webp'
  };
  let status: ActiveBrews = {
    brews: [railBrew(101, 'Logo Test Brew')],
    recent_rating_brews: [],
    active_count: 1,
    max_active_brews: 2,
    can_start: true
  };

  await page.route('**/api/v1/brews/active', (route) => fulfillJson(route, status));
  await mockSignedOutHome(page, settings);
  await page.goto('/?kiosk=0');

  await expect(page.locator('.brand img')).toHaveAttribute(
    'src',
    '/brand/filter-coffee-club-brewing.svg'
  );
  await expect(page.locator('.hero-logo img')).toHaveAttribute(
    'src',
    '/brand/filter-coffee-club-brewing.svg'
  );
  await expect
    .poll(() =>
      page.locator('.brand img').evaluate((image) => (image as HTMLImageElement).naturalWidth)
    )
    .toBeGreaterThan(0);

  status = {
    brews: [],
    recent_rating_brews: [railBrew(100, 'Rating Only', 'rating-token')],
    active_count: 0,
    max_active_brews: 2,
    can_start: true
  };
  await expect(page.locator('.brand img')).toHaveAttribute(
    'src',
    '/brand/filter-coffee-club-logo-256.webp',
    { timeout: 8_000 }
  );
  await expect(page.locator('.hero-logo img')).toHaveAttribute(
    'src',
    '/brand/filter-coffee-club-logo-256.webp',
    { timeout: 8_000 }
  );

  settings.brewing_logo_path = null;
  status = {
    ...status,
    brews: [railBrew(102, 'Fallback Brew')],
    recent_rating_brews: [],
    active_count: 1
  };
  await page.reload();
  await expect(page.locator('.brand img')).toHaveAttribute(
    'src',
    '/brand/filter-coffee-club-logo-256.webp'
  );
  await expect(page.locator('.hero-logo img')).toHaveAttribute(
    'src',
    '/brand/filter-coffee-club-logo-256.webp'
  );
});

async function mockMattermostAdmin(page: Page, mattermostSettings: MattermostSettings) {
  const adminSession: Session = {
    profile: {
      id: 1,
      display_name: 'Ada',
      role: 'admin',
      active: true,
      pin_change_required: false
    },
    csrf_token: 'locked-mattermost-test-token',
    device_mode: 'personal',
    expires_at: '2030-01-01T00:00:00Z'
  };

  await page.route('**/api/v1/settings', (route) => fulfillJson(route, publicAppSettings));
  await page.route('**/api/v1/settings/mattermost', (route) =>
    fulfillJson(route, mattermostSettings)
  );
  await page.route('**/api/v1/auth/bootstrap-status', (route) =>
    fulfillJson(route, { required: false })
  );
  await page.route('**/api/v1/auth/me', (route) => fulfillJson(route, adminSession));
  await page.route('**/api/v1/brews/active', (route) =>
    fulfillJson(route, {
      brews: [],
      recent_rating_brews: [],
      active_count: 0,
      max_active_brews: 2,
      can_start: true
    })
  );
  for (const path of ['people', 'grinders', 'drippers', 'filters']) {
    await page.route(`**/api/v1/${path}`, (route) => fulfillJson(route, []));
  }
  await page.route('**/api/v1/grinder-definitions', (route) => fulfillJson(route, []));
  await page.route('**/api/v1/presets?active_only=false', (route) => fulfillJson(route, []));
  await page.route('**/api/v1/flavor-tags?active_only=false', (route) => fulfillJson(route, []));

  await page.goto('/admin?tab=settings&kiosk=0');
}

async function expectMattermostConfigurationLocked(page: Page) {
  const mattermostForm = page.locator('.mattermost-form');

  await expect(mattermostForm.getByLabel('Enabled')).toBeDisabled();
  await expect(mattermostForm.getByLabel('Authentication')).toBeDisabled();
  await expect(mattermostForm.getByRole('textbox', { name: /^Mattermost server/ })).toBeDisabled();
  await expect(mattermostForm.getByLabel('Incoming webhook URL')).toBeDisabled();
  await expect(mattermostForm.getByLabel('Post when a brew starts')).toBeDisabled();
  await expect(mattermostForm.getByLabel('Post when rating opens')).toBeDisabled();
  await expect(
    mattermostForm.getByRole('button', { name: 'Save Mattermost settings' })
  ).toBeDisabled();
  await expect(mattermostForm.getByRole('button', { name: 'Send test message' })).toBeDisabled();
}

test('fresh Mattermost setup clearly locks controls when encryption is unavailable', async ({
  page
}) => {
  await mockMattermostAdmin(page, {
    ...patMattermostSettings,
    auth_mode: 'webhook',
    encryption_available: false,
    credential_status: 'not_configured'
  });

  const mattermostForm = page.locator('.mattermost-form');
  await expect(mattermostForm.getByText('Mattermost setup is locked.')).toBeVisible();
  await expect(mattermostForm).toHaveAttribute('aria-describedby', 'mattermost-encryption-warning');
  await expect(mattermostForm.getByLabel('Enabled')).not.toBeChecked();
  await expectMattermostConfigurationLocked(page);
  await expect(mattermostForm.getByRole('button', { name: 'Remove credential' })).toHaveCount(0);
});

test('a mismatched Mattermost key is diagnosed and only credential removal remains', async ({
  page
}) => {
  await mockMattermostAdmin(page, {
    ...patMattermostSettings,
    enabled: true,
    auth_mode: 'webhook',
    credential_configured: true,
    encryption_available: true,
    credential_status: 'unreadable',
    failed_count: 2
  });

  const mattermostForm = page.locator('.mattermost-form');
  await expect(
    mattermostForm.getByText('Saved Mattermost credential is unreadable.')
  ).toBeVisible();
  await expect(mattermostForm).toHaveAttribute('aria-describedby', 'mattermost-credential-warning');
  await expect(mattermostForm.getByLabel('Enabled')).toBeChecked();
  await expectMattermostConfigurationLocked(page);
  await expect(mattermostForm.getByRole('button', { name: 'Retry failed' })).toBeDisabled();
  await expect(mattermostForm.getByRole('button', { name: 'Remove credential' })).toBeEnabled();
});

test('admin settings actions update without reloading unrelated data', async ({ page }) => {
  let settings: AppSettings = { ...publicAppSettings };
  let peopleRequests = 0;
  const adminSession: Session = {
    profile: {
      id: 1,
      display_name: 'Ada',
      role: 'admin',
      active: true,
      pin_change_required: false
    },
    csrf_token: 'branding-test-token',
    device_mode: 'personal',
    expires_at: '2030-01-01T00:00:00Z'
  };

  await page.route('**/api/v1/settings', (route) => fulfillJson(route, settings));
  await page.route('**/api/v1/settings/mattermost', (route) =>
    fulfillJson(route, patMattermostSettings)
  );
  await page.route('**/api/v1/auth/bootstrap-status', (route) =>
    fulfillJson(route, { required: false })
  );
  await page.route('**/api/v1/auth/me', (route) => fulfillJson(route, adminSession));
  await page.route('**/api/v1/brews/active', (route) =>
    fulfillJson(route, {
      brews: [],
      recent_rating_brews: [],
      active_count: 0,
      max_active_brews: 2,
      can_start: true
    })
  );
  await page.route('**/api/v1/people', (route) => {
    peopleRequests += 1;
    return fulfillJson(route, []);
  });
  for (const path of ['grinders', 'drippers', 'filters']) {
    await page.route(`**/api/v1/${path}`, (route) => fulfillJson(route, []));
  }
  await page.route('**/api/v1/grinder-definitions', (route) => fulfillJson(route, []));
  await page.route('**/api/v1/presets?active_only=false', (route) => fulfillJson(route, []));
  await page.route('**/api/v1/flavor-tags?active_only=false', (route) => fulfillJson(route, []));
  await page.route('**/api/v1/settings/mattermost/verify', (route) =>
    fulfillJson(route, {
      user_id: 'mattermost-user-1',
      username: 'coffee-bot',
      channels: [
        {
          team_id: 'team-1',
          team_name: 'coffee-team',
          team_display_name: 'Coffee Team',
          channel_id: 'channel-1',
          channel_name: 'coffee-breaks',
          channel_display_name: 'Coffee breaks'
        }
      ]
    })
  );
  await page.route('**/api/v1/settings/brewing-logo/default', (route) => {
    settings = {
      ...settings,
      brewing_logo_path: '/brand/filter-coffee-club-brewing.svg'
    };
    return fulfillJson(route, settings);
  });
  await page.route('**/api/v1/settings/brewing-logo', (route) => {
    settings = {
      ...settings,
      brewing_logo_path:
        route.request().method() === 'DELETE' ? null : '/brand/filter-coffee-club-logo-256.webp'
    };
    return fulfillJson(route, settings);
  });

  await page.goto('/admin?kiosk=0');
  await page.getByRole('tab', { name: 'Settings' }).click();
  await expect(page.getByAltText('Current brew-in-progress logo')).toHaveAttribute(
    'src',
    '/brand/filter-coffee-club-brewing.svg'
  );
  expect(peopleRequests).toBe(1);

  const mattermostForm = page.locator('.mattermost-form');
  await mattermostForm
    .getByRole('textbox', { name: /^Personal access token/ })
    .fill('write-only-token');
  await mattermostForm.getByRole('button', { name: 'Verify token & load channels' }).click();
  await expect(page.getByText('Token verified as @coffee-bot.')).toBeVisible();
  await expect(mattermostForm.getByText('Connected as @coffee-bot')).toBeVisible();
  await expect(mattermostForm.getByLabel('Destination channel')).toContainText('Coffee breaks');
  await mattermostForm.getByLabel('Destination channel').selectOption('channel-1');
  await expect(mattermostForm.getByRole('button', { name: 'Send test message' })).toBeDisabled();

  await page.getByLabel('Replacement PNG/WebP').setInputFiles({
    name: 'custom-brewing.png',
    mimeType: 'image/png',
    buffer: Buffer.from('mock image handled by the route')
  });
  await expect(page.getByText('Brewing logo uploaded.')).toBeVisible();
  await expect(page.getByAltText('Current brew-in-progress logo')).toHaveAttribute(
    'src',
    '/brand/filter-coffee-club-logo-256.webp'
  );
  expect(peopleRequests).toBe(1);

  await page.getByRole('button', { name: 'Use regular logo while brewing' }).click();
  await expect(page.getByText('The regular logo will be used while brewing.')).toBeVisible();
  await expect(page.getByText('The regular logo is currently reused while brewing.')).toBeVisible();
  expect(peopleRequests).toBe(1);

  await page.getByRole('button', { name: 'Restore default brewing animation' }).click();
  await expect(page.getByText('Default brewing animation restored.')).toBeVisible();
  await expect(page.getByAltText('Current brew-in-progress logo')).toHaveAttribute(
    'src',
    '/brand/filter-coffee-club-brewing.svg'
  );
  expect(peopleRequests).toBe(1);
});

test('admin tab deep links survive the sign-in redirect', async ({ page }) => {
  await page.route('**/api/v1/auth/profiles', (route) => fulfillJson(route, []));
  await page.route('**/api/v1/brews/active', (route) =>
    fulfillJson(route, {
      brews: [],
      recent_rating_brews: [],
      active_count: 0,
      max_active_brews: 2,
      can_start: true
    })
  );
  await mockSignedOutHome(page);

  await page.goto('/admin?tab=settings&kiosk=0');

  await expect(page).toHaveURL(/\/login\?/);
  expect(new URL(page.url()).searchParams.get('next')).toBe('/admin?tab=settings');
});

test('the brew rail keeps parallel activity side-by-side at every breakpoint', async ({ page }) => {
  let status: ActiveBrews = {
    brews: [],
    recent_rating_brews: [],
    active_count: 0,
    max_active_brews: 2,
    can_start: true
  };
  let activityUnavailable = false;

  await page.route('**/api/v1/brews/active', async (route) => {
    if (activityUnavailable) {
      await fulfillJson(route, { detail: 'Temporarily unavailable' }, 503);
      return;
    }
    await fulfillJson(route, status);
  });
  await mockSignedOutHome(page);
  await page.goto('/?kiosk=0');
  await expect(page.getByTestId('start-brew-chip')).toHaveAttribute(
    'href',
    '/login?next=%2Fbrews%2Fnew'
  );

  status = {
    brews: [railBrew(101, 'Parallel One')],
    recent_rating_brews: [railBrew(99, 'Freshly Finished', 'fresh-token')],
    active_count: 1,
    max_active_brews: 2,
    can_start: true
  };
  await page.reload();
  await expect(page.getByTestId('active-brew-chip')).toHaveCount(1);
  await expect(page.getByTestId('rating-brew-chip')).toHaveAttribute('href', '/rate/fresh-token');
  await expect(page.getByTestId('start-brew-chip')).toContainText('+ New brew');

  activityUnavailable = true;
  await page.waitForResponse(
    (response) => response.url().endsWith('/api/v1/brews/active') && response.status() === 503
  );
  await expect(page.getByTestId('active-brew-chip')).toHaveCount(1);
  await expect(page.getByTestId('rating-brew-chip')).toHaveCount(1);
  activityUnavailable = false;

  status = {
    brews: [railBrew(101, 'Parallel One'), railBrew(102, 'Parallel Two')],
    recent_rating_brews: [
      railBrew(100, 'Newest Rating Prompt', 'new-token'),
      railBrew(99, 'Older Rating Prompt', 'older-token')
    ],
    active_count: 2,
    max_active_brews: 2,
    can_start: false
  };
  await page.reload();
  await expect(page.getByTestId('active-brew-chip')).toHaveCount(2);
  await expect(page.getByTestId('rating-brew-chip')).toHaveCount(2);
  await expect(page.getByTestId('start-brew-chip')).toHaveCount(0);

  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1024, height: 768 },
    { width: 768, height: 1024 },
    { width: 393, height: 851 }
  ]) {
    await page.setViewportSize(viewport);
    const layout = await page.getByTestId('brew-activity-rail').evaluate((rail) => {
      const track = rail.firstElementChild as HTMLElement;
      const chips = [...track.querySelectorAll<HTMLElement>('.brew-activity-chip')];
      const tops = new Set(chips.map((chip) => Math.round(chip.getBoundingClientRect().top)));
      return {
        chipCount: chips.length,
        oneRow: tops.size === 1,
        minimumTouchTarget: Math.min(...chips.map((chip) => chip.getBoundingClientRect().height)),
        scrolls: track.scrollWidth > track.clientWidth,
        pageScrollWidth: document.documentElement.scrollWidth,
        pageClientWidth: document.documentElement.clientWidth
      };
    });
    expect(layout.chipCount).toBe(4);
    expect(layout.oneRow).toBe(true);
    expect(layout.minimumTouchTarget).toBeGreaterThanOrEqual(44);
    expect(layout.scrolls).toBe(viewport.width <= 768);
    expect(layout.pageScrollWidth).toBeLessThanOrEqual(layout.pageClientWidth);

    const menu = page.getByRole('button', { name: 'Menu' });
    if (viewport.width <= 820) {
      await expect(menu).toBeVisible();
      await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeHidden();
    } else {
      await expect(menu).toBeHidden();
      await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeVisible();
    }
  }
});

test('the home brew log survives a temporary activity failure', async ({ page }) => {
  await page.route('**/api/v1/brews/active', (route) =>
    fulfillJson(route, { detail: 'Temporarily unavailable' }, 503)
  );
  await mockSignedOutHome(page);
  await page.goto('/?kiosk=0');

  await expect(page.getByText('No brews yet. The first measurement is waiting.')).toBeVisible();
  await expect(page.locator('.section .error')).toHaveCount(0);
  await expect(page.getByTestId('brew-activity-rail')).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Version v2026.08.5' })).toHaveAttribute(
    'href',
    'https://github.com/clelange/filter-coffee-club/releases/tag/v2026.08.5'
  );
  await expect(page.getByRole('link', { name: 'Report an issue' })).toHaveAttribute(
    'href',
    'https://github.com/clelange/filter-coffee-club/issues/new?body=%0A%0ADeployed%20version%3A%20v2026.08.5'
  );
  await page.setViewportSize({ width: 393, height: 851 });
  const footerLayout = await page.locator('footer').evaluate((footer) => ({
    pageFits: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    detailsStayTogether: Array.from(footer.querySelectorAll('.footer-detail')).every((detail) => {
      const children = Array.from(detail.children);
      return (
        children.length === 2 &&
        children[0].getBoundingClientRect().top === children[1].getBoundingClientRect().top
      );
    })
  }));
  expect(footerLayout).toEqual({ pageFits: true, detailsStayTogether: true });
});

test('the footer links source deployments to their commit', async ({ page }) => {
  await page.route('**/api/v1/brews/active', (route) =>
    fulfillJson(route, {
      brews: [],
      recent_rating_brews: [],
      active_count: 0,
      max_active_brews: 2,
      can_start: true
    })
  );
  await mockSignedOutHome(page, { ...publicAppSettings, app_version: 'abcdef0' });
  await page.goto('/?kiosk=0');

  await expect(page.getByRole('link', { name: 'Version abcdef0' })).toHaveAttribute(
    'href',
    'https://github.com/clelange/filter-coffee-club/commit/abcdef0'
  );
  await expect(page.getByRole('link', { name: 'Report an issue' })).toHaveAttribute(
    'href',
    'https://github.com/clelange/filter-coffee-club/issues/new?body=%0A%0ADeployed%20version%3A%20abcdef0'
  );
});

test('the footer omits unverified deployment metadata when settings fail', async ({ page }) => {
  await page.route('**/api/v1/settings', (route) =>
    fulfillJson(route, { detail: 'Temporarily unavailable' }, 503)
  );
  await page.route('**/api/v1/brews?*', (route) => fulfillJson(route, []));
  await page.goto('/?kiosk=0');

  await expect(page.getByText('Version development')).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Report an issue' })).toHaveCount(0);
});

test('the rail waits for bootstrap and omits start during a mandatory PIN change', async ({
  page
}) => {
  let bootstrapFails = true;
  let activityRequests = 0;
  const requiredPinSession: Session = {
    profile: {
      id: 1,
      display_name: 'Ada',
      role: 'admin',
      active: true,
      pin_change_required: true
    },
    csrf_token: 'pin-change-test-token',
    device_mode: 'personal',
    expires_at: '2030-01-01T00:00:00Z'
  };
  const activity: ActiveBrews = {
    brews: [railBrew(101, 'Bootstrap Brew')],
    recent_rating_brews: [],
    active_count: 1,
    max_active_brews: 2,
    can_start: true
  };

  await page.route('**/api/v1/settings', (route) => fulfillJson(route, publicAppSettings));
  await page.route('**/api/v1/auth/bootstrap-status', (route) =>
    bootstrapFails
      ? fulfillJson(route, { detail: 'Temporarily unavailable' }, 503)
      : fulfillJson(route, { required: false })
  );
  await page.route('**/api/v1/auth/me', (route) => fulfillJson(route, requiredPinSession));
  await page.route('**/api/v1/brews?*', (route) => fulfillJson(route, []));
  await page.route('**/api/v1/brews/active', (route) => {
    activityRequests += 1;
    return fulfillJson(route, activity);
  });

  await page.goto('/?kiosk=0');
  await expect(page.getByRole('heading', { name: 'The club could not start.' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Try again' })).toBeVisible();
  await expect(page.getByTestId('brew-activity-rail')).toHaveCount(0);
  expect(activityRequests).toBe(0);

  bootstrapFails = false;
  await page.getByRole('button', { name: 'Try again' }).click();
  await expect(page).toHaveURL(/\/account\/pin/);
  await expect(page.getByRole('heading', { name: 'Choose your own PIN.' })).toBeVisible();
  await expect(page.getByTestId('active-brew-chip')).toContainText('Bootstrap Brew');
  await expect(page.getByTestId('start-brew-chip')).toHaveCount(0);
});
