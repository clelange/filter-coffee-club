import { describe, expect, it } from 'vitest';
import {
  chartMeasurements,
  convertedGrind,
  grinderScales,
  grinderSetting,
  type AnalyticsPoint
} from './analytics-grind';
import { grinderDefinitions } from '../../tests-fixtures/grinders';

function point(overrides: Partial<AnalyticsPoint> = {}): AnalyticsPoint {
  const metric = { average: 7, minimum: 7, maximum: 7 };
  return {
    brew_id: 1,
    coffee_id: 1,
    coffee: 'Coffee',
    coffee_color: '#0072B2',
    liking: 7,
    ratings: 1,
    rating_metrics: {
      liking: metric,
      acidity: metric,
      bitterness: metric,
      sweetness: metric,
      body: metric
    },
    ratio: 16,
    temperature_c: 92,
    grinder_id: 1,
    grinder_name: 'Comandante C40',
    grinder_unit: 'clicks',
    grinder_setting: 28,
    grinder_definition_key: 'comandante_c40',
    reference_grinder_setting: 28,
    total_brew_time_s: 180,
    target_flow_g_s: null,
    overall_throughput_g_s: 1.33,
    ...overrides
  };
}

const c40 = point();
const k6 = point({
  brew_id: 2,
  grinder_id: 2,
  grinder_name: 'KINGrinder K6',
  grinder_definition_key: 'kingrinder_k6',
  grinder_setting: 90,
  reference_grinder_setting: 28.125
});
const custom = point({
  brew_id: 3,
  grinder_id: 3,
  grinder_name: 'Custom grinder',
  grinder_unit: 'steps',
  grinder_definition_key: 'custom',
  grinder_setting: 5.25,
  reference_grinder_setting: null
});
const otherCustom = point({ ...custom, brew_id: 4, grinder_id: 4 });
const points = [c40, k6, custom, otherCustom];
const scales = grinderScales(grinderDefinitions, points);

describe('grinder scales in analytics', () => {
  it('keeps cross-grinder fractions and original observations intact', () => {
    expect(grinderSetting(k6, scales[0])).toBe(28.125);
    expect(grinderSetting(c40, scales[1])).toBeCloseTo(89.6);
    expect(grinderSetting(k6, scales[1])).toBe(90);
    expect(convertedGrind(k6, scales[0])).toBe(true);
    expect(convertedGrind(k6, scales[1])).toBe(false);
    expect(k6.grinder_setting).toBe(90);
  });

  it('combines compatible observations and counts unsupported brews', () => {
    expect(chartMeasurements(points, ['grinder_setting', 'temperature_c'], scales[0])).toEqual({
      points: [c40, k6],
      unconverted: 2
    });
    expect(chartMeasurements(points, ['temperature_c', 'grinder_setting'], scales[1])).toEqual({
      points: [c40, k6],
      unconverted: 2
    });
  });

  it('keeps custom grinders separate even when their units match', () => {
    expect(scales.slice(2).map((scale) => scale.key)).toEqual(['grinder:3', 'grinder:4']);
    expect(chartMeasurements(points, ['grinder_setting'], scales[2])).toEqual({
      points: [custom],
      unconverted: 3
    });
    expect(grinderSetting(custom, scales[2])).toBe(5.25);
    expect(convertedGrind(custom, scales[2])).toBe(false);
  });

  it('includes custom grinders on other axes and excludes missing measurements', () => {
    expect(chartMeasurements(points, ['ratio'], null)).toEqual({ points, unconverted: 0 });
    expect(
      chartMeasurements(
        [k6, point({ target_flow_g_s: 4 })],
        ['target_flow_g_s', 'grinder_setting'],
        scales[0]
      )
    ).toEqual({ points: [point({ target_flow_g_s: 4 })], unconverted: 0 });
    expect(
      grinderSetting(point({ grinder_setting: 0, reference_grinder_setting: 0 }), scales[1])
    ).toBe(0);
  });
});
