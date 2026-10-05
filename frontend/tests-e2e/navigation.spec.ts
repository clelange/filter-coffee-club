import { expect, test, type Page } from '@playwright/test';
import type { AppSettings, DeviceMode, Session } from '../src/lib/types';

interface NavigationOptions {
  signedIn?: boolean;
  role?: 'admin' | 'member';
  deviceMode?: DeviceMode;
  pinChangeRequired?: boolean;
  demoMode?: boolean;
}

async function mockNavigation(page: Page, options: NavigationOptions = {}) {
  let signedIn = options.signedIn ?? true;
  const settings: AppSettings = {
    app_name: 'Filter Coffee Club',
    app_version: 'development',
    subtitle: 'Navigation test',
    public_base_url: null,
    logo_path: null,
    brewing_logo_path: null,
    color_cream: '#f6f1e8',
    color_surface: '#fffdfc',
    color_ink: '#241c19',
    color_coffee: '#6b3f2a',
    color_cyan: '#00728f',
    color_amber: '#d88700',
    max_active_brews: 2,
    public_url_needs_configuration: false,
    demo_mode: options.demoMode ?? false,
    demo_notice: null,
    demo_pin: null,
    demo_profile_names: []
  };
  const session: Session = {
    profile: {
      id: 1,
      display_name: 'Ada',
      role: options.role ?? 'admin',
      active: true,
      pin_change_required: options.pinChangeRequired ?? false
    },
    device_mode: options.deviceMode ?? 'personal',
    csrf_token: 'navigation-test',
    expires_at: '2099-01-01T00:00:00Z'
  };
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname.replace('/api/v1', '');
    if (path === '/settings') return route.fulfill({ json: settings });
    if (path === '/auth/bootstrap-status') return route.fulfill({ json: { required: false } });
    if (path === '/auth/me') {
      return signedIn
        ? route.fulfill({ json: session })
        : route.fulfill({ status: 401, json: { detail: 'Not authenticated' } });
    }
    if (path === '/auth/logout') {
      signedIn = false;
      return route.fulfill({ status: 204 });
    }
    if (path === '/brews/active') {
      return route.fulfill({
        json: {
          brews: [],
          recent_rating_brews: [],
          active_count: 0,
          max_active_brews: 2,
          can_start: true
        }
      });
    }
    if (path === '/catalog/usage') return route.fulfill({ json: { items: [] } });
    if (['/brews', '/coffees', '/auth/profiles', '/ratings/me/comparisons'].includes(path)) {
      return route.fulfill({ json: [] });
    }
    throw new Error(`Unexpected navigation fixture request: ${path}`);
  });
  await page.goto(options.pinChangeRequired ? '/account/pin' : '/');
  await expect(
    page.getByRole('heading', {
      name: options.pinChangeRequired ? 'Choose your own PIN.' : 'Past brews',
      exact: true
    })
  ).toBeVisible();
}

const scenarios: { name: string; options: NavigationOptions; items: string[] }[] = [
  { name: 'signed out', options: { signedIn: false }, items: ['Home', 'Coffees', 'Sign in'] },
  {
    name: 'personal admin',
    options: {},
    items: [
      'Coffees',
      'Equipment',
      'Members',
      'Analytics',
      'Admin',
      'Change PIN',
      'Ada',
      'Sign out'
    ]
  },
  {
    name: 'member',
    options: { role: 'member' },
    items: ['Coffees', 'Equipment', 'Members', 'Analytics', 'Change PIN', 'Ada', 'Sign out']
  },
  {
    name: 'kiosk admin',
    options: { deviceMode: 'kiosk' },
    items: ['Coffees', 'Equipment', 'Members', 'Analytics', 'Change PIN', 'Ada', 'Sign out']
  },
  {
    name: 'demo admin',
    options: { demoMode: true },
    items: ['Coffees', 'Equipment', 'Members', 'Analytics', 'Admin', 'Ada', 'Sign out']
  },
  {
    name: 'required PIN change',
    options: { pinChangeRequired: true },
    items: ['Change PIN', 'Sign out']
  }
];

for (const scenario of scenarios) {
  test(`navigation preserves available actions for ${scenario.name}`, async ({ page }) => {
    await mockNavigation(page, scenario.options);
    const navigation = page.getByRole('navigation', { name: 'Main navigation', exact: true });
    await expect(navigation.locator('a, button')).toHaveText(scenario.items);
  });
}

for (const signedIn of [false, true]) {
  test(`mobile navigation closes on keyboard exit ${signedIn ? 'signed in' : 'signed out'}`, async ({
    page,
    browserName
  }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await mockNavigation(page, { signedIn });
    const toggle = page.getByRole('button', { name: 'Menu', exact: true });
    const navigation = page.getByRole('navigation', { name: 'Main navigation', exact: true });
    const items = navigation.locator('a, button');
    // macOS WebKit uses Option-Tab to include links in keyboard navigation.
    const tab = browserName === 'webkit' && process.platform === 'darwin' ? 'Alt+Tab' : 'Tab';
    const previous =
      browserName === 'webkit' && process.platform === 'darwin' ? 'Alt+Shift+Tab' : 'Shift+Tab';

    await toggle.focus();
    await page.keyboard.press('Enter');
    await page.keyboard.press(tab);
    await expect(items.first()).toBeFocused();
    await expect(toggle).toHaveAttribute('aria-expanded', 'true');

    await page.keyboard.press(previous);
    await expect(toggle).toBeFocused();
    await expect(toggle).toHaveAttribute('aria-expanded', 'true');
    await page.keyboard.press(previous);
    await expect(page.getByRole('link', { name: 'Filter Coffee Club home' })).toBeFocused();
    await expect(navigation).toBeHidden();

    await toggle.click();
    await items.last().focus();
    await page.keyboard.press(tab);
    const start = page.getByTestId('start-brew-chip');
    await expect(start).toBeFocused();
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await expect(navigation).toBeHidden();
    await page.keyboard.press('Escape');
    await expect(start).toBeFocused();

    await toggle.click();
    await items.first().focus();
    await page.keyboard.press('Escape');
    await expect(toggle).toBeFocused();
    await expect(navigation).toBeHidden();
  });
}

test('mobile navigation closes on outside clicks, navigation, and breakpoint changes', async ({
  page
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await mockNavigation(page);
  const toggle = page.getByRole('button', { name: 'Menu', exact: true });
  const navigation = page.getByRole('navigation', { name: 'Main navigation', exact: true });

  await toggle.click();
  await page.getByRole('heading', { name: 'Make the next brew measurable.' }).click();
  await expect(navigation).toBeHidden();

  await toggle.click();
  await navigation.getByRole('link', { name: 'Coffees', exact: true }).click();
  await expect(page).toHaveURL(/\/coffees$/);
  await expect(navigation).toBeHidden();

  await toggle.click();
  await page.setViewportSize({ width: 1024, height: 600 });
  await expect(navigation).toBeVisible();
  await expect(navigation.getByRole('link', { name: 'Coffees', exact: true })).toHaveClass(
    /active/
  );
  await page.setViewportSize({ width: 375, height: 812 });
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await expect(navigation).toBeHidden();

  await toggle.click();
  await page.goBack();
  await expect(page).toHaveURL(/\/$/);
  await expect(navigation).toBeHidden();
});

test('signing out through navigation clears the session and opens sign in', async ({ page }) => {
  await mockNavigation(page);
  const navigation = page.getByRole('navigation', { name: 'Main navigation', exact: true });
  await navigation.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(navigation.locator('a, button')).toHaveText(['Home', 'Coffees', 'Sign in']);
});

test('navigation keeps focus on a visible control when crossing the mobile breakpoint', async ({
  page
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await mockNavigation(page);
  const toggle = page.getByRole('button', { name: 'Menu', exact: true });
  const navigation = page.getByRole('navigation', { name: 'Main navigation', exact: true });
  const firstLink = navigation.getByRole('link', { name: 'Coffees', exact: true });

  await toggle.focus();
  await page.setViewportSize({ width: 1024, height: 600 });
  await expect(firstLink).toBeFocused();
  await page.setViewportSize({ width: 375, height: 812 });
  await expect(toggle).toBeFocused();
  await expect(navigation).toBeHidden();

  await toggle.click();
  await firstLink.focus();
  await page.setViewportSize({ width: 1024, height: 600 });
  await expect(firstLink).toBeFocused();
  await page.setViewportSize({ width: 375, height: 812 });
  await expect(toggle).toBeFocused();
  await expect(navigation).toBeHidden();

  const start = page.getByTestId('start-brew-chip');
  await start.focus();
  await page.setViewportSize({ width: 1024, height: 600 });
  await expect(start).toBeFocused();
  await page.setViewportSize({ width: 375, height: 812 });
  await expect(start).toBeFocused();
});
