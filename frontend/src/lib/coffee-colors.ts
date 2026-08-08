export const COFFEE_COLOR_PALETTE = [
  '#0072B2',
  '#D55E00',
  '#009E73',
  '#CC79A7',
  '#A6761D',
  '#6A3D9A',
  '#B2182B',
  '#4D4D4D'
] as const;

export function nextCoffeeColor(colors: string[]): string {
  const counts = new Map<string, number>();
  for (const color of colors) {
    const normalized = color.toUpperCase();
    counts.set(normalized, (counts.get(normalized) ?? 0) + 1);
  }
  return COFFEE_COLOR_PALETTE.reduce((best, color) =>
    (counts.get(color) ?? 0) < (counts.get(best) ?? 0) ? color : best
  );
}

function relativeLuminance(color: string): number {
  const channels = [1, 3, 5].map((offset) => {
    const value = Number.parseInt(color.slice(offset, offset + 2), 16) / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
}

export function contrastRatio(first: string, second: string): number {
  const light = Math.max(relativeLuminance(first), relativeLuminance(second));
  const dark = Math.min(relativeLuminance(first), relativeLuminance(second));
  return (light + 0.05) / (dark + 0.05);
}
