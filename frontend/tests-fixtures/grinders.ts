import type { components } from '../src/lib/generated-api';

export const grinderDefinitions: components['schemas']['GrinderDefinitionResponse'][] = [
  {
    key: 'comandante_c40',
    label: 'Comandante C40',
    manufacturer: 'Comandante',
    model: 'C40',
    setting_unit: 'clicks',
    setting_step: 1,
    soft_min: 0,
    soft_max: 50,
    guidance: null,
    reference_multiplier: 1,
    clicks_per_rotation: null
  },
  {
    key: 'kingrinder_k6',
    label: 'KINGrinder K6',
    manufacturer: 'KINGrinder',
    model: 'K6',
    setting_unit: 'clicks',
    setting_step: 1,
    soft_min: 15,
    soft_max: 150,
    guidance: null,
    reference_multiplier: 3.2,
    clicks_per_rotation: 60
  },
  {
    key: 'custom',
    label: 'Custom',
    manufacturer: null,
    model: null,
    setting_unit: 'clicks',
    setting_step: 1,
    soft_min: 0,
    soft_max: 50,
    guidance: null,
    reference_multiplier: null,
    clicks_per_rotation: null
  }
];
