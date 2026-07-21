import { expect, test, type Page } from '@playwright/test';

const settings = {
  app_name: 'Filter Coffee Club',
  subtitle: 'Analytics test',
  public_base_url: null,
  logo_path: null,
  color_cream: '#f6f1e8',
  color_surface: '#fffdfc',
  color_ink: '#241c19',
  color_coffee: '#6b3f2a',
  color_cyan: '#007f9e',
  color_amber: '#d88700',
  public_url_needs_configuration: false,
  demo_mode: false,
  demo_notice: null,
  demo_pin: null,
  demo_profile_names: []
};

const session = {
  profile: {
    id: 1,
    display_name: 'Ada',
    role: 'admin',
    active: true,
    pin_change_required: false
  },
  csrf_token: 'analytics-test-token',
  device_mode: 'personal',
  expires_at: '2030-01-01T00:00:00Z'
};

function metric(average: number, minimum = average, maximum = average) {
  return { average, minimum, maximum };
}

const analytics = {
  counts: { brews: 4, ratings: 8, coffees: 2 },
  top_coffees: [],
  top_recipes: [],
  flavor_counts: {},
  operator_counts: [{ profile_id: 1, display_name: 'Ada', brew_count: 4 }],
  scatter: [
    {
      brew_id: 101,
      coffee_id: 11,
      coffee: 'Atlas · Alpha',
      liking: 1,
      ratings: 1,
      rating_metrics: {
        liking: metric(1),
        acidity: metric(0),
        bitterness: metric(2),
        sweetness: metric(3),
        body: metric(2)
      },
      ratio: 16,
      temperature_c: 92,
      grinder_id: 21,
      grinder_name: 'Orbit One',
      grinder_unit: 'clicks',
      grinder_setting: 20,
      total_brew_time_s: 180,
      target_flow_g_s: null,
      overall_throughput_g_s: 1.33
    },
    {
      brew_id: 102,
      coffee_id: 11,
      coffee: 'Atlas · Alpha',
      liking: 8,
      ratings: 4,
      rating_metrics: {
        liking: metric(8, 7, 9),
        acidity: metric(4, 3, 5),
        bitterness: metric(1, 0, 2),
        sweetness: metric(4, 3, 5),
        body: metric(3, 2, 4)
      },
      ratio: 16,
      temperature_c: 92,
      grinder_id: 21,
      grinder_name: 'Orbit One',
      grinder_unit: 'clicks',
      grinder_setting: 22,
      total_brew_time_s: 200,
      target_flow_g_s: 4.5,
      overall_throughput_g_s: 1.2
    },
    {
      brew_id: 103,
      coffee_id: 11,
      coffee: 'Atlas · Alpha',
      liking: 6,
      ratings: 2,
      rating_metrics: {
        liking: metric(6, 5, 7),
        acidity: metric(2, 1, 3),
        bitterness: metric(3, 2, 4),
        sweetness: metric(2, 1, 3),
        body: metric(4, 3, 5)
      },
      ratio: 17,
      temperature_c: 94,
      grinder_id: 22,
      grinder_name: 'Orbit Two',
      grinder_unit: 'steps',
      grinder_setting: 5,
      total_brew_time_s: 210,
      target_flow_g_s: null,
      overall_throughput_g_s: 1.14
    },
    {
      brew_id: 201,
      coffee_id: 12,
      coffee: 'Beacon · Beta',
      liking: 7,
      ratings: 1,
      rating_metrics: {
        liking: metric(7),
        acidity: metric(3),
        bitterness: metric(2),
        sweetness: metric(3),
        body: metric(3)
      },
      ratio: 15.5,
      temperature_c: 91,
      grinder_id: 21,
      grinder_name: 'Orbit One',
      grinder_unit: 'clicks',
      grinder_setting: 18,
      total_brew_time_s: 175,
      target_flow_g_s: null,
      overall_throughput_g_s: 1.37
    }
  ]
};

async function mockAnalyticsPage(page: Page) {
  await page.route('**/api/v1/settings', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(settings) })
  );
  await page.route('**/api/v1/auth/bootstrap-status', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ required: false })
    })
  );
  await page.route('**/api/v1/auth/me', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(session) })
  );
  await page.route('**/api/v1/analytics', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(analytics) })
  );
}

test('recipe map exposes comparable axes, ratings, and brew details', async ({ page }) => {
  await mockAnalyticsPage(page);
  await page.goto('/analytics?kiosk=0');

  const settingsChart = page.locator('.chart-panel').filter({
    has: page.getByRole('heading', { name: 'Settings versus liking' })
  });
  await expect(settingsChart.locator('.x-tick').first()).toBeVisible();
  const xTickLabels = await settingsChart.locator('.x-tick').allTextContents();
  expect(xTickLabels.length).toBeGreaterThan(1);
  expect(new Set(xTickLabels).size).toBe(xTickLabels.length);
  expect(xTickLabels.every((tick) => Number.isFinite(Number(tick)))).toBe(true);
  await expect(settingsChart.getByText('Brew ratio (1:x)', { exact: true })).toBeVisible();
  await expect(settingsChart.getByText('Liking (1–9)', { exact: true })).toBeVisible();

  const recipeMap = page.locator('.recipe-map');
  const coffee = recipeMap.getByRole('combobox', { name: 'Map coffee', exact: true });
  const xAxis = recipeMap.getByRole('combobox', { name: 'X axis', exact: true });
  const yAxis = recipeMap.getByRole('combobox', { name: 'Y axis', exact: true });
  const colour = recipeMap.getByRole('combobox', { name: 'Colour', exact: true });

  await expect(coffee).toHaveValue('');
  await expect(recipeMap.getByText(/Choose one coffee to compare recipes/)).toBeVisible();
  await coffee.selectOption('11');
  await expect(xAxis).toHaveValue('ratio');
  await expect(yAxis).toHaveValue('temperature_c');
  await expect(xAxis.locator('option[value="temperature_c"]')).toHaveAttribute('disabled', '');
  await expect(yAxis.locator('option[value="ratio"]')).toHaveAttribute('disabled', '');

  const plot = recipeMap.getByRole('group', {
    name: 'Interactive scatter plot of Brew ratio (1:x) versus Temperature (°C), coloured by Liking'
  });
  await expect(plot).toBeVisible();
  const legend = recipeMap.getByTestId('color-legend');
  await expect(legend).toHaveAttribute('aria-label', 'Liking average colour scale from 1 to 9');

  const first = recipeMap.locator('.plot-point[data-brew-id="101"]');
  const overlap = recipeMap.locator('.plot-point[data-brew-id="102"]');
  const firstCircle = first.locator('circle');
  const overlapCircle = overlap.locator('circle');
  const firstPosition = await firstCircle.evaluate((circle) => [
    circle.getAttribute('cx'),
    circle.getAttribute('cy')
  ]);
  const overlapPosition = await overlapCircle.evaluate((circle) => [
    circle.getAttribute('cx'),
    circle.getAttribute('cy')
  ]);
  expect(firstPosition).not.toEqual(overlapPosition);
  expect(Number(await overlapCircle.getAttribute('r'))).toBeGreaterThan(
    Number(await firstCircle.getAttribute('r'))
  );
  expect(await overlapCircle.getAttribute('fill')).not.toBe(await firstCircle.getAttribute('fill'));

  await overlap.focus();
  await expect(recipeMap.getByTestId('point-details')).toContainText('8 average · 7–9 range');
  await expect(recipeMap.getByRole('link', { name: 'Open brew' })).toHaveAttribute(
    'href',
    '/brews/102'
  );
  await first.hover();
  await expect(recipeMap.getByRole('link', { name: 'Open brew' })).toHaveAttribute(
    'href',
    '/brews/101'
  );
  await expect(first).toHaveAttribute('href', '/brews/101');

  await coffee.selectOption('12');
  await expect(recipeMap.getByTestId('point-details')).toContainText(
    'Focus, hover, or tap a point to inspect its measurements.'
  );
  await expect(recipeMap.getByRole('link', { name: 'Open brew' })).toHaveCount(0);
  await recipeMap.locator('.plot-point[data-brew-id="201"]').focus();
  await expect(recipeMap.getByRole('link', { name: 'Open brew' })).toHaveAttribute(
    'href',
    '/brews/201'
  );

  await colour.selectOption('acidity');
  await expect(legend).toHaveAttribute('aria-label', 'Acidity average colour scale from 0 to 5');
  await xAxis.selectOption('target_flow_g_s');
  await expect(
    recipeMap.getByText('No rated brews have both selected measurements yet.', { exact: true })
  ).toBeVisible();

  await coffee.selectOption('11');
  await expect(recipeMap.locator('.plot-point')).toHaveCount(1);
  await xAxis.selectOption('grinder_setting');
  await expect(
    recipeMap.getByText('Choose one grinder before comparing grinder settings.', { exact: true })
  ).toBeVisible();
  const grinder = recipeMap.getByRole('combobox', { name: 'Map grinder', exact: true });
  await grinder.selectOption('21');
  await expect(recipeMap.locator('.plot-point')).toHaveCount(2);
  await expect(yAxis.locator('option[value="grinder_setting"]')).toHaveAttribute('disabled', '');

  await page.setViewportSize({ width: 360, height: 800 });
  const mobileLayout = await recipeMap.evaluate((map) => {
    const scroller = map.querySelector<HTMLElement>('[data-testid="analytics-plot"]');
    return {
      plotScrolls: Boolean(scroller && scroller.scrollWidth > scroller.clientWidth),
      pageFits: document.documentElement.scrollWidth <= document.documentElement.clientWidth
    };
  });
  expect(mobileLayout).toEqual({ plotScrolls: true, pageFits: true });
});

test('a touch point opens details first and follows its brew link on the second tap', async ({
  browser
}) => {
  const context = await browser.newContext({
    baseURL: 'http://127.0.0.1:8000',
    viewport: { width: 360, height: 800 },
    isMobile: true,
    hasTouch: true
  });
  const page = await context.newPage();
  await mockAnalyticsPage(page);
  await page.goto('/analytics?kiosk=0');
  const recipeMap = page.locator('.recipe-map');
  await recipeMap.getByRole('combobox', { name: 'Map coffee', exact: true }).selectOption('11');
  const point = recipeMap.locator('.plot-point[data-brew-id="102"]');

  await point.tap();
  await expect(page).toHaveURL(/\/analytics$/);
  await expect(recipeMap.getByRole('link', { name: 'Open brew' })).toHaveAttribute(
    'href',
    '/brews/102'
  );
  await point.tap();
  await expect(page).toHaveURL(/\/brews\/102$/);
  await context.close();
});
