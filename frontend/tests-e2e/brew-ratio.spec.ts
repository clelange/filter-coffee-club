import { expect, test, type Page, type Route } from '@playwright/test';
import type { Brew, BrewInput, Session } from '../src/lib/types';

const settings = {
  app_name: 'Filter Coffee Club',
  subtitle: 'Ratio guard test',
  public_base_url: null,
  logo_path: null,
  color_cream: '#f6f1e8',
  color_surface: '#fffdfc',
  color_ink: '#241c19',
  color_coffee: '#6b3f2a',
  color_cyan: '#007f9e',
  color_amber: '#d88700',
  max_active_brews: 2,
  public_url_needs_configuration: false,
  demo_mode: false,
  demo_notice: null,
  demo_pin: null,
  demo_profile_names: []
};

const session: Session = {
  profile: {
    id: 1,
    display_name: 'Ada',
    role: 'admin',
    active: true,
    pin_change_required: false
  },
  csrf_token: 'ratio-guard-token',
  device_mode: 'personal',
  expires_at: '2030-01-01T00:00:00Z'
};

const coffee = {
  id: 11,
  roaster: 'Guard Roasters',
  name: 'Batch Lot',
  country: null,
  region: null,
  producer: null,
  process: null,
  roast_level: null,
  roast_date: null,
  opened_date: null,
  variety: null,
  package_notes: null,
  purchase_location: null,
  chart_color: '#0072B2',
  photo_path: null,
  photo_framing: null,
  archived: false,
  cloned_from_id: null,
  created_at: '2026-08-15T10:00:00Z',
  updated_at: '2026-08-15T10:00:00Z'
};

const grinder = {
  id: 21,
  manufacturer: 'Orbit',
  model: 'One',
  setting_unit: 'clicks',
  setting_step: 1,
  soft_min: 10,
  soft_max: 40,
  notes: null,
  photo_path: null,
  photo_framing: null,
  archived: false
};

const preset = {
  id: 31,
  name: 'Medium washed / balanced',
  ratio: 16,
  temperature_min_c: 92,
  temperature_max_c: 96,
  active: true,
  sort_order: 1,
  grinder_ranges: [{ grinder_id: grinder.id, setting_min: 24, setting_max: 28 }]
};

function fulfillJson(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body)
  });
}

function brewFromInput(id: number, input: BrewInput, status: Brew['status'] = 'draft'): Brew {
  return {
    ...input,
    id,
    operator_id: 1,
    operator_name: 'Ada',
    operators: [{ id: 1, display_name: 'Ada' }],
    revision: 1,
    coffee_name: coffee.name,
    coffee_roaster: coffee.roaster,
    grinder_name: `${grinder.manufacturer} ${grinder.model}`,
    grinder_unit: grinder.setting_unit,
    dripper_name: null,
    filter_name: null,
    status,
    ratio: Math.round((input.water_g / input.dose_g) * 100) / 100,
    overall_throughput_g_s: null,
    total_brew_time_s: null,
    completed_at: null,
    created_at: '2026-08-15T10:00:00Z',
    cloned_from_id: null,
    rating_token: null
  };
}

async function mockCommonApi(page: Page, brewState: () => Brew | null) {
  await page.route('**/api/v1/**', (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();
    if (path === '/api/v1/settings') return fulfillJson(route, settings);
    if (path === '/api/v1/auth/bootstrap-status') return fulfillJson(route, { required: false });
    if (path === '/api/v1/auth/me') return fulfillJson(route, session);
    if (path === '/api/v1/brews/active') {
      const current = brewState();
      const draft = current?.status === 'draft' ? current : null;
      return fulfillJson(route, {
        brews: draft
          ? [
              {
                id: draft.id,
                coffee_name: draft.coffee_name,
                coffee_roaster: draft.coffee_roaster,
                operators: draft.operators,
                status: draft.status,
                rating_token: draft.rating_token
              }
            ]
          : [],
        recent_rating_brews: [],
        active_count: draft ? 1 : 0,
        max_active_brews: 2,
        can_start: true
      });
    }
    if (path === '/api/v1/coffees') return fulfillJson(route, [coffee]);
    if (path === '/api/v1/grinders') return fulfillJson(route, [grinder]);
    if (path === '/api/v1/drippers' || path === '/api/v1/filters') return fulfillJson(route, []);
    if (path === '/api/v1/presets') return fulfillJson(route, [preset]);
    if (path === '/api/v1/brews' && method === 'GET') return fulfillJson(route, []);
    const current = brewState();
    if (current && path === `/api/v1/brews/${current.id}` && method === 'GET') {
      return fulfillJson(route, current);
    }
    return fulfillJson(route, { detail: `Unhandled mocked request: ${method} ${path}` }, 500);
  });
}

test('servings rescale batch totals and unusual creation requires explicit confirmation', async ({
  page
}) => {
  let currentBrew: Brew | null = null;
  let createRequests = 0;
  let confirmationHeader = '';
  await mockCommonApi(page, () => currentBrew);
  await page.route('**/api/v1/brews', (route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    createRequests += 1;
    confirmationHeader = route.request().headers()['x-confirm-unusual-ratio'] ?? '';
    currentBrew = brewFromInput(101, route.request().postDataJSON() as BrewInput);
    return fulfillJson(route, currentBrew);
  });

  await page.goto('/brews/new?kiosk=0');
  await page.getByRole('button', { name: /Medium washed \/ balanced/ }).click();
  const servings = page.getByRole('spinbutton', { name: 'Servings', exact: true });
  await servings.fill('5');
  await servings.blur();
  await expect(page.getByRole('spinbutton', { name: 'Total coffee dose' })).toHaveValue('40');
  await expect(page.getByRole('spinbutton', { name: 'Total water', exact: true })).toHaveValue(
    '640'
  );

  const totalDose = page.getByRole('spinbutton', { name: 'Total coffee dose' });
  await totalDose.fill('8');
  await totalDose.blur();
  await expect(page.getByText(/A 1:80 ratio is outside the normal/)).toBeVisible();
  await page.getByRole('button', { name: 'Save and open brew mode' }).click();
  const confirmation = page.getByRole('alertdialog', { name: 'Save unusual 1:80 ratio?' });
  await expect(confirmation).toContainText('8 g total coffee and 640 g total water');
  expect(createRequests).toBe(0);

  await confirmation.getByRole('button', { name: 'Review amounts' }).click();
  await expect(confirmation).toBeHidden();
  await page.getByRole('button', { name: 'Save and open brew mode' }).click();
  await confirmation.getByRole('button', { name: 'Save 1:80 anyway' }).click();
  await expect(page).toHaveURL(/\/brews\/101$/);
  expect(createRequests).toBe(1);
  expect(confirmationHeader).toBe('true');
});

test('unusual actual water requires confirmation before finalization', async ({ page }) => {
  const input: BrewInput = {
    coffee_id: coffee.id,
    grinder_id: grinder.id,
    dripper_id: null,
    filter_id: null,
    source_preset_id: preset.id,
    dose_g: 8,
    water_g: 128,
    temperature_c: 94,
    grinder_setting: 26,
    servings: 1,
    target_flow_g_s: 4.5,
    bloom_water_g: null,
    bloom_time_s: null,
    pour_count: null,
    technique_note: null
  };
  let currentBrew = brewFromInput(202, input);
  let finalizeRequests = 0;
  let confirmationHeader = '';
  await mockCommonApi(page, () => currentBrew);
  await page.route('**/api/v1/brews/202/finalize', (route) => {
    finalizeRequests += 1;
    confirmationHeader = route.request().headers()['x-confirm-unusual-ratio'] ?? '';
    const payload = route.request().postDataJSON() as {
      water_g: number;
      total_brew_time_s: number;
    };
    currentBrew = {
      ...currentBrew,
      water_g: payload.water_g,
      ratio: Math.round((payload.water_g / currentBrew.dose_g) * 100) / 100,
      total_brew_time_s: payload.total_brew_time_s,
      revision: currentBrew.revision + 1,
      status: 'completed',
      completed_at: '2026-08-15T10:03:00Z',
      rating_token: 'ratio-test-token'
    };
    return fulfillJson(route, currentBrew);
  });

  await page.goto('/brews/202?kiosk=0');
  await page.getByRole('button', { name: 'Finish brew' }).click();
  const actualWater = page.getByRole('spinbutton', { name: 'Actual water', exact: true });
  await actualWater.fill('640');
  await actualWater.blur();
  await expect(page.getByText(/Final ratio:/)).toContainText('1:80');
  await page.getByRole('button', { name: 'Finalize and invite tasters' }).click();
  const confirmation = page.getByRole('alertdialog', { name: 'Save unusual 1:80 ratio?' });
  await expect(confirmation).toContainText('8 g total coffee and 640 g total water');
  expect(finalizeRequests).toBe(0);

  await confirmation.getByRole('button', { name: 'Review amounts' }).click();
  await page.getByRole('button', { name: 'Finalize and invite tasters' }).click();
  await confirmation.getByRole('button', { name: 'Save 1:80 anyway' }).click();
  await expect(page.getByRole('heading', { name: 'Taste. Scan. Rate.' })).toBeVisible();
  expect(finalizeRequests).toBe(1);
  expect(confirmationHeader).toBe('true');
});
