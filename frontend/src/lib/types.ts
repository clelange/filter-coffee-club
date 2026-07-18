export interface Profile {
  id: number;
  display_name: string;
  role: 'member' | 'admin';
  active: boolean;
}

export interface Session {
  profile: Profile;
  csrf_token: string;
  device_mode: 'kiosk' | 'personal';
  expires_at: string;
}

export interface AppSettings {
  app_name: string;
  subtitle: string;
  public_base_url: string | null;
  logo_path: string | null;
  color_cream: string;
  color_surface: string;
  color_ink: string;
  color_coffee: string;
  color_cyan: string;
  color_amber: string;
  public_url_needs_configuration: boolean;
}

export interface Coffee {
  id: number;
  roaster: string;
  name: string;
  country?: string | null;
  region?: string | null;
  producer?: string | null;
  process?: string | null;
  roast_level?: string | null;
  roast_date?: string | null;
  opened_date?: string | null;
  variety?: string | null;
  package_notes?: string | null;
  archived: boolean;
  cloned_from_id?: number | null;
  created_at: string;
}

export interface Grinder {
  id: number;
  manufacturer: string;
  model: string;
  setting_unit: string;
  setting_step: number;
  soft_min: number | null;
  soft_max: number | null;
  guidance: string | null;
  archived: boolean;
}

export interface Dripper {
  id: number;
  manufacturer: string | null;
  model: string;
  notes: string | null;
  archived: boolean;
}

export interface BrewFilter {
  id: number;
  name: string;
  notes: string | null;
  archived: boolean;
}

export interface PresetRange {
  grinder_id: number;
  setting_min: number;
  setting_max: number;
}

export interface Preset {
  id: number;
  name: string;
  ratio: number;
  temperature_min_c: number;
  temperature_max_c: number;
  active: boolean;
  sort_order: number;
  grinder_ranges: PresetRange[];
}

export interface BrewInput {
  coffee_id: number;
  grinder_id: number;
  dripper_id: number | null;
  filter_id: number | null;
  source_preset_id: number | null;
  dose_g: number;
  water_g: number;
  temperature_c: number;
  grinder_setting: number;
  servings: number;
  target_flow_g_s: number | null;
  bloom_water_g: number | null;
  bloom_time_s: number | null;
  pour_count: number | null;
  technique_note: string | null;
}

export interface Brew extends BrewInput {
  id: number;
  operator_id: number;
  operator_name: string;
  coffee_name: string;
  coffee_roaster: string;
  grinder_name: string;
  grinder_unit: string;
  dripper_name: string | null;
  filter_name: string | null;
  status: 'draft' | 'completed' | 'cancelled' | 'voided';
  ratio: number;
  overall_throughput_g_s: number | null;
  total_brew_time_s: number | null;
  completed_at: string | null;
  created_at: string;
  cloned_from_id: number | null;
  rating_token: string | null;
}

export interface FlavorTag {
  id: number;
  name: string;
  parent_id: number | null;
  active: boolean;
  sort_order: number;
}

export interface RatingInput {
  liking: number;
  acidity: number;
  bitterness: number;
  sweetness: number;
  body: number;
  flavor_tag_ids: number[];
}

export interface RatingItem extends RatingInput {
  profile_id: number;
  profile_name: string;
  updated_at: string;
}

export interface RatingSummary {
  can_view: boolean;
  own_rating: RatingItem | null;
  ratings: RatingItem[];
  count: number;
  averages: Record<string, number>;
  flavor_counts: Record<string, number>;
}

