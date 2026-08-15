export const NORMAL_BREW_RATIO_MIN = 10;
export const NORMAL_BREW_RATIO_MAX = 25;

export function calculateBrewRatio(waterG: number, doseG: number): number {
  if (!doseG) return 0;
  return Math.round((waterG / doseG) * 100) / 100;
}

export function brewRatioIsUnusual(waterG: number, doseG: number): boolean {
  const ratio = calculateBrewRatio(waterG, doseG);
  return ratio < NORMAL_BREW_RATIO_MIN || ratio > NORMAL_BREW_RATIO_MAX;
}

export function unusualBrewRatioDescription(doseG: number, waterG: number): string {
  const ratio = calculateBrewRatio(waterG, doseG);
  return `This recipe records ${doseG} g total coffee and ${waterG} g total water, a 1:${ratio} ratio. Check that both amounts are for the whole batch.`;
}
