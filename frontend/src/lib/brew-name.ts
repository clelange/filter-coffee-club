import type { Brew } from './types';

type BrewIdentity = Pick<Brew, 'brew_name' | 'coffee_name'>;

export function brewTitle(brew: BrewIdentity): string {
  return brew.brew_name ?? brew.coffee_name;
}

export function brewCoffeeSubtitle(brew: BrewIdentity & Pick<Brew, 'coffee_roaster'>): string {
  return brew.brew_name ? `${brew.coffee_roaster} · ${brew.coffee_name}` : brew.coffee_roaster;
}

export function namedBrewDescription(brew: Pick<Brew, 'brew_name'>, description: string): string {
  return brew.brew_name ? `${brew.brew_name} · ${description}` : description;
}
