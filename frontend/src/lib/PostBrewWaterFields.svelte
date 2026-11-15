<script module lang="ts">
  const MAX_ADDED_WATER_G = 5000;

  export function invalidAddedWater(amount: number | null): boolean {
    return (
      amount !== null && (!Number.isInteger(amount) || amount < 1 || amount > MAX_ADDED_WATER_G)
    );
  }
</script>

<script lang="ts">
  import NumberStepper from './NumberStepper.svelte';

  let {
    added = $bindable(),
    amount = $bindable()
  }: { added: boolean | null; amount: number | null } = $props();

  function toggleAdded(event: Event) {
    added = (event.currentTarget as HTMLInputElement).checked;
    if (!added) amount = null;
  }
</script>

<div class="post-brew-water">
  <label>
    <input type="checkbox" checked={added === true} onchange={toggleAdded} />
    Water added after brewing
  </label>
  {#if added}
    <NumberStepper
      label="Added water"
      bind:value={amount}
      min={1}
      max={MAX_ADDED_WATER_G}
      unit="g"
      inputmode="numeric"
      nullable
    />
    <p class="hint">Leave blank if you didn’t weigh it.</p>
    {#if invalidAddedWater(amount)}
      <p class="error" role="alert">Enter a whole number from 1 to {MAX_ADDED_WATER_G} g.</p>
    {/if}
  {/if}
</div>

<style>
  .post-brew-water {
    display: grid;
    align-items: start;
    gap: 0.5rem;
  }

  label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    min-height: 44px;
  }

  input {
    width: 1.25rem;
    height: 1.25rem;
    min-height: 0;
    margin: 0;
    padding: 0;
  }

  p {
    margin: 0;
  }
</style>
