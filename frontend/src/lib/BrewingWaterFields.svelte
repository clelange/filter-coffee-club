<script lang="ts">
  import { untrack } from 'svelte';
  import type { WaterProfile } from './types';
  import {
    presetWater,
    waterLabel,
    waterMixDescription,
    waterPresets,
    type WaterDraft
  } from './brewing-water';
  import NumberStepper from './NumberStepper.svelte';

  let { draft = $bindable(), profile }: { draft: WaterDraft; profile: WaterProfile | null } =
    $props();
  let original = $state.raw(untrack(() => ({ ...draft })));
  const ingredients = [
    ['buffer_g', 'Buffer concentrate'],
    ['magnesium_g', 'Magnesium concentrate'],
    ['distilled_g', 'Distilled water']
  ] as const;

  function selectPreset(preset: WaterProfile['preset']) {
    original = presetWater(preset);
    draft = { ...original };
  }
</script>

<div class="water-fields">
  <label>
    Brewing water
    <select
      value={draft.preset}
      onchange={(event) => selectPreset(event.currentTarget.value as WaterProfile['preset'])}
    >
      <option>Tap water</option>
      {#each waterPresets as preset}
        <option value={preset}>{profile?.preset === preset ? waterLabel(profile) : preset}</option>
      {/each}
    </select>
  </label>
  {#if draft.preset !== 'Tap water' && original.preset !== 'Tap water'}
    {#key draft.preset}
      <details oninvalidcapture={(event) => (event.currentTarget.open = true)}>
        <summary>Adjust water recipe</summary>
        <div class="mix">
          <p class="hint">
            Enter the weights for your batch. <a
              href="https://www.baristahustle.com/diy-water-recipes-the-world-in-two-bottles/"
              target="_blank"
              rel="noreferrer">Barista Hustle concentrate recipes</a
            >
          </p>
          <div class="field-grid">
            {#each ingredients as [field, label]}
              <NumberStepper
                {label}
                bind:value={draft[field]}
                recordedValue={original[field] ?? undefined}
                step={0.000001}
                buttonIncrement={0.01}
                unit="g"
              />
            {/each}
          </div>
          {#if profile && profile.preset !== 'Tap water'}
            <p role="status">
              <strong>{waterLabel(profile)}</strong><br />{waterMixDescription(profile)}
            </p>
          {/if}
        </div>
      </details>
    {/key}
    {#if !profile}
      <p class="error" role="alert">
        Enter all three weights, with at least one greater than zero.
      </p>
    {/if}
  {/if}
</div>

<style>
  .water-fields {
    display: grid;
    gap: 0.75rem;
  }
  details {
    border: 0;
    background: transparent;
  }
  summary {
    width: fit-content;
    min-height: 44px;
    padding: 0.65rem 0.25rem;
    color: var(--coffee);
  }
  .mix {
    display: grid;
    gap: 0.75rem;
    margin: 0.25rem 0 0;
  }
  p {
    margin: 0;
  }
</style>
