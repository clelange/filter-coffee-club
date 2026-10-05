<script lang="ts">
  import { selectedOption } from '$lib/selected-option';
  import type { GrinderScale } from '$lib/analytics-grind';

  export let scales: GrinderScale[];
  export let grinders: { id: number; name: string }[];
  export let scaleKey: string;
  export let sourceFilter: string;

  $: originalGrinderId = scales.find((scale) => scale.key === scaleKey)?.grinderId;
  $: availableGrinders =
    originalGrinderId == null
      ? grinders
      : grinders.filter((grinder) => grinder.id === originalGrinderId);
  $: if (
    sourceFilter !== 'all' &&
    !availableGrinders.some((grinder) => String(grinder.id) === sourceFilter)
  ) {
    sourceFilter = 'all';
  }
</script>

<label>
  Show settings in
  <select use:selectedOption={scaleKey} bind:value={scaleKey}>
    {#each scales as scale (scale.key)}<option value={scale.key}>{scale.label}</option>{/each}
  </select>
</label>
<label>
  Brewed with
  <select use:selectedOption={sourceFilter} bind:value={sourceFilter}>
    <option value="all">All grinders</option>
    {#each availableGrinders as grinder (grinder.id)}
      <option value={String(grinder.id)}>{grinder.name}</option>
    {/each}
  </select>
</label>

<style>
  label {
    width: 100%;
    min-width: 0;
    flex: 1 1 180px;
  }
</style>
