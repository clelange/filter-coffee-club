<script lang="ts">
  import CoffeeColorPicker from '$lib/CoffeeColorPicker.svelte';
  import type { Coffee, CoffeeFormData } from '$lib/types';

  export let form: CoffeeFormData;
  export let coffees: Coffee[] = [];
  export let currentCoffeeId: number | null = null;
  export let surfaceColor = '#FFFDFC';
</script>

<div class="field-grid">
  <label>Roaster / brand<input bind:value={form.roaster} required /></label>
  <label>Coffee name<input bind:value={form.name} required /></label>
  <label>Country<input bind:value={form.country} /></label>
  <label>Region<input bind:value={form.region} /></label>
  <label>Producer / farm<input bind:value={form.producer} /></label>
  <label
    >Purchased from<input
      bind:value={form.purchase_location}
      maxlength="160"
      placeholder="Shop, city, or country"
    /></label
  >
  <label>Variety<input bind:value={form.variety} /></label>
  <label>Process<input bind:value={form.process} placeholder="Washed, natural, anaerobic…" /></label
  >
  <label>
    Roast level
    <select bind:value={form.roast_level}>
      <option value="">Not recorded</option>
      {#each ['Light', 'Medium-light', 'Medium', 'Medium-dark', 'Dark'] as level}
        <option>{level}</option>
      {/each}
    </select>
  </label>
  <label>Roast date<input type="date" bind:value={form.roast_date} /></label>
  <label>Opened date<input type="date" bind:value={form.opened_date} /></label>
</div>
<label>Package tasting notes<textarea bind:value={form.package_notes}></textarea></label>
<CoffeeColorPicker bind:value={form.chart_color} {coffees} {currentCoffeeId} {surfaceColor} />
