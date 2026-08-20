import type { Grinder, Preset } from './types';

export type AmountBasis = 'coffee' | 'water';
export type PresetDeviation = 'ratio' | 'temperature' | 'grind';

export interface RecipeCalculationState {
  basis: AmountBasis;
  dose_g: number;
  water_g: number;
  target_ratio: number;
  bloom_water_g: number | null;
  servings: number;
}

export type RecipeCalculationAction =
  | { type: 'dose'; value: number }
  | { type: 'water'; value: number }
  | { type: 'ratio'; value: number }
  | { type: 'servings'; value: number }
  | { type: 'coffee-shortcut' }
  | { type: 'water-shortcut' };

function roundDose(value: number): number {
  return Math.round(value * 10) / 10;
}

function scaleBloom(
  bloomWater: number | null,
  previousDose: number,
  nextDose: number
): number | null {
  if (bloomWater === null || previousDose <= 0 || previousDose === nextDose) return bloomWater;
  return Math.round(bloomWater * (nextDose / previousDose));
}

function withCoffeeBasis(state: RecipeCalculationState, dose: number): RecipeCalculationState {
  return {
    ...state,
    basis: 'coffee',
    dose_g: dose,
    water_g: Math.round(dose * state.target_ratio),
    bloom_water_g: scaleBloom(state.bloom_water_g, state.dose_g, dose)
  };
}

function withWaterBasis(state: RecipeCalculationState, water: number): RecipeCalculationState {
  const dose = roundDose(water / state.target_ratio);
  return {
    ...state,
    basis: 'water',
    dose_g: dose,
    water_g: water,
    bloom_water_g: scaleBloom(state.bloom_water_g, state.dose_g, dose)
  };
}

export function applyRecipeCalculation(
  state: RecipeCalculationState,
  action: RecipeCalculationAction
): RecipeCalculationState {
  switch (action.type) {
    case 'dose':
      return withCoffeeBasis(state, action.value);
    case 'water':
      return withWaterBasis(state, action.value);
    case 'ratio': {
      const next = { ...state, target_ratio: action.value };
      return state.basis === 'coffee'
        ? withCoffeeBasis(next, state.dose_g)
        : withWaterBasis(next, state.water_g);
    }
    case 'servings': {
      if (state.servings <= 0 || state.servings === action.value) {
        return { ...state, servings: action.value };
      }
      const scale = action.value / state.servings;
      const next = { ...state, servings: action.value };
      return state.basis === 'coffee'
        ? withCoffeeBasis(next, roundDose(state.dose_g * scale))
        : withWaterBasis(next, Math.round(state.water_g * scale));
    }
    case 'coffee-shortcut':
      return withCoffeeBasis(state, state.servings * 8);
    case 'water-shortcut':
      return withWaterBasis(state, state.servings * 120);
  }
}

export function recipeAmountError(dose: number, water: number): string {
  if (dose < 1 || dose > 500) {
    return 'The selected basis and ratio require a coffee dose between 1 and 500 g.';
  }
  if (water < 1 || water > 5000) {
    return 'The selected basis and ratio require a water amount between 1 and 5000 g.';
  }
  return '';
}

export function presetDeviations(
  recipe: Pick<RecipeCalculationState, 'target_ratio'> & {
    temperature_c: number;
    grinder_setting: number | null;
  },
  preset: Preset | undefined,
  grinderId: number
): PresetDeviation[] {
  if (!preset) return [];
  const deviations: PresetDeviation[] = [];
  if (Math.round(recipe.target_ratio * 10) !== Math.round(preset.ratio * 10)) {
    deviations.push('ratio');
  }
  if (
    recipe.temperature_c < preset.temperature_min_c ||
    recipe.temperature_c > preset.temperature_max_c
  ) {
    deviations.push('temperature');
  }
  const range = preset.grinder_ranges.find((item) => item.grinder_id === grinderId);
  if (
    range &&
    recipe.grinder_setting !== null &&
    (recipe.grinder_setting < range.setting_min || recipe.grinder_setting > range.setting_max)
  ) {
    deviations.push('grind');
  }
  return deviations;
}

export function isClickGrinder(grinder: Grinder | undefined): boolean {
  return ['click', 'clicks'].includes(grinder?.setting_unit.trim().toLowerCase() ?? '');
}

function decimalPlaces(value: number): number {
  const text = String(value);
  if (text.includes('e-')) return Number(text.split('e-')[1]);
  return text.includes('.') ? text.split('.')[1].length : 0;
}

export function snapGrinderSetting(value: number, grinder: Grinder): number {
  const step = isClickGrinder(grinder) ? 1 : grinder.setting_step;
  const snapped = Math.round(value / step) * step;
  return Number(snapped.toFixed(decimalPlaces(step)));
}

export function presetGrinderSetting(preset: Preset, grinder: Grinder): number | null {
  const range = preset.grinder_ranges.find((item) => item.grinder_id === grinder.id);
  if (!range) return null;
  return snapGrinderSetting((range.setting_min + range.setting_max) / 2, grinder);
}
