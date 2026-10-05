import type { components } from './generated-api';
import type { AnalyticsAxisKey } from './types';

export type AnalyticsPoint = components['schemas']['AnalyticsPoint'];
type GrinderDefinition = components['schemas']['GrinderDefinitionResponse'];

export interface GrinderScale {
  key: string;
  name: string;
  label: string;
  axisLabel: string;
  unit: string;
  step: number;
  multiplier: number | null;
  grinderId: number | null;
}

export function grinderScales(
  definitions: GrinderDefinition[],
  points: AnalyticsPoint[]
): GrinderScale[] {
  const shared = definitions
    .filter((definition) => definition.reference_multiplier !== null)
    .map((definition) => ({
      key: definition.key,
      name: definition.label,
      label: `${definition.label} ${definition.setting_unit}${definition.key === 'comandante_c40' ? ' (reference)' : ''}`,
      axisLabel: `Grind (${definition.model}-equivalent ${definition.setting_unit})`,
      unit: definition.setting_unit,
      step: definition.setting_step,
      multiplier: definition.reference_multiplier,
      grinderId: null
    }));
  const custom = [
    ...new Map(
      points
        .filter((point) => point.reference_grinder_setting == null)
        .map((point) => [
          point.grinder_id,
          {
            key: `grinder:${point.grinder_id}`,
            name: point.grinder_name,
            label: `${point.grinder_name} (original ${point.grinder_unit})`,
            axisLabel: `Grinder setting (${point.grinder_unit})`,
            unit: point.grinder_unit,
            step: 1,
            multiplier: null,
            grinderId: point.grinder_id
          }
        ])
    ).values()
  ];
  return [...shared, ...custom];
}

export function grinderSetting(point: AnalyticsPoint, scale: GrinderScale): number | null {
  if (scale.grinderId !== null) {
    return point.grinder_id === scale.grinderId ? point.grinder_setting : null;
  }
  if (point.grinder_definition_key === scale.key) return point.grinder_setting;
  if (point.reference_grinder_setting == null || scale.multiplier === null) return null;
  return point.reference_grinder_setting * scale.multiplier;
}

export function convertedGrind(point: AnalyticsPoint, scale: GrinderScale | null): boolean {
  return scale !== null && scale.grinderId === null && point.grinder_definition_key !== scale.key;
}

export function chartMeasurements(
  points: AnalyticsPoint[],
  axes: AnalyticsAxisKey[],
  scale: GrinderScale | null
): { points: AnalyticsPoint[]; unconverted: number } {
  const candidates = points.filter((point) =>
    axes.every((key) => point[key] !== null && Number.isFinite(point[key]))
  );
  if (!axes.includes('grinder_setting')) return { points: candidates, unconverted: 0 };
  const comparable = candidates.filter((point) => {
    const setting = scale ? grinderSetting(point, scale) : null;
    return setting !== null && Number.isFinite(setting);
  });
  return { points: comparable, unconverted: candidates.length - comparable.length };
}
