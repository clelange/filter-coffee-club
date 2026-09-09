import { describe, expect, it } from 'vitest';
import { COFFEE_COLOR_PALETTE, contrastRatio, nextCoffeeColor } from './coffee-colors';

describe('automatic coffee colours', () => {
  it('extends the existing palette without duplicates and keeps the preview stable', () => {
    const colors: string[] = [...COFFEE_COLOR_PALETTE];
    for (let i = 0; i < 100; i++) {
      const next = nextCoffeeColor(colors);
      expect(colors).not.toContain(next);
      expect(contrastRatio(next, '#FFFDFC')).toBeGreaterThanOrEqual(3);
      colors.push(next);
    }
    expect(colors.slice(0, 8)).toEqual(COFFEE_COLOR_PALETTE);
    expect(nextCoffeeColor(colors)).toBe(nextCoffeeColor([...colors].reverse()));
  });

  it('selects visible colours for a dark configured surface', () => {
    const colors: string[] = [];
    for (let i = 0; i < 12; i++) {
      const next = nextCoffeeColor(colors, '#241C19');
      expect(colors).not.toContain(next);
      expect(contrastRatio(next, '#241C19')).toBeGreaterThanOrEqual(3);
      colors.push(next);
    }
  });
});
