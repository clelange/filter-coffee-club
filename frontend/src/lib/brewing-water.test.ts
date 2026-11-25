import { describe, expect, it } from 'vitest';
import {
  isValidWaterProfile,
  presetWater,
  waterLabel,
  waterMixDescription,
  waterPresets
} from './brewing-water';

describe('brewing water', () => {
  it.each(waterPresets)('preserves the %s preset at different batch sizes', (preset) => {
    const original = presetWater(preset);
    if (original.preset === 'Tap water') throw new Error('Expected a mineral water recipe');
    const halfBatch = {
      preset,
      buffer_g: original.buffer_g / 2,
      magnesium_g: original.magnesium_g / 2,
      distilled_g: original.distilled_g / 2
    };
    expect(waterLabel(halfBatch)).toBe(preset);
    expect(waterMixDescription(halfBatch)).toBe(waterMixDescription(original));
    const shown = [...waterMixDescription(original).matchAll(/(\d+\.\d) g/g)];
    expect(shown.map((match) => Math.round(Number(match[1]) * 10)).reduce((a, b) => a + b)).toBe(
      10_000
    );
  });

  it('balances display rounding for equal parts', () => {
    expect(
      waterMixDescription({
        preset: 'SCA',
        buffer_g: 0.01,
        magnesium_g: 0.01,
        distilled_g: 0.01
      })
    ).toBe(
      'Per litre · 333.4 g buffer concentrate · 333.3 g magnesium concentrate · 333.3 g distilled water'
    );
  });

  it('checks weights before submitting a batch', () => {
    const fineAdjustment = {
      preset: 'SCA',
      buffer_g: 0.01,
      magnesium_g: 0,
      distilled_g: 999.99
    } as const;
    expect(isValidWaterProfile(fineAdjustment)).toBe(true);
    expect(
      isValidWaterProfile({ preset: 'SCA', buffer_g: null, magnesium_g: 0, distilled_g: 500 })
    ).toBe(false);
    expect(
      isValidWaterProfile({ preset: 'SCA', buffer_g: 0, magnesium_g: 0, distilled_g: 0 })
    ).toBe(false);
  });
});
