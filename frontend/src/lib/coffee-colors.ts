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

function rgb(color: string): number[] {
  return [1, 3, 5].map((offset) => Number.parseInt(color.slice(offset, offset + 2), 16));
}

export function nextCoffeeColor(colors: string[], surface = '#FFFDFC'): string {
  const used = new Set(colors.map((color) => color.toUpperCase()));
  for (const color of COFFEE_COLOR_PALETTE) {
    if (!used.has(color) && contrastRatio(color, surface) >= 3) return color;
  }
  const peers = [...used].map(rgb);
  let best = relativeLuminance(surface) > 0.179 ? '#000000' : '#FFFFFF';
  let bestDistance = -1;
  let candidates = 0;
  for (let index = 0; index < 2 ** 24 && candidates < 64; index++) {
    const color = `#${((index * 0x9e3779 + 0x4b6a80) & 0xffffff).toString(16).padStart(6, '0').toUpperCase()}`;
    if (used.has(color) || contrastRatio(color, surface) < 3) continue;
    candidates++;
    const channels = rgb(color);
    const distance = peers.length
      ? Math.min(
          ...peers.map((peer) =>
            channels.reduce((sum, channel, i) => sum + (channel - peer[i]) ** 2, 0)
          )
        )
      : 0;
    if (distance > bestDistance) {
      best = color;
      bestDistance = distance;
    }
  }
  return best;
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
