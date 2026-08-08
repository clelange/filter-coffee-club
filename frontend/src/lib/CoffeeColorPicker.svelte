<script lang="ts">
  import { COFFEE_COLOR_PALETTE, contrastRatio, nextCoffeeColor } from '$lib/coffee-colors';
  import type { Coffee } from '$lib/types';

  export let value: string;
  export let coffees: Coffee[] = [];
  export let currentCoffeeId: number | null = null;
  export let surfaceColor = '#FFFDFC';

  $: peers = coffees.filter((coffee) => coffee.id !== currentCoffeeId);
  $: effectiveColor = value || nextCoffeeColor(peers.map((coffee) => coffee.chart_color));
  $: duplicates = peers.filter(
    (coffee) => coffee.chart_color.toUpperCase() === effectiveColor.toUpperCase()
  );
  $: lowContrast = contrastRatio(effectiveColor, surfaceColor) < 3;

  function chooseCustom(event: Event): void {
    value = (event.currentTarget as HTMLInputElement).value.toUpperCase();
  }
</script>

<fieldset class="color-picker">
  <legend>Chart color</legend>
  <p class="hint">Used to distinguish this coffee in recipe comparisons.</p>
  <div class="swatches" role="group" aria-label="Suggested chart colors">
    <button
      class="swatch auto"
      class:chosen={!value}
      type="button"
      aria-pressed={!value}
      onclick={() => (value = '')}
    >
      <i style={`--swatch:${effectiveColor}`}></i><span>Automatic</span>
    </button>
    {#each COFFEE_COLOR_PALETTE as color}
      <button
        class="swatch"
        class:chosen={value === color}
        type="button"
        aria-label={`Use chart color ${color}`}
        aria-pressed={value === color}
        title={color}
        onclick={() => (value = color)}
      >
        <i style={`--swatch:${color}`}></i>
      </button>
    {/each}
    <label class="custom-color">
      <span>Custom</span>
      <input
        type="color"
        aria-label="Custom chart color"
        value={effectiveColor}
        oninput={chooseCustom}
      />
    </label>
  </div>
  <div class="preview" style={`--preview:${effectiveColor};--preview-surface:${surfaceColor}`}>
    <i></i><span>{value ? effectiveColor : `${effectiveColor} suggested automatically`}</span>
  </div>
  {#if duplicates.length}
    <p class="color-warning" role="status">
      Also used by {duplicates.map((coffee) => `${coffee.roaster} · ${coffee.name}`).join(', ')}.
      You can still save this color.
    </p>
  {/if}
  {#if lowContrast}
    <p class="color-warning" role="status">
      This color may be difficult to see against the current surface color. You can still save it.
    </p>
  {/if}
</fieldset>

<style>
  .color-picker {
    display: grid;
    gap: 10px;
    min-width: 0;
  }
  .color-picker p {
    margin: 0;
  }
  .swatches {
    display: flex;
    flex-wrap: wrap;
    align-items: stretch;
    gap: 8px;
  }
  .swatch {
    display: grid;
    place-items: center;
    min-width: 48px;
    min-height: 48px;
    padding: 6px;
    border: 2px solid transparent;
    border-radius: 12px;
    background: var(--surface);
    color: var(--ink);
    cursor: pointer;
  }
  .swatch.chosen {
    border-color: var(--ink);
  }
  .swatch i,
  .preview i {
    display: block;
    width: 28px;
    height: 28px;
    border: 1px solid color-mix(in srgb, var(--ink) 28%, transparent);
    border-radius: 999px;
    background: var(--swatch);
  }
  .swatch.auto {
    grid-auto-flow: column;
    gap: 7px;
    padding-inline: 10px;
  }
  .swatch.auto span,
  .custom-color span {
    font-size: 0.75rem;
    font-weight: 800;
  }
  .custom-color {
    display: grid;
    grid-auto-flow: column;
    align-items: center;
    gap: 8px;
    min-height: 48px;
    padding: 6px 9px;
    border: 1px solid var(--line);
    border-radius: 12px;
    background: var(--surface);
  }
  .custom-color input {
    width: 38px;
    height: 34px;
    padding: 2px;
    cursor: pointer;
  }
  .preview {
    display: flex;
    align-items: center;
    gap: 9px;
    width: fit-content;
    padding: 8px 11px;
    border: 1px solid var(--line);
    border-radius: 12px;
    background: var(--preview-surface);
    color: var(--ink);
    font-size: 0.78rem;
    font-weight: 700;
  }
  .preview i {
    --swatch: var(--preview);
    width: 22px;
    height: 22px;
  }
  .color-warning {
    max-width: 70ch;
    color: color-mix(in srgb, var(--amber) 62%, var(--ink));
    font-size: 0.8rem;
    font-weight: 650;
    line-height: 1.45;
  }
</style>
