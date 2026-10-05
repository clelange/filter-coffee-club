import { expect, test, type Page, type Route } from '@playwright/test';
import type { AppSettings, Brew, RatingComparison, Session } from '../src/lib/types';

const settings: AppSettings = {
  app_name: 'Filter Coffee Club',
  app_version: 'development',
  subtitle: 'Home page test',
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
  demo_mode: false,
  demo_notice: null,
  demo_pin: null,
  demo_profile_names: []
};
const session: Session = {
  profile: { id: 1, display_name: 'Ada', role: 'admin', active: true, pin_change_required: false },
  device_mode: 'personal',
  csrf_token: 'home-test',
  expires_at: '2099-01-01T00:00:00Z'
};
const brew: Brew = {
  id: 1,
  coffee_id: 1,
  coffee_name: 'Ethiopia Guji Hambela',
  coffee_roaster: 'Club Roasters',
  operator_id: 1,
  operator_name: 'Ada',
  operators: [{ id: 1, display_name: 'Ada' }],
  grinder_id: 1,
  grinder_name: 'Comandante C40',
  grinder_unit: 'clicks',
  grinder_setting: 25,
  dripper_id: null,
  dripper_name: null,
  filter_id: null,
  filter_name: null,
  source_preset_id: null,
  status: 'completed',
  dose_g: 20,
  water_g: 320,
  ratio: 16,
  target_ratio: 16,
  temperature_c: 94,
  servings: 2,
  target_flow_g_s: null,
  bloom_water_g: null,
  bloom_time_s: null,
  pour_count: null,
  technique_note: null,
  total_brew_time_s: 180,
  overall_throughput_g_s: 1.78,
  completed_at: '2026-10-01T10:03:00Z',
  created_at: '2026-10-01T10:00:00Z',
  revision: 1,
  cloned_from_id: null,
  rating_token: 'home-rating-token'
};
const brews: Brew[] = [
  brew,
  { ...brew, id: 2, coffee_name: 'Colombia Huila', status: 'cancelled' },
  { ...brew, id: 3, coffee_name: 'Kenya Kirinyaga' },
  { ...brew, id: 4, coffee_name: 'Archived observation', status: 'voided' }
];
const scores = { liking: 8, acidity: 2, bitterness: 1, sweetness: 3, body: 3 };
const comparison: RatingComparison = {
  brew_id: 1,
  rating: {
    ...scores,
    profile_id: 1,
    profile_name: 'Ada',
    flavor_tag_ids: [],
    updated_at: '2026-10-01T10:10:00Z'
  },
  peer_count: 2,
  total_rating_count: 3,
  peer_averages: scores,
  peer_deltas: { liking: 0, acidity: 0, bitterness: 0, sweetness: 0, body: 0 },
  selected_flavors: [],
  peer_flavor_counts: {}
};

async function mockHome(
  page: Page,
  options: {
    signedIn?: boolean;
    onclone?: (route: Route) => void | Promise<void>;
    onjoin?: (route: Route) => void | Promise<void>;
  } = {}
) {
  const signedIn = options.signedIn ?? true;
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname.replace('/api/v1', '');
    if (path === '/settings') return route.fulfill({ json: settings });
    if (path === '/auth/bootstrap-status') return route.fulfill({ json: { required: false } });
    if (path === '/auth/me') {
      return signedIn
        ? route.fulfill({ json: session })
        : route.fulfill({ status: 401, json: { detail: 'Not authenticated' } });
    }
    if (path === '/brews/active') {
      return route.fulfill({
        json: {
          brews: [
            {
              id: 10,
              coffee_name: 'Bob’s brew',
              coffee_roaster: 'Club Roasters',
              operators: [{ id: 2, display_name: 'Bob' }],
              status: 'draft',
              rating_token: null
            }
          ],
          recent_rating_brews: [],
          active_count: 1,
          max_active_brews: 2,
          can_start: true
        }
      });
    }
    if (path === '/brews') return route.fulfill({ json: brews });
    if (path === '/ratings/me/comparisons') return route.fulfill({ json: [comparison] });
    if (path.endsWith('/clone') && options.onclone) return options.onclone(route);
    if (path.endsWith('/join') && options.onjoin) return options.onjoin(route);
    throw new Error(`Unexpected home fixture request: ${path}`);
  });
  await page.goto('/');
  await expect(page.locator('.brew-card')).toHaveCount(4);
  if (signedIn) await expect(page.getByText('Your rating vs other tasters')).toBeVisible();
}

test('populated home sections have readable spacing at phone and desktop sizes', async ({
  page
}, testInfo) => {
  await mockHome(page);
  for (const viewport of [
    { width: 320, height: 800 },
    { width: 375, height: 812 },
    { width: 560, height: 900 },
    { width: 561, height: 900 },
    { width: 768, height: 1024 },
    { width: 1024, height: 600 },
    { width: 1024, height: 2000 },
    { width: 2560, height: 1080 }
  ]) {
    await page.setViewportSize(viewport);
    const geometry = await page.evaluate(() => {
      const activeHeading = document.querySelector('.active-section h2')!.getBoundingClientRect();
      const activeCard = document.querySelector('.active-card')!.getBoundingClientRect();
      const links = document.querySelector('.section-links')!.getBoundingClientRect();
      const pastCard = document.querySelector('.brew-card')!.getBoundingClientRect();
      const hero = document.querySelector('.hero')!.getBoundingClientRect();
      return {
        activeGap: activeCard.top - activeHeading.bottom,
        pastGap: pastCard.top - links.bottom,
        linksBelowTitle:
          links.top >=
          document.querySelector('.section-links')!.previousElementSibling!.getBoundingClientRect()
            .bottom,
        heroHeight: hero.height,
        overflows: document.documentElement.scrollWidth > innerWidth
      };
    });
    expect(geometry.overflows).toBe(false);
    expect(geometry.activeGap).toBeGreaterThanOrEqual(15);
    if (viewport.width <= 560) {
      expect(geometry.linksBelowTitle).toBe(true);
      expect(geometry.pastGap).toBeGreaterThanOrEqual(15);
    }
    if (viewport.height === 2000) expect(geometry.heroHeight).toBeLessThanOrEqual(700);
  }
  await page.setViewportSize({ width: 375, height: 812 });
  await page.screenshot({ path: testInfo.outputPath('home-mobile.png'), fullPage: true });
});

for (const signedIn of [false, true]) {
  test(`brew cards preserve actions and comparisons ${signedIn ? 'signed in' : 'signed out'}`, async ({
    page
  }) => {
    await mockHome(page, { signedIn });
    const completed = page.locator('.brew-card').filter({ hasText: 'Ethiopia Guji Hambela' });
    await expect(
      completed.getByRole('link', { name: 'Open invitation', exact: true })
    ).toHaveAttribute('href', '/brews/1');
    await expect(
      page.locator('.brew-card').getByRole('button', { name: 'Repeat', exact: true })
    ).toHaveCount(signedIn ? 2 : 0);
    await expect(
      page.locator('.brew-card').getByRole('link', { name: 'View record', exact: true })
    ).toHaveCount(2);
    await expect(page.getByText('Your rating vs other tasters')).toHaveCount(signedIn ? 1 : 0);
    if (signedIn) {
      await expect(completed.getByRole('link', { name: 'Full details' })).toHaveAttribute(
        'href',
        '/profiles/1#brew-1'
      );
      await expect(completed.locator('.mini-metrics')).toContainText('1:16');
      await expect(completed.locator('.mini-metrics')).toContainText('3:00');
    }
  });
}

test('a failed repeat keeps the log, focus, and idempotency key available for retry', async ({
  page
}) => {
  const pending: Route[] = [];
  const keys: string[] = [];
  await mockHome(page, {
    onclone: async (route) => {
      keys.push(route.request().headers()['idempotency-key']);
      expect(route.request().headers()['x-csrf-token']).toBe(session.csrf_token);
      if (keys.length === 1) {
        pending.push(route);
        return;
      }
      await route.fulfill({
        status: 503,
        json: { detail: 'Brew service temporarily unavailable' }
      });
    }
  });
  const repeat = page.locator('.brew-card').getByRole('button', { name: 'Repeat', exact: true });
  await repeat.first().focus();
  await repeat.first().press('Enter');
  await expect.poll(() => pending.length).toBe(1);
  await expect(repeat).toHaveCount(2);
  for (const button of await repeat.all()) await expect(button).toBeDisabled();
  await page.keyboard.press('Enter');
  await pending[0].fulfill({
    status: 503,
    json: { detail: 'Brew service temporarily unavailable' }
  });
  const failedCard = page.locator('.brew-card').filter({ hasText: 'Ethiopia Guji Hambela' });
  await expect(failedCard.getByRole('alert')).toHaveText('Brew service temporarily unavailable');
  await expect(page.locator('.brew-card')).toHaveCount(4);
  await expect(repeat.first()).toBeFocused();
  for (const button of await repeat.all()) await expect(button).toBeEnabled();

  await repeat.first().press('Enter');
  await expect.poll(() => keys.length).toBe(2);
  expect(keys[0]).toBeTruthy();
  expect(keys[1]).toBe(keys[0]);
  await expect(repeat.first()).toBeEnabled();
  await expect(page.locator('.brew-card')).toHaveCount(4);
});

test('a failed join preserves the brew log and an accessible retry button', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await mockHome(page, {
    onjoin: (route) =>
      route.fulfill({ status: 503, json: { detail: 'Could not join this brew yet' } })
  });
  const join = page.getByRole('button', { name: 'Join brew', exact: true });
  expect((await join.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await join.focus();
  await join.press('Enter');
  await expect(page.locator('.active-section').getByRole('alert')).toHaveText(
    'Could not join this brew yet'
  );
  await expect(join).toBeEnabled();
  await expect(join).toBeFocused();
  await expect(page.locator('.brew-card')).toHaveCount(4);
});

test('session expiry keeps public brews visible while removing cached personal comparisons', async ({
  page
}) => {
  await mockHome(page, {
    onclone: (route) => route.fulfill({ status: 401, json: { detail: 'Please sign in again' } })
  });
  await page
    .locator('.brew-card')
    .getByRole('button', { name: 'Repeat', exact: true })
    .first()
    .click();
  await expect(page.getByRole('alert')).toHaveText('Please sign in again');
  await expect(page.locator('.brew-card')).toHaveCount(4);
  await expect(page.getByText('Your rating vs other tasters')).toHaveCount(0);
  await expect(
    page.locator('.brew-card').getByRole('button', { name: 'Repeat', exact: true })
  ).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Sign in to brew', exact: true })).toBeVisible();
});
