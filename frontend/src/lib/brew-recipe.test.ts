import { describe, expect, it } from 'vitest';
import {
  applyRecipeCalculation,
  presetDeviations,
  recipeAmountError,
  snapGrinderSetting,
  type RecipeCalculationState
} from './brew-recipe';
import type { Grinder, Preset } from './types';

const baseRecipe: RecipeCalculationState = {
  basis: 'coffee',
  dose_g: 8,
  water_g: 128,
  target_ratio: 16,
  bloom_water_g: 16,
  servings: 1
};

describe('applyRecipeCalculation', () => {
  it('switches the amount basis to the value the user changed', () => {
    const waterBased = applyRecipeCalculation(baseRecipe, { type: 'water', value: 240 });
    expect(waterBased).toMatchObject({ basis: 'water', dose_g: 15, water_g: 240 });

    const ratioChanged = applyRecipeCalculation(waterBased, { type: 'ratio', value: 20 });
    expect(ratioChanged).toMatchObject({ basis: 'water', dose_g: 12, water_g: 240 });

    const coffeeBased = applyRecipeCalculation(ratioChanged, { type: 'dose', value: 10 });
    expect(coffeeBased).toMatchObject({ basis: 'coffee', dose_g: 10, water_g: 200 });
  });

  it.each([
    {
      name: 'coffee basis',
      state: baseRecipe,
      expected: { dose_g: 40, water_g: 640, bloom_water_g: 80 }
    },
    {
      name: 'water basis',
      state: { ...baseRecipe, basis: 'water' as const },
      expected: { dose_g: 40, water_g: 640, bloom_water_g: 80 }
    }
  ])('scales the full batch on $name', ({ state, expected }) => {
    expect(applyRecipeCalculation(state, { type: 'servings', value: 5 })).toMatchObject(expected);
  });

  it('keeps an explicit non-integer target separate from its rounded actual ratio', () => {
    const result = applyRecipeCalculation(
      { ...baseRecipe, basis: 'water', water_g: 120, target_ratio: 16.3 },
      { type: 'ratio', value: 16.3 }
    );
    expect(result).toMatchObject({ target_ratio: 16.3, dose_g: 7.4, water_g: 120 });
    expect(result.water_g / result.dose_g).not.toBe(result.target_ratio);
  });

  it('applies per-serving shortcuts and scales bloom water with the dose', () => {
    const fiveServings = { ...baseRecipe, servings: 5 };
    expect(applyRecipeCalculation(fiveServings, { type: 'coffee-shortcut' })).toMatchObject({
      basis: 'coffee',
      dose_g: 40,
      water_g: 640,
      bloom_water_g: 80
    });
    expect(applyRecipeCalculation(fiveServings, { type: 'water-shortcut' })).toMatchObject({
      basis: 'water',
      dose_g: 37.5,
      water_g: 600,
      bloom_water_g: 75
    });
  });
});

describe('recipe validation helpers', () => {
  it.each([
    [0.9, 128, 'The selected basis and ratio require a coffee dose between 1 and 500 g.'],
    [501, 128, 'The selected basis and ratio require a coffee dose between 1 and 500 g.'],
    [8, 0.9, 'The selected basis and ratio require a water amount between 1 and 5000 g.'],
    [8, 5001, 'The selected basis and ratio require a water amount between 1 and 5000 g.'],
    [1, 1, ''],
    [500, 5000, '']
  ])('validates calculated amount boundaries', (dose, water, expected) => {
    expect(recipeAmountError(dose as number, water as number)).toBe(expected as string);
  });
});

describe('preset conformance', () => {
  const preset: Preset = {
    id: 1,
    name: 'Balanced',
    ratio: 16.3,
    temperature_min_c: 92,
    temperature_max_c: 96,
    active: true,
    sort_order: 1,
    grinder_ranges: [{ grinder_id: 1, setting_min: 24, setting_max: 28 }]
  };

  it('reports only fields that deviate from the selected preset', () => {
    expect(
      presetDeviations({ target_ratio: 16.4, temperature_c: 97, grinder_setting: 29 }, preset, 1)
    ).toEqual(['ratio', 'temperature', 'grind']);
  });

  it('does not call a missing grinder range a recipe deviation', () => {
    expect(
      presetDeviations({ target_ratio: 16.3, temperature_c: 92, grinder_setting: 999 }, preset, 2)
    ).toEqual([]);
  });
});

describe('snapGrinderSetting', () => {
  const grinder: Grinder = {
    id: 1,
    manufacturer: 'Orbit',
    model: 'One',
    setting_unit: 'turns',
    setting_step: 0.25,
    soft_min: null,
    soft_max: null,
    guidance: null,
    archived: false,
    photo_path: null,
    photo_framing: null
  };

  it('snaps continuous settings to their configured precision', () => {
    expect(snapGrinderSetting(5.13, grinder)).toBe(5.25);
  });

  it('always snaps click grinders to whole numbers', () => {
    expect(snapGrinderSetting(5.6, { ...grinder, setting_unit: 'clicks' })).toBe(6);
  });
});
