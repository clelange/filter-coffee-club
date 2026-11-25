export const likingScale = { key: 'liking', label: 'Liking', maximum: 9 } as const;
export const intensityScales = [
  { key: 'acidity', label: 'Acidity', maximum: 5 },
  { key: 'bitterness', label: 'Bitterness', maximum: 5 },
  { key: 'sweetness', label: 'Sweetness', maximum: 5 },
  { key: 'body', label: 'Body', maximum: 5 }
] as const;
export const ratingScales = [likingScale, ...intensityScales] as const;
export type RatingScaleKey = (typeof ratingScales)[number]['key'];
