<script lang="ts">
  let {
    label,
    value = $bindable(),
    step = 1,
    min = 0,
    max = Number.POSITIVE_INFINITY,
    unit = '',
    inputmode = 'decimal'
  }: {
    label: string;
    value: number;
    step?: number;
    min?: number;
    max?: number;
    unit?: string;
    inputmode?: 'numeric' | 'decimal';
  } = $props();

  function adjust(direction: number) {
    const next = Math.min(max, Math.max(min, Number(value) + direction * step));
    value = Math.round(next * 1000) / 1000;
  }
</script>

<div class="stepper-field">
  <span class="stepper-label">{label}</span>
  <div class="stepper" role="group" aria-label={label}>
    <button type="button" aria-label={`Decrease ${label}`} onclick={() => adjust(-1)}>−</button>
    <input aria-label={label} type="number" bind:value {min} {max} {step} {inputmode} required />
    {#if unit}<b>{unit}</b>{/if}
    <button type="button" aria-label={`Increase ${label}`} onclick={() => adjust(1)}>+</button>
  </div>
</div>

<style>
  .stepper-field {
    display: grid;
    gap: 7px;
    min-width: 0;
  }
  .stepper-label {
    font-weight: 750;
  }
  .stepper {
    display: grid;
    grid-template-columns: 48px minmax(70px, 1fr) auto 48px;
    align-items: center;
    overflow: hidden;
    border: 1px solid color-mix(in srgb, var(--coffee) 28%, var(--cream));
    border-radius: 12px;
    background: var(--surface);
  }
  button {
    min-width: 48px;
    min-height: 52px;
    border: 0;
    background: color-mix(in srgb, var(--coffee) 8%, var(--surface));
    color: var(--ink);
    cursor: pointer;
    font-size: 1.45rem;
    font-weight: 800;
  }
  input {
    min-width: 0;
    min-height: 52px;
    padding: 10px;
    border: 0;
    border-radius: 0;
    background: transparent;
    text-align: center;
    font-size: 1.25rem;
    font-weight: 850;
    appearance: textfield;
  }
  input::-webkit-inner-spin-button {
    appearance: none;
  }
  b {
    color: var(--muted);
    font-size: 0.82rem;
  }
</style>
