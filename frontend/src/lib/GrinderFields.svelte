<script lang="ts">
  import { isClickUnit } from '$lib/catalog';
  import type { GrinderFormData } from '$lib/types';

  export let form: GrinderFormData;
</script>

<div class="field-grid">
  <label>Manufacturer<input bind:value={form.manufacturer} required /></label>
  <label>Model<input bind:value={form.model} required /></label>
  <label>Setting unit<input bind:value={form.setting_unit} required /></label>
  <label>
    Step
    <input
      type="number"
      bind:value={form.setting_step}
      min={isClickUnit(form.setting_unit) ? 1 : 0.01}
      step={isClickUnit(form.setting_unit) ? 1 : 0.01}
      inputmode={isClickUnit(form.setting_unit) ? 'numeric' : 'decimal'}
      required
    />
  </label>
  <label>
    Soft minimum
    <input
      type="number"
      bind:value={form.soft_min}
      step={isClickUnit(form.setting_unit) ? 1 : 0.01}
      inputmode={isClickUnit(form.setting_unit) ? 'numeric' : 'decimal'}
    />
  </label>
  <label>
    Soft maximum
    <input
      type="number"
      bind:value={form.soft_max}
      step={isClickUnit(form.setting_unit) ? 1 : 0.01}
      inputmode={isClickUnit(form.setting_unit) ? 'numeric' : 'decimal'}
    />
  </label>
</div>
<label>Guidance<textarea bind:value={form.guidance}></textarea></label>
