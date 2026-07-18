<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { api, ensureSession, jsonBody } from '$lib/api';
  import type { BrewFilter, Dripper, Grinder } from '$lib/types';

  let grinders: Grinder[] = $state([]);
  let drippers: Dripper[] = $state([]);
  let filters: BrewFilter[] = $state([]);
  let message = $state('');
  let error = $state('');
  let adding: 'grinder' | 'dripper' | 'filter' | null = $state(null);
  let grinderForm = $state({
    manufacturer: '',
    model: '',
    setting_unit: 'clicks',
    setting_step: 1,
    soft_min: 0,
    soft_max: 50,
    guidance: ''
  });
  let dripperForm = $state({ manufacturer: '', model: '', notes: '' });
  let filterForm = $state({ name: '', notes: '' });

  function isClickUnit(unit: string) {
    return ['click', 'clicks'].includes(unit.trim().toLowerCase());
  }

  onMount(async () => {
    if (!(await ensureSession())) {
      await goto('/login?next=/equipment');
      return;
    }
    await load();
  });
  async function load() {
    [grinders, drippers, filters] = await Promise.all([
      api<Grinder[]>('/grinders'),
      api<Dripper[]>('/drippers'),
      api<BrewFilter[]>('/filters')
    ]);
  }
  async function run(action: () => Promise<unknown>, success: string) {
    error = '';
    message = '';
    try {
      await action();
      message = success;
      adding = null;
      await load();
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not save equipment.';
    }
  }
  async function addGrinder(event: SubmitEvent) {
    event.preventDefault();
    await run(
      () =>
        api('/grinders', {
          method: 'POST',
          body: jsonBody({ ...grinderForm, guidance: grinderForm.guidance || null })
        }),
      'Grinder added.'
    );
  }
  async function addDripper(event: SubmitEvent) {
    event.preventDefault();
    await run(
      () =>
        api('/drippers', {
          method: 'POST',
          body: jsonBody({
            ...dripperForm,
            manufacturer: dripperForm.manufacturer || null,
            notes: dripperForm.notes || null
          })
        }),
      'Dripper added.'
    );
  }
  async function addFilter(event: SubmitEvent) {
    event.preventDefault();
    await run(
      () =>
        api('/filters', {
          method: 'POST',
          body: jsonBody({ ...filterForm, notes: filterForm.notes || null })
        }),
      'Filter added.'
    );
  }
  async function saveGrinder(item: Grinder) {
    await run(
      () =>
        api(`/grinders/${item.id}`, {
          method: 'PUT',
          body: jsonBody({
            manufacturer: item.manufacturer,
            model: item.model,
            setting_unit: item.setting_unit,
            setting_step: item.setting_step,
            soft_min: item.soft_min,
            soft_max: item.soft_max,
            guidance: item.guidance
          })
        }),
      'Grinder updated.'
    );
  }
  async function saveDripper(item: Dripper) {
    await run(
      () =>
        api(`/drippers/${item.id}`, {
          method: 'PUT',
          body: jsonBody({ manufacturer: item.manufacturer, model: item.model, notes: item.notes })
        }),
      'Dripper updated.'
    );
  }
  async function saveFilter(item: BrewFilter) {
    await run(
      () =>
        api(`/filters/${item.id}`, {
          method: 'PUT',
          body: jsonBody({ name: item.name, notes: item.notes })
        }),
      'Filter updated.'
    );
  }
</script>

<svelte:head><title>Equipment · Filter Coffee Club</title></svelte:head>
<div class="heading">
  <div>
    <p class="eyebrow">Shared equipment</p>
    <h1>Keep the rack current.</h1>
    <p class="lede">
      Members can register and correct grinders, drippers, and filters. Administrators can archive
      retired equipment.
    </p>
  </div>
  <div class="actions">
    <button class="primary" onclick={() => (adding = 'grinder')}>+ Grinder</button><button
      class="secondary"
      onclick={() => (adding = 'dripper')}>+ Dripper</button
    ><button class="secondary" onclick={() => (adding = 'filter')}>+ Filter</button>
  </div>
</div>
{#if message}<p class="success" role="status">{message}</p>{/if}{#if error}<p
    class="error"
    role="alert"
  >
    {error}
  </p>{/if}

{#if adding}
  <section class="panel section">
    {#if adding === 'grinder'}<form onsubmit={addGrinder}>
        <h2>Add a grinder</h2>
        <div class="field-grid">
          <label>Manufacturer<input bind:value={grinderForm.manufacturer} required /></label><label
            >Model<input bind:value={grinderForm.model} required /></label
          ><label>Setting unit<input bind:value={grinderForm.setting_unit} required /></label><label
            >Step<input
              type="number"
              bind:value={grinderForm.setting_step}
              min={isClickUnit(grinderForm.setting_unit) ? 1 : 0.01}
              step={isClickUnit(grinderForm.setting_unit) ? 1 : 0.01}
              inputmode={isClickUnit(grinderForm.setting_unit) ? 'numeric' : 'decimal'}
            /></label
          ><label
            >Soft minimum<input
              type="number"
              bind:value={grinderForm.soft_min}
              step={isClickUnit(grinderForm.setting_unit) ? 1 : 0.01}
              inputmode={isClickUnit(grinderForm.setting_unit) ? 'numeric' : 'decimal'}
            /></label
          ><label
            >Soft maximum<input
              type="number"
              bind:value={grinderForm.soft_max}
              step={isClickUnit(grinderForm.setting_unit) ? 1 : 0.01}
              inputmode={isClickUnit(grinderForm.setting_unit) ? 'numeric' : 'decimal'}
            /></label
          >
        </div>
        <label>Guidance<textarea bind:value={grinderForm.guidance}></textarea></label>
        <div class="actions">
          <button class="primary">Save grinder</button><button
            class="secondary"
            type="button"
            onclick={() => (adding = null)}>Cancel</button
          >
        </div>
      </form>
    {:else if adding === 'dripper'}<form onsubmit={addDripper}>
        <h2>Add a dripper</h2>
        <div class="field-grid">
          <label>Manufacturer<input bind:value={dripperForm.manufacturer} /></label><label
            >Model<input bind:value={dripperForm.model} required /></label
          >
        </div>
        <label>Notes<textarea bind:value={dripperForm.notes}></textarea></label>
        <div class="actions">
          <button class="primary">Save dripper</button><button
            class="secondary"
            type="button"
            onclick={() => (adding = null)}>Cancel</button
          >
        </div>
      </form>
    {:else}<form onsubmit={addFilter}>
        <h2>Add a filter</h2>
        <label>Name<input bind:value={filterForm.name} required /></label><label
          >Notes<textarea bind:value={filterForm.notes}></textarea></label
        >
        <div class="actions">
          <button class="primary">Save filter</button><button
            class="secondary"
            type="button"
            onclick={() => (adding = null)}>Cancel</button
          >
        </div>
      </form>{/if}
  </section>
{/if}

<div class="equipment-grid section">
  <section class="panel">
    <h2>Grinders</h2>
    <div class="items">
      {#each grinders as item}<article>
          <div class="field-grid">
            <label>Manufacturer<input bind:value={item.manufacturer} /></label><label
              >Model<input bind:value={item.model} /></label
            ><label>Unit<input bind:value={item.setting_unit} /></label><label
              >Step<input
                type="number"
                bind:value={item.setting_step}
                min={isClickUnit(item.setting_unit) ? 1 : 0.01}
                step={isClickUnit(item.setting_unit) ? 1 : 0.01}
                inputmode={isClickUnit(item.setting_unit) ? 'numeric' : 'decimal'}
              /></label
            ><label
              >Soft min<input
                type="number"
                bind:value={item.soft_min}
                step={isClickUnit(item.setting_unit) ? 1 : 0.01}
                inputmode={isClickUnit(item.setting_unit) ? 'numeric' : 'decimal'}
              /></label
            ><label
              >Soft max<input
                type="number"
                bind:value={item.soft_max}
                step={isClickUnit(item.setting_unit) ? 1 : 0.01}
                inputmode={isClickUnit(item.setting_unit) ? 'numeric' : 'decimal'}
              /></label
            >
          </div>
          <label>Guidance<textarea bind:value={item.guidance}></textarea></label><button
            class="secondary"
            onclick={() => saveGrinder(item)}>Save grinder</button
          >
        </article>{/each}
    </div>
  </section>
  <section class="panel">
    <h2>Drippers</h2>
    <div class="items">
      {#each drippers as item}<article>
          <label>Manufacturer<input bind:value={item.manufacturer} /></label><label
            >Model<input bind:value={item.model} /></label
          ><label>Notes<textarea bind:value={item.notes}></textarea></label><button
            class="secondary"
            onclick={() => saveDripper(item)}>Save dripper</button
          >
        </article>{:else}<p class="muted">No drippers registered.</p>{/each}
    </div>
  </section>
  <section class="panel">
    <h2>Filters</h2>
    <div class="items">
      {#each filters as item}<article>
          <label>Name<input bind:value={item.name} /></label><label
            >Notes<textarea bind:value={item.notes}></textarea></label
          ><button class="secondary" onclick={() => saveFilter(item)}>Save filter</button>
        </article>{:else}<p class="muted">No filters registered.</p>{/each}
    </div>
  </section>
</div>

<style>
  .heading {
    display: flex;
    justify-content: space-between;
    align-items: end;
    gap: 24px;
  }
  .equipment-grid {
    display: grid;
    grid-template-columns: 1.35fr 1fr 1fr;
    gap: 16px;
    align-items: start;
  }
  .items {
    display: grid;
    gap: 14px;
  }
  .items article {
    display: grid;
    gap: 10px;
    padding-top: 14px;
    border-top: 1px solid var(--line);
  }
  .items article:first-child {
    padding-top: 0;
    border-top: 0;
  }
  .items textarea {
    min-height: 80px;
  }
  @media (max-width: 950px) {
    .equipment-grid {
      grid-template-columns: 1fr 1fr;
    }
    .equipment-grid section:first-child {
      grid-column: span 2;
    }
  }
  @media (max-width: 650px) {
    .heading {
      display: grid;
      align-items: start;
    }
    .equipment-grid {
      grid-template-columns: 1fr;
    }
    .equipment-grid section:first-child {
      grid-column: auto;
    }
  }
</style>
