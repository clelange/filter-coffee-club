import { describe, expect, it } from 'vitest';
import type { GrinderFormData } from './types';
import { formatGrinderSetting, grinderPayload } from './catalog';

describe('formatGrinderSetting', () => {
  it('formats total clicks with the definition rotation helper', () => {
    const grinder = { setting_unit: 'clicks' };
    const definition = { clicks_per_rotation: 60 };
    expect(formatGrinderSetting(96, grinder, definition)).toBe('96 clicks · 1 turn + 36');
    expect(formatGrinderSetting(120, grinder, definition)).toBe('120 clicks · 2 turns');
  });

  it('uses the grinder unit when no rotation metadata exists', () => {
    expect(formatGrinderSetting(30, { setting_unit: 'clicks' }, null)).toBe('30 clicks');
    expect(formatGrinderSetting(5.5, { setting_unit: 'turns' }, null)).toBe('5.5 turns');
  });
});

describe('grinderPayload', () => {
  it('normalizes cleared optional numeric fields to explicit nulls', () => {
    const form = {
      definition_key: 'custom',
      manufacturer: 'Orbit',
      model: 'One',
      setting_unit: 'turns',
      setting_step: 0.25,
      soft_min: undefined,
      soft_max: undefined,
      guidance: '',
      preset_ranges: [{ preset_id: 7, setting_min: undefined, setting_max: undefined }]
    } as unknown as GrinderFormData;

    expect(grinderPayload(form)).toMatchObject({
      soft_min: null,
      soft_max: null,
      preset_ranges: [{ preset_id: 7, setting_min: null, setting_max: null }]
    });
  });
});
