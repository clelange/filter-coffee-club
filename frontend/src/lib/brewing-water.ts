import type { MineralWater, WaterProfile } from './types';

// One-litre weights of buffer concentrate, magnesium concentrate and distilled water.
const recipes: Record<MineralWater['preset'], [number, number, number]> = {
  Melbourne: [11.5, 23.7, 964.8],
  'WOC Budapest': [40.1, 51.2, 908.7],
  SCA: [40.1, 68.6, 891.3],
  'Barista Hustle Water Recipe': [40.1, 80.7, 879.2],
  'Rao Water': [50.1, 75.7, 874.2],
  'Hendon Water': [30.8, 99.9, 869.3],
  // The published 35.1 / 126.1 / 838.9 g batch totals 1,000.1 g.
  'Pretty Hard': [35.09649, 126.087391, 838.816119],
  'Hard dot AF': [45.2, 176.8, 778]
};

export const waterPresets = Object.keys(recipes) as MineralWater['preset'][];
export type WaterDraft =
  | { preset: 'Tap water' }
  | {
      preset: MineralWater['preset'];
      buffer_g: number | null;
      magnesium_g: number | null;
      distilled_g: number | null;
    };

export function presetWater(preset: WaterProfile['preset']): WaterProfile {
  if (preset === 'Tap water') return { preset };
  const [buffer_g, magnesium_g, distilled_g] = recipes[preset];
  return { preset, buffer_g, magnesium_g, distilled_g };
}

export function isValidWaterProfile(draft: WaterDraft): draft is WaterProfile {
  if (draft.preset === 'Tap water') return true;
  const weights = [draft.buffer_g, draft.magnesium_g, draft.distilled_g];
  return (
    weights.every((w) => w !== null && Number.isFinite(w) && w >= 0) &&
    weights.some((w) => w !== null && w > 0)
  );
}

// Display calculations only. The brew API normalises the submitted batch for storage.
function gramsPerLitre(water: MineralWater): number[] {
  const weights = [water.buffer_g, water.magnesium_g, water.distilled_g];
  const largest = Math.max(...weights);
  const parts = weights.map((weight) => weight / largest);
  const total = parts.reduce((a, b) => a + b, 0);
  return parts.map((part) => (part / total) * 1000);
}

export function waterMixDescription(water: MineralWater): string {
  const portions = gramsPerLitre(water).map((grams) => grams * 10);
  const tenths = portions.map(Math.floor);
  const order = [0, 1, 2].sort((a, b) => portions[b] - tenths[b] - (portions[a] - tenths[a]));
  const remaining = 10_000 - tenths.reduce((a, b) => a + b, 0);
  for (const i of order.slice(0, remaining)) tenths[i]++;
  const [buffer, magnesium, distilled] = tenths.map((value) => (value / 10).toFixed(1));
  return `Per litre · ${buffer} g buffer concentrate · ${magnesium} g magnesium concentrate · ${distilled} g distilled water`;
}

export function waterLabel(water: WaterProfile): string {
  if (water.preset === 'Tap water') return water.preset;
  const recipe = recipes[water.preset];
  // Compare ratios within the microgram resolution of a saved profile.
  const matches = gramsPerLitre(water).every((grams, i) => Math.abs(grams - recipe[i]) < 0.000001);
  return matches ? water.preset : `${water.preset} (adjusted)`;
}
