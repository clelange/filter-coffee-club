import type { AppSettings } from '$lib/types';

export function applyTheme(value: AppSettings): void {
  const root = document.documentElement;
  root.style.setProperty('--cream', value.color_cream);
  root.style.setProperty('--surface', value.color_surface);
  root.style.setProperty('--ink', value.color_ink);
  root.style.setProperty('--coffee', value.color_coffee);
  root.style.setProperty('--cyan', value.color_cyan);
  root.style.setProperty('--amber', value.color_amber);
}
