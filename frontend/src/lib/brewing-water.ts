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

// Allocate whole units by largest remainder. Ingredient order breaks exact ties.
function apportion(weights: bigint[], units: bigint): bigint[] {
  const total = weights.reduce((a, b) => a + b);
  const numerators = weights.map((weight) => weight * units);
  const shares = numerators.map((n) => n / total);
  const remainders = numerators.map((n) => n % total);
  const order = [0, 1, 2].sort((a, b) => Number(remainders[b] - remainders[a]));
  const remaining = units - shares.reduce((a, b) => a + b);
  for (const i of order.slice(0, Number(remaining))) shares[i]++;
  return shares;
}

function microgramsPerLitre(water: MineralWater): bigint[] {
  // Use the same decimal weights as the JSON request, including scientific notation.
  const parts = [water.buffer_g, water.magnesium_g, water.distilled_g].map((weight) => {
    const [mantissa, exponent = '0'] = String(weight).split('e');
    const [whole, fraction = ''] = mantissa.split('.');
    return { digits: BigInt(whole + fraction), power: Number(exponent) - fraction.length };
  });
  const commonPower = Math.min(...parts.map((part) => part.power));
  const weights = parts.map(({ digits, power }) => digits * 10n ** BigInt(power - commonPower));
  return apportion(weights, 1_000_000_000n);
}

export function waterMixDescription(water: MineralWater): string {
  // Round the saved one-litre profile to display precision, even in the unsaved preview.
  const tenths = apportion(microgramsPerLitre(water), 10_000n);
  const [buffer, magnesium, distilled] = tenths.map((value) => (Number(value) / 10).toFixed(1));
  return `Per litre · ${buffer} g buffer concentrate · ${magnesium} g magnesium concentrate · ${distilled} g distilled water`;
}

export function waterLabel(water: WaterProfile): string {
  if (water.preset === 'Tap water') return water.preset;
  const recipe = recipes[water.preset];
  const matches = microgramsPerLitre(water).every(
    (micrograms, i) => Number(micrograms) === Math.round(recipe[i] * 1_000_000)
  );
  return matches ? water.preset : `${water.preset} (adjusted)`;
}
