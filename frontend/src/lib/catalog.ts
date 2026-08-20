import type {
  BrewFilter,
  CatalogKind,
  CatalogUsageItem,
  Coffee,
  CoffeeFormData,
  Dripper,
  DripperFormData,
  FilterFormData,
  Grinder,
  GrinderDefinition,
  GrinderFormData,
  Preset
} from './types';

export function emptyCoffeeForm(): CoffeeFormData {
  return {
    roaster: '',
    name: '',
    country: '',
    region: '',
    producer: '',
    purchase_location: '',
    process: '',
    roast_level: '',
    roast_date: '',
    opened_date: '',
    variety: '',
    package_notes: '',
    chart_color: ''
  };
}

export function coffeeToForm(coffee: Coffee): CoffeeFormData {
  return {
    roaster: coffee.roaster,
    name: coffee.name,
    country: coffee.country ?? '',
    region: coffee.region ?? '',
    producer: coffee.producer ?? '',
    purchase_location: coffee.purchase_location ?? '',
    process: coffee.process ?? '',
    roast_level: coffee.roast_level ?? '',
    roast_date: coffee.roast_date ?? '',
    opened_date: coffee.opened_date ?? '',
    variety: coffee.variety ?? '',
    package_notes: coffee.package_notes ?? '',
    chart_color: coffee.chart_color
  };
}

export function coffeePayload(form: CoffeeFormData): Record<string, string | null> {
  return Object.fromEntries(
    Object.entries(form).map(([key, value]) => [key, value.trim() || null])
  );
}

export function emptyGrinderForm(presets: Preset[] = []): GrinderFormData {
  return {
    definition_key: '',
    manufacturer: '',
    model: '',
    setting_unit: 'clicks',
    setting_step: 1,
    soft_min: 0,
    soft_max: 50,
    guidance: '',
    preset_ranges: presets
      .filter((preset) => preset.active)
      .map((preset) => ({ preset_id: preset.id, setting_min: null, setting_max: null }))
  };
}

export function grinderToForm(item: Grinder): GrinderFormData {
  return {
    definition_key: item.definition_key,
    manufacturer: item.manufacturer,
    model: item.model,
    setting_unit: item.setting_unit,
    setting_step: item.setting_step,
    soft_min: item.soft_min,
    soft_max: item.soft_max,
    guidance: item.guidance ?? '',
    preset_ranges: []
  };
}

export function grinderPayload(form: GrinderFormData) {
  if (form.definition_key && form.definition_key !== 'custom') {
    return { definition_key: form.definition_key };
  }
  return {
    definition_key: 'custom',
    manufacturer: form.manufacturer,
    model: form.model,
    setting_unit: form.setting_unit,
    setting_step: form.setting_step,
    soft_min: form.soft_min ?? null,
    soft_max: form.soft_max ?? null,
    guidance: form.guidance.trim() || null,
    preset_ranges: form.preset_ranges.map((range) => ({
      preset_id: range.preset_id,
      setting_min: range.setting_min ?? null,
      setting_max: range.setting_max ?? null
    }))
  };
}

export function grinderUpdatePayload(form: GrinderFormData) {
  return {
    manufacturer: form.manufacturer,
    model: form.model,
    setting_unit: form.setting_unit,
    setting_step: form.setting_step,
    soft_min: form.soft_min ?? null,
    soft_max: form.soft_max ?? null,
    guidance: form.guidance.trim() || null
  };
}

export function formatGrinderSetting(
  value: number,
  grinder: Pick<Grinder, 'setting_unit'>,
  definition?: Pick<GrinderDefinition, 'clicks_per_rotation'> | null
): string {
  const total = `${value} ${grinder.setting_unit}`;
  const clicksPerRotation = definition?.clicks_per_rotation;
  if (!clicksPerRotation) return total;
  const turns = Math.floor(value / clicksPerRotation);
  const clicks = value % clicksPerRotation;
  if (turns === 0) return total;
  const turnLabel = `${turns} ${turns === 1 ? 'turn' : 'turns'}`;
  return `${total} · ${turnLabel}${clicks ? ` + ${clicks}` : ''}`;
}

export function emptyDripperForm(): DripperFormData {
  return { manufacturer: '', model: '', notes: '' };
}

export function dripperToForm(item: Dripper): DripperFormData {
  return {
    manufacturer: item.manufacturer ?? '',
    model: item.model,
    notes: item.notes ?? ''
  };
}

export function dripperPayload(form: DripperFormData) {
  return {
    manufacturer: form.manufacturer.trim() || null,
    model: form.model,
    notes: form.notes.trim() || null
  };
}

export function emptyFilterForm(): FilterFormData {
  return { name: '', notes: '' };
}

export function filterToForm(item: BrewFilter): FilterFormData {
  return { name: item.name, notes: item.notes ?? '' };
}

export function filterPayload(form: FilterFormData) {
  return { name: form.name, notes: form.notes.trim() || null };
}

export function usageFor(
  usage: CatalogUsageItem[],
  kind: CatalogKind,
  itemId: number
): CatalogUsageItem | null {
  return usage.find((item) => item.kind === kind && item.item_id === itemId) ?? null;
}

export function formatCatalogDate(value: string | null | undefined): string {
  if (!value) return 'Never';
  return new Intl.DateTimeFormat(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric'
  }).format(new Date(value));
}

export function formatCatalogNumber(value: number | null, suffix = ''): string {
  return value === null
    ? '—'
    : `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}${suffix}`;
}

export function isClickUnit(unit: string): boolean {
  return ['click', 'clicks'].includes(unit.trim().toLowerCase());
}
