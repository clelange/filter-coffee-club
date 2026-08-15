export const NORMAL_BREW_RATIO_MIN = 10;
export const NORMAL_BREW_RATIO_MAX = 25;

export function calculateBrewRatio(waterG: number, doseG: number): number {
  if (!doseG) return 0;
  const ratio = waterG / doseG;
  const rounded = Math.round(ratio * 100) / 100;
  if (
    (ratio < NORMAL_BREW_RATIO_MIN && rounded >= NORMAL_BREW_RATIO_MIN) ||
    (ratio > NORMAL_BREW_RATIO_MAX && rounded <= NORMAL_BREW_RATIO_MAX)
  ) {
    return ratio;
  }
  return rounded;
}

export function brewRatioIsUnusual(waterG: number, doseG: number): boolean {
  if (!doseG) return true;
  const ratio = waterG / doseG;
  return ratio < NORMAL_BREW_RATIO_MIN || ratio > NORMAL_BREW_RATIO_MAX;
}

export function unusualBrewRatioDescription(doseG: number, waterG: number): string {
  const ratio = calculateBrewRatio(waterG, doseG);
  return `This recipe records ${doseG} g total coffee and ${waterG} g total water, a 1:${ratio} ratio. Check that both amounts are for the whole batch.`;
}
