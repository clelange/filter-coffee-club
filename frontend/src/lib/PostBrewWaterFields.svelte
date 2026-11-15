<script lang="ts">
  import NumberStepper from './NumberStepper.svelte';

  let {
    added = $bindable(),
    amount = $bindable(),
    invalid = $bindable()
  }: { added: boolean | null; amount: number | null; invalid: boolean } = $props();

  function toggleAdded(event: Event) {
    added = (event.currentTarget as HTMLInputElement).checked;
    if (!added) {
      amount = null;
      invalid = false;
    }
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
      onvaliditychange={(valid) => (invalid = !valid)}
      min={1}
      max={5000}
      unit="g"
      inputmode="numeric"
      nullable
    />
    <p class="hint">Leave blank if you didn’t weigh it.</p>
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
