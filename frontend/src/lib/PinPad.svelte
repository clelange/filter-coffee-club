<script lang="ts">
  let {
    label = 'PIN',
    value = $bindable(''),
    disabled = false
  }: { label?: string; value?: string; disabled?: boolean } = $props();

  const digits = [1, 2, 3, 4, 5, 6, 7, 8, 9];

  function addDigit(digit: number | string) {
    if (disabled || value.length >= 4) return;
    value = `${value}${digit}`;
  }

  function backspace() {
    if (disabled) return;
    value = value.slice(0, -1);
  }

  function clear() {
    if (disabled) return;
    value = '';
  }

  function handleKeydown(event: KeyboardEvent) {
    if (disabled) return;
    if (/^[0-9]$/.test(event.key)) {
      event.preventDefault();
      addDigit(event.key);
    } else if (event.key === 'Backspace' || event.key === 'Delete') {
      event.preventDefault();
      backspace();
    }
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="pin-pad" role="group" aria-label={label}>
  <div
    class="pin-display"
    role="status"
    aria-live="polite"
    aria-label={`${value.length} of 4 digits entered`}
  >
    {#each Array(4) as _, index}<span class:filled={index < value.length}></span>{/each}
  </div>
  <div class="digit-grid">
    {#each digits as digit}
      <button type="button" onclick={() => addDigit(digit)} {disabled}>{digit}</button>
    {/each}
    <button class="utility" type="button" onclick={clear} {disabled}>Clear</button>
    <button type="button" onclick={() => addDigit(0)} {disabled}>0</button>
    <button
      class="utility"
      type="button"
      aria-label="Delete last digit"
      onclick={backspace}
      {disabled}>⌫</button
    >
  </div>
</div>

<style>
  .pin-pad {
    display: grid;
    gap: 14px;
    width: min(100%, 330px);
    margin: 0 auto;
  }
  .pin-display {
    display: flex;
    justify-content: center;
    gap: 14px;
    min-height: 50px;
    padding: 15px;
    border: 1px solid var(--line);
    border-radius: 14px;
    background: var(--surface);
  }
  .pin-display span {
    width: 18px;
    height: 18px;
    border: 2px solid color-mix(in srgb, var(--coffee) 45%, var(--cream));
    border-radius: 50%;
  }
  .pin-display span.filled {
    border-color: var(--coffee);
    background: var(--coffee);
  }
  .digit-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 9px;
  }
  button {
    min-height: 58px;
    border: 1px solid var(--line);
    border-radius: 14px;
    background: var(--surface);
    color: var(--ink);
    cursor: pointer;
    font-size: 1.25rem;
    font-weight: 850;
  }
  button:active {
    background: color-mix(in srgb, var(--coffee) 12%, var(--surface));
  }
  button.utility {
    font-size: 0.85rem;
  }
</style>
