<script lang="ts">
  import { tick } from 'svelte';
  import { deviceModeStore } from './device';

  let {
    label,
    value = $bindable(),
    step = 1,
    min = 0,
    max = Number.POSITIVE_INFINITY,
    unit = '',
    inputmode = 'decimal',
    nullable = false
  }: {
    label: string;
    value: number | null;
    step?: number;
    min?: number;
    max?: number;
    unit?: string;
    inputmode?: 'numeric' | 'decimal';
    nullable?: boolean;
  } = $props();

  let padOpen = $state(false);
  let draft = $state('');
  let error = $state('');
  let dialog = $state<HTMLElement>();
  let valueButton = $state<HTMLButtonElement>();

  const precision = $derived(decimalPlaces(step));

  function decimalPlaces(number: number): number {
    const text = String(number);
    if (text.includes('e-')) return Number(text.split('e-')[1]);
    return text.includes('.') ? text.split('.')[1].length : 0;
  }

  function adjust(direction: number) {
    const base = value ?? Math.max(min, 0);
    const next = Math.min(max, Math.max(min, Number(base) + direction * step));
    value = Number(next.toFixed(precision));
  }

  async function openPad() {
    draft = value === null ? '' : String(value);
    error = '';
    padOpen = true;
    await tick();
    dialog?.querySelector<HTMLButtonElement>('.pad-key')?.focus();
  }

  async function closePad() {
    padOpen = false;
    await tick();
    valueButton?.focus();
  }

  function addCharacter(character: string) {
    if (character === '.') {
      if (precision === 0 || draft.includes('.')) return;
      draft = draft ? `${draft}.` : '0.';
    } else {
      const fraction = draft.split('.')[1];
      if (fraction !== undefined && fraction.length >= precision) return;
      draft = draft === '0' && !draft.includes('.') ? character : `${draft}${character}`;
    }
    error = '';
  }

  function backspace() {
    draft = draft.slice(0, -1);
    error = '';
  }

  function clearDraft() {
    draft = '';
    error = '';
  }

  function applyDraft() {
    if (!draft) {
      if (nullable) {
        value = null;
        void closePad();
      } else {
        error = `${label} is required.`;
      }
      return;
    }
    const parsed = Number(draft);
    if (!Number.isFinite(parsed) || parsed < min || parsed > max) {
      error = Number.isFinite(max)
        ? `${label} must be between ${min} and ${max}.`
        : `${label} must be at least ${min}.`;
      return;
    }
    const scale = 10 ** precision;
    if (Math.abs(parsed * scale - Math.round(parsed * scale)) > 1e-8) {
      error = `${label} supports at most ${precision} decimal place${precision === 1 ? '' : 's'}.`;
      return;
    }
    value = Number(parsed.toFixed(precision));
    void closePad();
  }

  function handleDialogKeydown(event: KeyboardEvent) {
    if (!padOpen) return;
    if (/^[0-9]$/.test(event.key)) {
      event.preventDefault();
      addCharacter(event.key);
    } else if (event.key === '.' || event.key === ',') {
      event.preventDefault();
      addCharacter('.');
    } else if (event.key === 'Backspace' || event.key === 'Delete') {
      event.preventDefault();
      backspace();
    } else if (event.key === 'Escape') {
      event.preventDefault();
      void closePad();
    } else if (event.key === 'Enter') {
      event.preventDefault();
      applyDraft();
    } else if (event.key === 'Tab' && dialog) {
      const controls = [...dialog.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')];
      const first = controls[0];
      const last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    }
  }
</script>

<svelte:window onkeydown={handleDialogKeydown} />

<div class="stepper-field">
  <span class="stepper-label">{label}</span>
  <div class="stepper" role="group" aria-label={label}>
    <button type="button" aria-label={`Decrease ${label}`} onclick={() => adjust(-1)}>−</button>
    {#if $deviceModeStore === 'kiosk'}
      <button
        class="kiosk-value"
        type="button"
        aria-label={`Set ${label}; current value ${value ?? 'not recorded'}`}
        bind:this={valueButton}
        onclick={openPad}>{value ?? '—'}</button
      >
    {:else}
      <input
        aria-label={label}
        type="number"
        bind:value
        {min}
        {max}
        {step}
        {inputmode}
        required={!nullable}
      />
    {/if}
    {#if unit}<b>{unit}</b>{/if}
    <button type="button" aria-label={`Increase ${label}`} onclick={() => adjust(1)}>+</button>
  </div>
</div>

{#if padOpen}
  <div class="number-pad-backdrop" role="presentation">
    <div
      class="number-pad panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby="number-pad-title"
      bind:this={dialog}
    >
      <div>
        <p class="eyebrow">Exact value</p>
        <h2 id="number-pad-title">{label}</h2>
      </div>
      <output aria-live="polite">{draft || (nullable ? 'Not recorded' : '—')} {unit}</output>
      <div class="pad-grid">
        {#each ['7', '8', '9', '4', '5', '6', '1', '2', '3'] as character}
          <button class="pad-key" type="button" onclick={() => addCharacter(character)}
            >{character}</button
          >
        {/each}
        {#if precision > 0}
          <button class="pad-key" type="button" onclick={() => addCharacter('.')}>.</button>
        {:else}
          <button class="pad-key utility" type="button" onclick={clearDraft}
            >{nullable ? 'Unset' : 'Clear'}</button
          >
        {/if}
        <button class="pad-key" type="button" onclick={() => addCharacter('0')}>0</button>
        <button
          class="pad-key utility"
          type="button"
          aria-label="Delete last digit"
          onclick={backspace}>⌫</button
        >
      </div>
      {#if precision > 0}
        <button class="clear-button secondary" type="button" onclick={clearDraft}
          >{nullable ? 'Unset value' : 'Clear value'}</button
        >
      {/if}
      {#if error}<p class="error" role="alert">{error}</p>{/if}
      <div class="actions">
        <button class="primary" type="button" onclick={applyDraft}>Apply</button>
        <button class="secondary" type="button" onclick={closePad}>Cancel</button>
      </div>
    </div>
  </div>
{/if}

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
  .kiosk-value {
    min-width: 0;
    padding: 10px 4px;
    background: transparent;
    font-size: 1.25rem;
  }
  input::-webkit-inner-spin-button {
    appearance: none;
  }
  b {
    color: var(--muted);
    font-size: 0.82rem;
  }
  .number-pad-backdrop {
    position: fixed;
    z-index: 80;
    inset: 0;
    display: grid;
    place-items: center;
    overflow-y: auto;
    padding: 16px;
    background: rgb(20 15 13 / 64%);
  }
  .number-pad {
    display: grid;
    gap: 14px;
    width: min(390px, 100%);
    max-height: calc(100dvh - 32px);
    overflow-y: auto;
    background: var(--surface);
  }
  .number-pad h2,
  .number-pad p {
    margin-bottom: 0;
  }
  .number-pad output {
    min-height: 58px;
    padding: 12px;
    border: 1px solid var(--line);
    border-radius: 14px;
    font-size: 1.65rem;
    font-weight: 850;
    text-align: center;
  }
  .pad-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
  }
  .pad-grid button {
    min-height: 54px;
    border: 1px solid var(--line);
    border-radius: 13px;
    background: var(--surface);
    font-size: 1.15rem;
  }
  .pad-grid button.utility {
    font-size: 0.78rem;
  }
  .clear-button {
    justify-self: stretch;
  }
  @media (max-height: 650px) {
    .number-pad {
      grid-template-columns: 0.8fr 1.2fr;
      width: min(620px, 100%);
    }
    .number-pad > div:first-child,
    .number-pad output,
    .number-pad .clear-button,
    .number-pad .error,
    .number-pad .actions {
      grid-column: 1;
    }
    .number-pad .pad-grid {
      grid-column: 2;
      grid-row: 1 / span 5;
    }
  }
</style>
