import type { PhotoFraming } from '$lib/types';

export function photoFramingStyle(framing: PhotoFraming): string {
  const x = framing.focus_x * 100;
  const y = framing.focus_y * 100;
  return `object-position: ${x}% ${y}%; transform: scale(${framing.zoom}); transform-origin: ${x}% ${y}%;`;
}
