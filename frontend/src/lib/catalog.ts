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
  GrinderFormData
} from './types';

export function emptyCoffeeForm(): CoffeeFormData {
  return {
    roaster: '',
    name: '',
    country: '',
    region: '',
    producer: '',
    process: '',
    roast_level: '',
    roast_date: '',
    opened_date: '',
    variety: '',
    package_notes: ''
  };
}

export function coffeeToForm(coffee: Coffee): CoffeeFormData {
  return {
    roaster: coffee.roaster,
    name: coffee.name,
    country: coffee.country ?? '',
    region: coffee.region ?? '',
    producer: coffee.producer ?? '',
    process: coffee.process ?? '',
    roast_level: coffee.roast_level ?? '',
    roast_date: coffee.roast_date ?? '',
    opened_date: coffee.opened_date ?? '',
    variety: coffee.variety ?? '',
    package_notes: coffee.package_notes ?? ''
  };
}

export function coffeePayload(form: CoffeeFormData): Record<string, string | null> {
  return Object.fromEntries(
    Object.entries(form).map(([key, value]) => [key, value.trim() || null])
  );
}

export function emptyGrinderForm(): GrinderFormData {
  return {
    manufacturer: '',
    model: '',
    setting_unit: 'clicks',
    setting_step: 1,
    soft_min: 0,
    soft_max: 50,
    guidance: ''
  };
}

export function grinderToForm(item: Grinder): GrinderFormData {
  return {
    manufacturer: item.manufacturer,
    model: item.model,
    setting_unit: item.setting_unit,
    setting_step: item.setting_step,
    soft_min: item.soft_min,
    soft_max: item.soft_max,
    guidance: item.guidance ?? ''
  };
}

export function grinderPayload(form: GrinderFormData) {
  return { ...form, guidance: form.guidance.trim() || null };
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
