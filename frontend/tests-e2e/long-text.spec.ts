import { expect, test, type Locator, type Page } from '@playwright/test';
import { grinderDefinitions } from '../tests-fixtures/grinders';

const name = 'Teilchenbeschleuniger';
const longName = name.repeat(3);
const longRoaster = 'Kaffeeröstereimanufaktur'.repeat(3);
const memberName = 'Alexanderthecoffeetaster'.repeat(3);
const date = '2026-09-14T10:00:00Z';
const coffees = [
  name,
  longName,
  'A very long coffee name with several ordinary words',
  'Short',
  longName
].map((name, index) => ({
  id: index + 1,
  name,
  roaster: index === 1 ? longRoaster : 'Becking',
  photo_path: null,
  photo_framing: null,
  chart_color: '#00728f',
  country: 'Switzerland',
  package_notes: index === 1 ? 'UnbrokenTastingNote'.repeat(6) : null,
  archived: false,
  available: index !== 4,
  finished_at: index === 4 ? date : null,
  created_at: date
}));
const grinder = {
  id: 1,
  manufacturer: longRoaster,
  model: longName,
  definition_key: 'custom',
  setting_unit: 'clicks',
  setting_step: 1,
  soft_min: 0,
  soft_max: 50,
  guidance: longName,
  archived: false,
  photo_path: null,
  photo_framing: null
};
const dripper = {
  id: 1,
  manufacturer: longRoaster,
  model: longName,
  notes: longName,
  archived: false,
  photo_path: null,
  photo_framing: null
};
const filter = {
  id: 1,
  name: longName,
  notes: longName,
  archived: false,
  photo_path: null,
  photo_framing: null
};
const brews = coffees.slice(0, 4).map((coffee) => ({
  id: coffee.id,
  coffee_id: coffee.id,
  coffee_name: coffee.name,
  coffee_roaster: coffee.roaster,
  operator_id: 1,
  operator_name: 'Ada',
  operators: [{ id: 1, display_name: 'Ada' }],
  grinder_id: 1,
  grinder_name: longName,
  grinder_unit: 'clicks',
  grinder_setting: 25,
  dripper_id: 1,
  dripper_name: longName,
  filter_id: 1,
  filter_name: longName,
  source_preset_id: null,
  status: 'completed',
  dose_g: 20,
  water_g: 320,
  ratio: 16,
  target_ratio: 16,
  temperature_c: 94,
  servings: 2,
  target_flow_g_s: 4,
  bloom_water_g: null,
  bloom_time_s: null,
  pour_count: null,
  technique_note: null,
  total_brew_time_s: 180,
  overall_throughput_g_s: 1.78,
  completed_at: date,
  created_at: date,
  revision: 1,
  cloned_from_id: null,
  rating_token: null
}));
const averages = { liking: 6, acidity: 2, bitterness: 2, sweetness: 3, body: 3 };
const aggregate = { count: 4, averages, flavor_axes: [] };
const summaries = coffees.map((coffee) => ({
  coffee_id: coffee.id,
  name: `${coffee.roaster} · ${coffee.name}`,
  bag_label: `Bag #${coffee.id}`,
  chart_color: coffee.chart_color,
  available: coffee.available,
  average: 5.75,
  ratings: 4,
  brews: 1,
  tasters: 4,
  best_brew: null
}));

async function mockCatalog(page: Page) {
  const unexpected: string[] = [];
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname.replace('/api/v1', '');
    let body: unknown;
    if (path === '/settings')
      body = {
        app_name: 'Filter Coffee Club',
        app_version: 'development',
        subtitle: 'Layout test',
        public_base_url: null,
        public_url_needs_configuration: false,
        logo_path: null,
        brewing_logo_path: '/brand/filter-coffee-club-brewing.svg',
        max_active_brews: 2,
        color_cream: '#f6f1e8',
        color_surface: '#fffdfc',
        color_ink: '#241c19',
        color_coffee: '#6b3f2a',
        color_cyan: '#00728f',
        color_amber: '#d88700',
        demo_mode: false
      };
    else if (path === '/auth/bootstrap-status') body = { required: false };
    else if (path === '/auth/me')
      body = {
        profile: {
          id: 1,
          display_name: 'Ada',
          role: 'admin',
          active: true,
          pin_change_required: false
        },
        device_mode: 'personal',
        csrf_token: 'layout-test',
        expires_at: '2030-01-01T00:00:00Z'
      };
    else if (path === '/auth/profiles')
      body = [
        { id: 1, display_name: 'Ada' },
        { id: 2, display_name: memberName }
      ];
    else if (path === '/brews/active')
      body = {
        brews: [],
        recent_rating_brews: [],
        active_count: 0,
        max_active_brews: 2,
        can_start: true
      };
    else if (path === '/coffees') body = coffees;
    else if (/^\/coffees\/\d+$/.test(path)) body = coffees[Number(path.split('/').at(-1)) - 1];
    else if (path.endsWith('/rating-insights'))
      body = {
        coffee_id: 1,
        aggregate,
        rated_brew_count: 1,
        taster_count: 4,
        ranking_min_ratings: 3,
        best_brew: { brew: brews[0], aggregate },
        rated_brews: [{ brew: brews[0], aggregate }],
        next_offset: null
      };
    else if (path === '/grinders') body = [grinder];
    else if (path === '/grinders/1') body = grinder;
    else if (path === '/drippers') body = [dripper];
    else if (path === '/filters') body = [filter];
    else if (
      path === '/grinder-definitions' ||
      path === '/presets' ||
      path === '/ratings/me/comparisons'
    )
      body = [];
    else if (path === '/catalog/usage')
      body = {
        items: coffees.map((coffee) => ({
          kind: 'coffee',
          item_id: coffee.id,
          completed_brew_count: 1,
          last_completed_at: date
        }))
      };
    else if (path.startsWith('/catalog/') && path.endsWith('/insights'))
      body = {
        kind: path.split('/')[2],
        item_id: 1,
        completed_brew_count: 4,
        last_completed_at: date,
        average_ratio: 16,
        average_temperature_c: 94,
        average_total_brew_time_s: 180,
        average_overall_throughput_g_s: 1.78,
        observed_grinder_setting_min: 25,
        observed_grinder_setting_max: 25,
        ratings_visible: true,
        rating_count: 4,
        average_liking: 6,
        recent_brews: brews.map((brew) => ({ ...brew, rating_count: 4, average_liking: 6 }))
      };
    else if (path === '/brews') body = brews;
    else if (path === '/brews/1')
      body = { ...brews[0], coffee_name: longName, status: 'draft', completed_at: null };
    else if (path === '/analytics')
      body = {
        counts: { brews: 4, ratings: 16, coffees: 4 },
        grinder_definitions: grinderDefinitions,
        coffee_summaries: summaries,
        top_coffees: summaries,
        top_recipes: [],
        flavor_counts: {},
        operator_counts: [],
        scatter: brews.map((brew) => ({
          brew_id: brew.id,
          coffee_id: brew.coffee_id,
          coffee: `${brew.coffee_roaster} · ${brew.coffee_name}`,
          coffee_color: '#00728f',
          liking: 6,
          ratings: 4,
          ratio: 16,
          temperature_c: 94,
          grinder_id: 1,
          grinder_name: longName,
          grinder_unit: 'clicks',
          grinder_setting: 25,
          grinder_definition_key: 'custom',
          reference_grinder_setting: null,
          total_brew_time_s: 180,
          target_flow_g_s: 4,
          overall_throughput_g_s: 1.78,
          rating_metrics: Object.fromEntries(
            Object.entries(averages).map(([key, value]) => [
              key,
              { average: value, minimum: value, maximum: value }
            ])
          )
        }))
      };
    else if (path === '/profiles/2/ratings')
      body = {
        profile: { id: 2, display_name: memberName },
        is_self: false,
        is_complete_history: true,
        rating_count: 4,
        averages,
        next_offset: null,
        favorite_coffees: coffees.slice(0, 3).map((coffee) => ({
          coffee_id: coffee.id,
          coffee_name: coffee.name,
          coffee_roaster: coffee.roaster,
          rating_count: 1,
          average_liking: 6
        })),
        ratings: brews.map((brew) => ({
          brew,
          brew_id: brew.id,
          rating: averages,
          peer_count: 0,
          total_rating_count: 1,
          peer_averages: {},
          peer_deltas: {},
          selected_flavors: [],
          peer_flavor_counts: {}
        }))
      };
    else {
      unexpected.push(path);
      await route.fulfill({ status: 404, json: { detail: 'Unexpected fixture request' } });
      return;
    }
    await route.fulfill({ json: body });
  });
  return unexpected;
}

const viewports = [
  { width: 320, height: 800 },
  { width: 375, height: 812 },
  { width: 768, height: 1024 },
  { width: 1024, height: 600 },
  { width: 1280, height: 900 }
];

// Page width alone cannot detect overflow hidden by a card, or text crossing into a score.
async function expectTextInside(text: Locator, boundary: string) {
  expect(await text.count()).toBeGreaterThan(0);
  const overflow = await text.evaluateAll(
    (elements, selector) =>
      elements.flatMap((element) => {
        const box = element.closest(selector)!;
        const bounds = box.getBoundingClientRect();
        if (!bounds.width || !bounds.height) return [];
        const style = getComputedStyle(box);
        const left = bounds.left + parseFloat(style.paddingLeft);
        const right = bounds.right - parseFloat(style.paddingRight);
        const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
        const failures: string[] = [];
        while (walker.nextNode()) {
          const node = walker.currentNode;
          if (!node.textContent?.trim()) continue;
          const range = document.createRange();
          range.selectNodeContents(node);
          if (
            [...range.getClientRects()].some(
              (rect) => rect.width > 0 && (rect.left < left - 2 || rect.right > right + 2)
            )
          ) {
            failures.push(node.textContent.trim());
          }
        }
        return failures;
      }),
    boundary
  );
  expect(overflow, `Text must fit inside ${boundary}`).toEqual([]);
}

const screens = [
  {
    url: '/coffees',
    ready: '[data-testid="catalog-card"] h3',
    text: '.catalog-copy h3, .catalog-copy p',
    boundary: '.catalog-copy'
  },
  {
    url: '/coffees/1',
    ready: '.detail-identity h1',
    text: '.detail-identity h1, .detail-identity p',
    boundary: '.detail-identity'
  },
  {
    url: '/coffees/2',
    ready: '.detail-identity h1',
    text: '.detail-identity h1, .detail-identity p',
    boundary: '.detail-identity'
  },
  {
    url: '/equipment',
    ready: '[data-testid="catalog-card"] h3',
    text: '.catalog-copy h3, .catalog-copy p',
    boundary: '.catalog-copy'
  },
  {
    url: '/equipment/grinders/1',
    ready: '.detail-identity h1',
    text: '.detail-identity h1, .detail-identity p',
    boundary: '.detail-identity'
  },
  {
    url: '/',
    ready: '.brew-card h3',
    text: '.brew-card h3, .brew-card > p',
    boundary: '.brew-card'
  },
  {
    url: '/brews/1',
    ready: '.brew-heading h1',
    text: '.brew-heading h1, .brew-heading .lede',
    boundary: '.brew-heading > div'
  },
  {
    url: '/profiles/2',
    ready: '.favorite-card h3',
    text: '.favorite-card h3, .favorite-card small, .rating-heading h3, .rating-heading p',
    boundary: 'div'
  },
  {
    url: '/analytics?coffee=1',
    ready: '.coffee-summary a',
    text: '.coffee-summary a, .ranking a > span',
    boundary: '.coffee-summary > div, .ranking a > span'
  }
];

for (const screen of screens) {
  test(`long display text stays in its column on ${screen.url}`, async ({ page }) => {
    const unexpected = await mockCatalog(page);
    await page.goto(screen.url);
    await expect(page.locator(screen.ready).first()).toBeVisible();
    if (screen.url === '/coffees') await page.getByText('Finished bags', { exact: true }).click();
    for (const viewport of viewports) {
      await page.setViewportSize(viewport);
      await expectTextInside(page.locator(screen.text), screen.boundary);
      await expect
        .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
        .toBe(true);
      if (screen.url.includes('/coffees/') || screen.url.includes('/equipment/')) {
        await expectTextInside(page.locator('.brew-heading strong'), '.brew-heading > div');
      }
      if (screen.url === '/profiles/2') {
        await expectTextInside(page.locator('.profile-hero h1'), '.profile-hero > div');
      }
    }
    expect(unexpected).toEqual([]);
  });
}

test('native selectors reveal clipped values, update with selection, and hide when they fit', async ({
  page
}) => {
  const unexpected = await mockCatalog(page);
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/brews/new?coffee=2');
  const coffee = page.getByRole('combobox', { name: 'Coffee', exact: true });
  const summary = coffee.locator('..').locator('.selected-option');
  await expect(summary).toHaveText(`${longRoaster} · ${longName}`);
  await expect(summary).toBeVisible();
  await expectTextInside(summary, 'label');
  expect(await coffee.getAttribute('aria-describedby')).toBeNull();
  await expect(summary).toHaveAttribute('aria-hidden', 'true');
  const field = await page.locator('.field-row').evaluate((el) => {
    const select = el.querySelector('select')!.getBoundingClientRect();
    const button = el.querySelector('button')!.getBoundingClientRect();
    return { stacked: select.bottom <= button.top, width: select.width };
  });
  expect(field.stacked).toBe(true);
  expect(field.width).toBeGreaterThan(280);
  await coffee.selectOption('4');
  await expect(summary).toBeHidden();
  await coffee.selectOption('1');
  await page.setViewportSize({ width: 320, height: 800 });
  await expect(summary).toBeVisible();
  await page.setViewportSize({ width: 600, height: 900 });
  await expect(summary).toBeHidden();
  for (const label of ['Choose a grinder', 'Dripper', 'Filter']) {
    const select = page.getByRole('combobox', { name: label, exact: true });
    await select.selectOption('1');
    await expect(select.locator('..').locator('.selected-option')).toBeVisible();
    await expectTextInside(select.locator('..').locator('.selected-option'), 'label');
  }
  // Leave the unsaved form through a full navigation in this isolated test context.
  page.on('dialog', (dialog) => dialog.accept());
  await page.goto('/analytics?coffee=2');
  await page.setViewportSize({ width: 375, height: 812 });
  const chartCoffee = page.getByRole('combobox', { name: 'Coffee', exact: true });
  const mapCoffee = page.getByRole('combobox', { name: 'Map coffee', exact: true });
  await expect(mapCoffee.locator('..').locator('.selected-option')).toContainText(longName);
  await chartCoffee.selectOption('4');
  await expect(mapCoffee).toHaveValue('4');
  await expect(mapCoffee.locator('..').locator('.selected-option')).toHaveText(
    'Becking · Short · Bag #4'
  );
  await chartCoffee.selectOption('all');
  await expect(chartCoffee.locator('..').locator('.selected-option')).toBeHidden();
  expect(unexpected).toEqual([]);
});

test('grind controls and original-setting details fit long labels at phone and Pi widths', async ({
  page
}, testInfo) => {
  const unexpected = await mockCatalog(page);
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/analytics?coffee=2');
  const panels = [
    page
      .locator('.chart-panel')
      .filter({ has: page.getByRole('heading', { name: 'Settings versus liking' }) }),
    page.locator('.recipe-map')
  ];
  for (let index = 0; index < panels.length; index++) {
    const panel = panels[index];
    await panel
      .getByRole('combobox', { name: index === 0 ? 'Horizontal axis' : 'Y axis', exact: true })
      .selectOption('grinder_setting');
    const scale = panel.getByRole('combobox', { name: 'Show settings in', exact: true });
    await expect(panel.getByTestId('unconverted-brews')).toContainText(
      '1 brew cannot be converted'
    );
    await scale.selectOption('grinder:1');
    await expect(panel.locator('.plot-point')).toHaveCount(1);
    await panel.locator('.plot-point').focus();
    await expect(panel.getByTestId('point-details')).toContainText(`Original grinder: ${longName}`);
    await expect(panel.getByTestId('point-details')).not.toContainText('Approximate conversion');
  }
  for (const viewport of [
    { width: 320, height: 800 },
    { width: 375, height: 812 },
    { width: 600, height: 900 },
    { width: 1024, height: 600 }
  ]) {
    await page.setViewportSize(viewport);
    for (const panel of panels) {
      const scale = panel.getByRole('combobox', { name: 'Show settings in', exact: true });
      const source = panel.getByRole('combobox', { name: 'Brewed with', exact: true });
      await expect(scale.locator('..').locator('.selected-option')).toBeVisible();
      await expectTextInside(panel.locator('.selected-option'), 'label');
      await expectTextInside(panel.locator('.point-details small'), '.point-details > div');
      if (viewport.width <= 500) {
        const fieldWidths = await panel
          .locator('select')
          .evaluateAll((selects) => selects.map((select) => select.getBoundingClientRect().width));
        expect(Math.max(...fieldWidths) - Math.min(...fieldWidths)).toBeLessThanOrEqual(1);
      }
      await expect(source).toHaveValue('all');
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true
    );
  }
  await page.setViewportSize({ width: 1024, height: 1600 });
  await panels[0].evaluate((panel) =>
    window.scrollTo(0, window.scrollY + panel.getBoundingClientRect().top - 160)
  );
  await panels[0].screenshot({ path: testInfo.outputPath('grind-controls-long-desktop.png') });
  await page.setViewportSize({ width: 375, height: 1800 });
  await panels[0].screenshot({ path: testInfo.outputPath('grind-controls-long-mobile.png') });
  expect(errors).toEqual([]);
  expect(unexpected).toEqual([]);
});
