<script lang="ts">
  import { isClickUnit } from '$lib/catalog';
  import type { GrinderDefinition, GrinderFormData, Preset } from '$lib/types';

  export let form: GrinderFormData;
  export let definitions: GrinderDefinition[] = [];
  export let presets: Preset[] = [];
  export let editing = false;

  $: selectedDefinition = definitions.find((item) => item.key === form.definition_key);
  $: custom = form.definition_key === 'custom';
  $: step = isClickUnit(form.setting_unit) ? 1 : form.setting_step || 0.01;

  function selectDefinition() {
    const definition = definitions.find((item) => item.key === form.definition_key);
    if (!definition) return;
    if (definition.key === 'custom') {
      form.manufacturer = '';
      form.model = '';
      form.setting_unit = definition.setting_unit;
      form.setting_step = definition.setting_step;
      form.soft_min = definition.soft_min;
      form.soft_max = definition.soft_max;
      form.guidance = '';
      return;
    }
    form.manufacturer = definition.manufacturer ?? '';
    form.model = definition.model ?? '';
    form.setting_unit = definition.setting_unit;
    form.setting_step = definition.setting_step;
    form.soft_min = definition.soft_min;
    form.soft_max = definition.soft_max;
    form.guidance = definition.guidance ?? '';
  }

  function presetFor(id: number): Preset | undefined {
    return presets.find((preset) => preset.id === id);
  }

  function hasNumericValue(value: number | null | undefined): boolean {
    return value !== null && value !== undefined && Number.isFinite(value);
  }
</script>

{#if !editing}
  <label>
    Grinder model
    <select bind:value={form.definition_key} onchange={selectDefinition} required>
      <option value="" disabled>Choose a grinder model</option>
      {#each definitions as definition}
        <option value={definition.key}>{definition.label}</option>
      {/each}
    </select>
  </label>
{/if}

{#if selectedDefinition && !custom}
  <div class="definition-summary">
    <strong>{selectedDefinition.label}</strong>
    <span>
      {selectedDefinition.setting_unit} · step {selectedDefinition.setting_step} · usual range
      {selectedDefinition.soft_min ?? '—'}–{selectedDefinition.soft_max ?? '—'}
    </span>
    {#if selectedDefinition.reference_multiplier === 1}
      <span>FCC reference grinder; preset ranges are entered in C40 clicks.</span>
    {:else if selectedDefinition.reference_multiplier}
      <span>
        FCC presets use C40 × {selectedDefinition.reference_multiplier}, rounded to whole clicks.
        {#if selectedDefinition.clicks_per_rotation}
          One full dial turn is {selectedDefinition.clicks_per_rotation} clicks.
        {/if}
      </span>
    {/if}
    {#if selectedDefinition.guidance}<span>{selectedDefinition.guidance}</span>{/if}
  </div>
{:else if custom}
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
        {step}
        inputmode={isClickUnit(form.setting_unit) ? 'numeric' : 'decimal'}
      />
    </label>
    <label>
      Soft maximum
      <input
        type="number"
        bind:value={form.soft_max}
        {step}
        inputmode={isClickUnit(form.setting_unit) ? 'numeric' : 'decimal'}
      />
    </label>
  </div>
  <label>Guidance<textarea bind:value={form.guidance}></textarea></label>

  {#if !editing && form.preset_ranges.length}
    <fieldset class="custom-ranges">
      <legend>Optional preset ranges</legend>
      <p class="muted">
        Add both values to give this grinder guidance for a preset. Leave both blank to require a
        manual setting while brewing.
      </p>
      {#each form.preset_ranges as range}
        <div class="preset-range">
          <strong>{presetFor(range.preset_id)?.name ?? `Preset ${range.preset_id}`}</strong>
          <label>
            Minimum
            <input
              type="number"
              bind:value={range.setting_min}
              {step}
              inputmode={isClickUnit(form.setting_unit) ? 'numeric' : 'decimal'}
              required={hasNumericValue(range.setting_max)}
            />
          </label>
          <label>
            Maximum
            <input
              type="number"
              bind:value={range.setting_max}
              {step}
              inputmode={isClickUnit(form.setting_unit) ? 'numeric' : 'decimal'}
              required={hasNumericValue(range.setting_min)}
            />
          </label>
        </div>
      {/each}
    </fieldset>
  {/if}
{/if}

<style>
  .definition-summary {
    display: grid;
    gap: 5px;
    padding: 14px;
    border: 1px solid var(--line);
    border-radius: 12px;
    background: color-mix(in srgb, var(--cyan) 7%, var(--surface));
  }
  .definition-summary span,
  .custom-ranges .muted {
    color: var(--muted);
    font-size: 0.82rem;
  }
  .custom-ranges {
    display: grid;
    gap: 10px;
  }
  .custom-ranges .muted {
    margin: 0;
  }
  .preset-range {
    display: grid;
    grid-template-columns: minmax(180px, 1fr) minmax(110px, 0.5fr) minmax(110px, 0.5fr);
    align-items: end;
    gap: 10px;
  }
  .preset-range strong {
    padding-bottom: 13px;
  }
  @media (max-width: 600px) {
    .preset-range {
      grid-template-columns: 1fr;
    }
    .preset-range strong {
      padding-bottom: 0;
    }
  }
</style>
