import { expect, test, type Page, type Route } from '@playwright/test';
import type { Brew, BrewInput, Session } from '../src/lib/types';

const settings = {
  app_name: 'Filter Coffee Club',
  app_version: 'development',
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

const memberSession: Session = {
  ...session,
  profile: { ...session.profile, role: 'member' }
};

const overseeingAdminSession: Session = {
  ...session,
  profile: { ...session.profile, id: 2, display_name: 'Grace' }
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
  finished_at: null,
  archived: false,
  available: true,
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

const alternateGrinder = {
  ...grinder,
  id: 22,
  model: 'Two',
  setting_unit: 'turns',
  setting_step: 0.5,
  soft_min: 2,
  soft_max: 8
};

const uncoveredGrinder = {
  ...grinder,
  id: 23,
  model: 'Three',
  soft_min: 12,
  soft_max: 36
};

const preset = {
  id: 31,
  name: 'Medium washed / balanced',
  ratio: 16,
  temperature_min_c: 92,
  temperature_max_c: 96,
  active: true,
  sort_order: 1,
  grinder_ranges: [
    { grinder_id: grinder.id, setting_min: 24, setting_max: 28 },
    { grinder_id: alternateGrinder.id, setting_min: 4, setting_max: 6 }
  ]
};

const inactivePreset = {
  ...preset,
  id: 32,
  name: 'Retired recipe',
  ratio: 16.3,
  active: false,
  sort_order: 2
};

const finishInput: BrewInput = {
  coffee_id: coffee.id,
  grinder_id: grinder.id,
  dripper_id: null,
  filter_id: null,
  source_preset_id: preset.id,
  dose_g: 8,
  water_g: 128,
  target_ratio: 16,
  temperature_c: 94,
  grinder_setting: 26,
  servings: 1,
  target_flow_g_s: 4.5,
  bloom_water_g: 45,
  bloom_time_s: null,
  pour_count: null,
  technique_note: null
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

async function mockCommonApi(
  page: Page,
  brewState: () => Brew | null,
  deviceMode: Session['device_mode'] = 'personal',
  viewerSession: Session = session
) {
  await page.route('**/api/v1/**', (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();
    if (path === '/api/v1/settings') return fulfillJson(route, settings);
    if (path === '/api/v1/auth/bootstrap-status') return fulfillJson(route, { required: false });
    if (path === '/api/v1/auth/me') {
      return fulfillJson(route, { ...viewerSession, device_mode: deviceMode });
    }
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
    if (path === '/api/v1/grinders') {
      return fulfillJson(route, [grinder, alternateGrinder, uncoveredGrinder]);
    }
    if (path === '/api/v1/drippers' || path === '/api/v1/filters') return fulfillJson(route, []);
    if (path === '/api/v1/presets') return fulfillJson(route, [preset, inactivePreset]);
    if (path === '/api/v1/brews' && method === 'GET') return fulfillJson(route, []);
    const current = brewState();
    if (current && path === `/api/v1/brews/${current.id}` && method === 'GET') {
      return fulfillJson(route, current);
    }
    return fulfillJson(route, { detail: `Unhandled mocked request: ${method} ${path}` }, 500);
  });
}

async function setKioskNumber(page: Page, label: string, value: string) {
  await page.getByRole('button', { name: new RegExp(`^Set ${label};`) }).click();
  const dialog = page.getByRole('dialog', { name: label, exact: true });
  await dialog.getByRole('button', { name: /^(Clear|Clear value)$/ }).click();
  for (const character of value) {
    await dialog.getByRole('button', { name: character, exact: true }).click();
  }
  await dialog.getByRole('button', { name: 'Apply' }).click();
}

test('correlated batch values stay synchronized and unusual creation requires confirmation', async ({
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
  await expect(page.getByText('Matches preset', { exact: true })).toBeVisible();
  await page.getByText('More pour details').click();
  const bloomWater = page.getByRole('spinbutton', { name: 'Bloom water' });
  await bloomWater.fill('16');
  await bloomWater.blur();
  const servings = page.getByRole('spinbutton', { name: 'Servings', exact: true });
  await servings.fill('5');
  await servings.blur();
  await expect(page.getByRole('spinbutton', { name: 'Total coffee dose' })).toHaveValue('40');
  await expect(page.getByRole('spinbutton', { name: 'Total water', exact: true })).toHaveValue(
    '640'
  );
  await expect(bloomWater).toHaveValue('80');

  const totalDose = page.getByRole('spinbutton', { name: 'Total coffee dose' });
  await totalDose.fill('8');
  await totalDose.blur();
  await expect(page.getByRole('spinbutton', { name: 'Total water', exact: true })).toHaveValue(
    '128'
  );
  await expect(bloomWater).toHaveValue('16');
  const targetRatio = page.getByRole('spinbutton', { name: 'Target ratio' });
  await targetRatio.fill('80');
  await targetRatio.blur();
  await expect(page.getByText(/A 1:80 ratio is outside the normal/)).toBeVisible();
  await expect(page.getByText('Customized · ratio', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Save and open brew mode' }).click();
  const confirmation = page.getByRole('alertdialog', { name: 'Save unusual 1:80 ratio?' });
  await expect(confirmation).toContainText('8 g total coffee and 640 g total water');
  await expect(confirmation.getByRole('button', { name: 'Review amounts' })).toBeFocused();
  expect(createRequests).toBe(0);

  await page.keyboard.press('Escape');
  await expect(confirmation).toBeHidden();
  await expect(page.getByRole('button', { name: 'Save and open brew mode' })).toBeFocused();
  await page.getByRole('button', { name: 'Save and open brew mode' }).click();
  await confirmation.getByRole('button', { name: 'Review amounts' }).click();
  await expect(confirmation).toBeHidden();
  await page.getByRole('button', { name: 'Save and open brew mode' }).click();
  await confirmation.getByRole('button', { name: 'Save 1:80 anyway' }).click();
  await expect(page).toHaveURL(/\/brews\/101$/);
  expect(createRequests).toBe(1);
  expect(confirmationHeader).toBe('true');
});

test('water basis keeps water fixed while ratio and dose changes stay synchronized', async ({
  page
}) => {
  await mockCommonApi(page, () => null);

  await page.goto('/brews/new?kiosk=0');
  await page.getByRole('button', { name: /Medium washed \/ balanced/ }).click();
  await page.getByText('More pour details').click();
  const bloomWater = page.getByRole('spinbutton', { name: 'Bloom water' });
  await bloomWater.fill('129');
  await bloomWater.blur();
  await expect(page.getByText('Bloom water must not exceed total water.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Save and open brew mode' })).toBeDisabled();
  await bloomWater.fill('16');
  await bloomWater.blur();
  const totalDose = page.getByRole('spinbutton', { name: 'Total coffee dose' });
  const totalWater = page.getByRole('spinbutton', { name: 'Total water', exact: true });
  await totalWater.fill('240');
  await totalWater.blur();
  await expect(totalDose).toHaveValue('15');
  await expect(bloomWater).toHaveValue('30');
  await expect(page.getByText(/Ratio changes preserve\s+total water/)).toBeVisible();

  const targetRatio = page.getByRole('spinbutton', { name: 'Target ratio' });
  await targetRatio.fill('20');
  await targetRatio.blur();
  await expect(totalWater).toHaveValue('240');
  await expect(totalDose).toHaveValue('12');
  await expect(bloomWater).toHaveValue('24');

  await totalDose.fill('10');
  await totalDose.blur();
  await expect(totalWater).toHaveValue('200');
  await expect(bloomWater).toHaveValue('20');
  await expect(page.getByText(/Ratio changes preserve\s+coffee dose/)).toBeVisible();

  await targetRatio.fill('600');
  await targetRatio.blur();
  await expect(page.getByText(/require a water amount between 1 and 5000 g/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Save and open brew mode' })).toBeDisabled();
  await targetRatio.fill('500');
  await targetRatio.blur();
  await expect(page.getByText(/require a water amount between 1 and 5000 g/)).toBeHidden();
});

test('preset conformance distinguishes deviations from missing grinder guidance', async ({
  page
}) => {
  await mockCommonApi(page, () => null);

  await page.goto('/brews/new?kiosk=0');
  const presetButton = page.getByRole('button', { name: /Medium washed \/ balanced/ });
  await presetButton.click();
  await expect(presetButton).toHaveClass(/chosen/);
  await expect(page.getByText('Matches preset', { exact: true })).toBeVisible();

  const temperature = page.getByRole('spinbutton', { name: 'Temperature' });
  await temperature.fill('97');
  await temperature.blur();
  await expect(page.getByText('Customized · temperature', { exact: true })).toBeVisible();
  await expect(page.getByText('Changed: temperature', { exact: true })).toBeVisible();
  await expect(presetButton).toHaveClass(/chosen/);

  await temperature.fill('96');
  await temperature.blur();
  await expect(page.getByText('Matches preset', { exact: true })).toBeVisible();

  const grinderSelect = page.getByRole('combobox', { name: 'Grinder' });
  const grinderSetting = page.getByRole('spinbutton', { name: 'Grinder setting' });
  await grinderSelect.selectOption(String(alternateGrinder.id));
  await expect(grinderSetting).toHaveValue('5');
  await expect(page.getByText('Matches preset', { exact: true })).toBeVisible();

  await grinderSetting.fill('7.5');
  await grinderSetting.blur();
  await expect(page.getByText('Customized · grind', { exact: true })).toBeVisible();

  await grinderSelect.selectOption(String(uncoveredGrinder.id));
  await expect(grinderSetting).toHaveValue('7.5');
  await expect(
    page.getByText('Matches guided fields · grinder not covered', { exact: true })
  ).toBeVisible();
  await expect(page.getByText(/Retained from the previous grinder/)).toBeVisible();
  await expect(page.getByText(/No guidance for Orbit Three/)).toBeVisible();
  await expect(page.getByText('Click-based grinder settings must be whole numbers.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Save and open brew mode' })).toBeDisabled();
  await grinderSetting.fill('20');
  await grinderSetting.blur();
  await expect(page.getByText(/Retained from the previous grinder/)).toBeHidden();
  await expect(page.getByText('Click-based grinder settings must be whole numbers.')).toBeHidden();
  await expect(presetButton).toHaveClass(/chosen/);
});

test('an inactive source preset remains visible while editing an existing brew', async ({
  page
}) => {
  const existing = brewFromInput(303, {
    coffee_id: coffee.id,
    grinder_id: grinder.id,
    dripper_id: null,
    filter_id: null,
    source_preset_id: inactivePreset.id,
    dose_g: 7.4,
    water_g: 120,
    target_ratio: 16.3,
    temperature_c: 94,
    grinder_setting: 26,
    servings: 1,
    target_flow_g_s: 4.5,
    bloom_water_g: null,
    bloom_time_s: null,
    pour_count: null,
    technique_note: null
  });
  await mockCommonApi(page, () => existing);

  await page.goto('/brews/new?edit=303&kiosk=0');
  const inactiveButton = page.getByRole('button', { name: /Retired recipe/ });
  await expect(inactiveButton).toBeVisible();
  await expect(inactiveButton).toBeDisabled();
  await expect(inactiveButton).toHaveClass(/chosen/);
  await expect(inactiveButton).toContainText('Inactive starting point');
  await expect(page.getByRole('spinbutton', { name: 'Target ratio' })).toHaveValue('16.3');
  await expect(page.getByText('Matches preset', { exact: true })).toBeVisible();
});

test('kiosk servings rescale both batch totals', async ({ page }) => {
  await mockCommonApi(page, () => null, 'kiosk');

  await page.goto('/brews/new?kiosk=1');
  await page.getByRole('button', { name: /Medium washed \/ balanced/ }).click();
  await setKioskNumber(page, 'Servings', '5');

  await expect(
    page.getByRole('button', { name: /^Set Total coffee dose; current value 40/ })
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: /^Set Total water; current value 640/ })
  ).toBeVisible();
  await setKioskNumber(page, 'Total water', '240');
  await expect(
    page.getByRole('button', { name: /^Set Total coffee dose; current value 15/ })
  ).toBeVisible();
  await setKioskNumber(page, 'Target ratio', '20');
  await expect(
    page.getByRole('button', { name: /^Set Total coffee dose; current value 12/ })
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: /^Set Total water; current value 240/ })
  ).toBeVisible();
  await expect(page.getByText(/Changing servings scales the whole batch/)).toBeVisible();
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
    target_ratio: 16,
    temperature_c: 94,
    grinder_setting: 26,
    servings: 1,
    target_flow_g_s: 4.5,
    bloom_water_g: 45,
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
  await actualWater.fill('40');
  await actualWater.blur();
  await expect(page.getByText(/cannot be lower than the recorded 45 g bloom/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Finalize and invite tasters' })).toBeDisabled();
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

for (const [viewerLabel, viewerSession] of [
  ['member operator', memberSession],
  ['administrator overseeing another operator', overseeingAdminSession]
] as const) {
  test(`${viewerLabel} reviews a concurrent change before retrying finalization`, async ({
    page
  }) => {
    let currentBrew = brewFromInput(404, finishInput);
    let finalizeAttempts = 0;
    let finalPayload: {
      water_g: number;
      total_brew_time_s: number;
      revision: number;
      mark_coffee_finished: boolean;
    } | null = null;
    await mockCommonApi(page, () => currentBrew, 'personal', viewerSession);
    await page.route('**/api/v1/brews/404/finalize', (route) => {
      finalizeAttempts += 1;
      const payload = route.request().postDataJSON() as {
        water_g: number;
        total_brew_time_s: number;
        revision: number;
        mark_coffee_finished: boolean;
      };
      if (finalizeAttempts === 1) {
        currentBrew = { ...currentBrew, revision: 2, temperature_c: 91 };
        return fulfillJson(route, { detail: 'Brew changed; refresh and try again' }, 409);
      }
      finalPayload = payload;
      currentBrew = {
        ...currentBrew,
        water_g: payload.water_g,
        ratio: Math.round((payload.water_g / currentBrew.dose_g) * 100) / 100,
        total_brew_time_s: payload.total_brew_time_s,
        revision: currentBrew.revision + 1,
        status: 'completed',
        completed_at: '2026-08-15T10:04:12Z',
        rating_token: 'conflict-test-token'
      };
      return fulfillJson(route, currentBrew);
    });

    await page.goto('/brews/404?kiosk=0');
    const finishButton = page.getByRole('button', { name: 'Finish brew' });
    await finishButton.click();
    const finishDialog = page.getByRole('dialog', { name: 'Finish this brew' });
    const minutes = finishDialog.getByRole('spinbutton', { name: 'Minutes' });
    await expect(minutes).toBeFocused();
    await minutes.fill('4');
    await finishDialog.getByRole('spinbutton', { name: 'Seconds' }).fill('12');
    await finishDialog.getByRole('spinbutton', { name: 'Actual water' }).fill('126');
    await finishDialog.getByRole('checkbox', { name: /last brew from this bag/i }).check();
    await finishDialog.getByRole('button', { name: 'Finalize and invite tasters' }).click();

    await expect(finishDialog.getByRole('alert')).toContainText('Another device changed this brew');
    await expect(
      finishDialog.getByRole('button', { name: 'Finalize and invite tasters' })
    ).toHaveCount(0);
    const reviewButton = finishDialog.getByRole('button', { name: 'Review latest recipe' });
    await expect(reviewButton).toBeFocused();
    await reviewButton.click();
    await expect(finishDialog).toBeHidden();
    await expect(finishButton).toBeFocused();
    await expect(page.getByText('91 °C', { exact: true })).toBeVisible();

    await finishButton.click();
    await expect(finishDialog.getByRole('spinbutton', { name: 'Minutes' })).toHaveValue('4');
    await expect(finishDialog.getByRole('spinbutton', { name: 'Seconds' })).toHaveValue('12');
    await expect(finishDialog.getByRole('spinbutton', { name: 'Actual water' })).toHaveValue('126');
    await expect(
      finishDialog.getByRole('checkbox', { name: /last brew from this bag/i })
    ).toBeChecked();
    await finishDialog.getByRole('button', { name: 'Finalize and invite tasters' }).click();

    await expect(page.getByRole('heading', { name: 'Taste. Scan. Rate.' })).toBeVisible();
    expect(finalizeAttempts).toBe(2);
    expect(finalPayload).toMatchObject({
      water_g: 126,
      total_brew_time_s: 252,
      revision: 2,
      mark_coffee_finished: true
    });
  });
}

test('finish dialog restores focus and keeps an ordinary failure retryable', async ({ page }) => {
  let currentBrew = brewFromInput(405, finishInput);
  let finalizeAttempts = 0;
  await mockCommonApi(page, () => currentBrew);
  await page.route('**/api/v1/brews/405/finalize', (route) => {
    finalizeAttempts += 1;
    if (finalizeAttempts === 1) {
      return fulfillJson(route, { detail: 'The brewer is temporarily unavailable' }, 500);
    }
    currentBrew = {
      ...currentBrew,
      status: 'completed',
      revision: 2,
      total_brew_time_s: 180,
      completed_at: '2026-08-15T10:04:12Z',
      rating_token: 'retry-test-token'
    };
    return fulfillJson(route, currentBrew);
  });

  await page.goto('/brews/405?kiosk=0');
  const finishButton = page.getByRole('button', { name: 'Finish brew' });
  const finishDialog = page.getByRole('dialog', { name: 'Finish this brew' });
  await finishButton.click();
  await expect(finishDialog.getByRole('spinbutton', { name: 'Minutes' })).toBeFocused();
  await finishDialog.getByRole('button', { name: 'Back' }).focus();
  await page.keyboard.press('Tab');
  await expect(finishDialog.getByRole('button', { name: 'Decrease Minutes' })).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(finishDialog).toBeHidden();
  await expect(finishButton).toBeFocused();

  await finishButton.click();
  const finalizeButton = finishDialog.getByRole('button', {
    name: 'Finalize and invite tasters'
  });
  await finalizeButton.click();
  await expect(finishDialog.getByRole('alert')).toHaveText('The brewer is temporarily unavailable');
  await expect(finalizeButton).toBeEnabled();
  await finalizeButton.click();
  await expect(page.getByRole('heading', { name: 'Taste. Scan. Rate.' })).toBeVisible();
  expect(finalizeAttempts).toBe(2);
});

test('failed conflict refresh requires a successful reload before review', async ({ page }) => {
  let currentBrew = brewFromInput(406, finishInput);
  let brewReads = 0;
  let finalizeAttempts = 0;
  await mockCommonApi(page, () => currentBrew);
  await page.route('**/api/v1/brews/406', (route) => {
    brewReads += 1;
    if (brewReads === 2) {
      return fulfillJson(route, { detail: 'Could not load this brew' }, 503);
    }
    return fulfillJson(route, currentBrew);
  });
  await page.route('**/api/v1/brews/406/finalize', (route) => {
    finalizeAttempts += 1;
    currentBrew = { ...currentBrew, revision: 2, temperature_c: 90 };
    return fulfillJson(route, { detail: 'Brew changed; refresh and try again' }, 409);
  });

  await page.goto('/brews/406?kiosk=0');
  await page.getByRole('button', { name: 'Finish brew' }).click();
  const finishDialog = page.getByRole('dialog', { name: 'Finish this brew' });
  await finishDialog.getByRole('button', { name: 'Finalize and invite tasters' }).click();

  await expect(finishDialog.getByRole('alert')).toContainText('latest version could not be loaded');
  await expect(
    finishDialog.getByRole('button', { name: 'Finalize and invite tasters' })
  ).toHaveCount(0);
  const reloadButton = finishDialog.getByRole('button', { name: 'Reload latest brew' });
  await expect(reloadButton).toBeFocused();
  await reloadButton.click();
  const reviewButton = finishDialog.getByRole('button', { name: 'Review latest recipe' });
  await expect(reviewButton).toBeFocused();
  expect(finalizeAttempts).toBe(1);
  expect(brewReads).toBe(3);
});

test('conflict refresh follows a brew already completed elsewhere', async ({ page }) => {
  let currentBrew = brewFromInput(407, finishInput);
  await mockCommonApi(page, () => currentBrew);
  await page.route('**/api/v1/brews/407/finalize', (route) => {
    currentBrew = {
      ...currentBrew,
      status: 'completed',
      revision: 2,
      total_brew_time_s: 195,
      completed_at: '2026-08-15T10:04:12Z',
      rating_token: 'completed-elsewhere-token'
    };
    return fulfillJson(route, { detail: 'Brew changed; refresh and try again' }, 409);
  });

  await page.goto('/brews/407?kiosk=0');
  await page.getByRole('button', { name: 'Finish brew' }).click();
  const finishDialog = page.getByRole('dialog', { name: 'Finish this brew' });
  await finishDialog.getByRole('button', { name: 'Finalize and invite tasters' }).click();

  await expect(finishDialog).toBeHidden();
  await expect(page.getByRole('heading', { name: 'Taste. Scan. Rate.' })).toBeVisible();
});
