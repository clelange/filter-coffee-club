<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { deviceModeStore, loginPath } from '$lib/device';
  import CatalogCard from '$lib/CatalogCard.svelte';
  import DripperFields from '$lib/DripperFields.svelte';
  import FilterFields from '$lib/FilterFields.svelte';
  import GrinderFields from '$lib/GrinderFields.svelte';
  import PhotoPicker from '$lib/PhotoPicker.svelte';
  import { api, appSettingsStore, ensureSession, jsonBody, uploadCatalogPhoto } from '$lib/api';
  import {
    dripperPayload,
    emptyDripperForm,
    emptyFilterForm,
    emptyGrinderForm,
    filterPayload,
    grinderPayload,
    usageFor
  } from '$lib/catalog';
  import type { BrewFilter, CatalogUsageResponse, Dripper, Grinder } from '$lib/types';

  type EquipmentKind = 'grinder' | 'dripper' | 'filter';

  let grinders: Grinder[] = $state([]);
  let drippers: Dripper[] = $state([]);
  let filters: BrewFilter[] = $state([]);
  let usage: CatalogUsageResponse['items'] = $state([]);
  let message = $state('');
  let error = $state('');
  let loading = $state(true);
  let adding: EquipmentKind | null = $state(null);
  let photoFile: File | null = $state(null);
  let grinderForm = $state(emptyGrinderForm());
  let dripperForm = $state(emptyDripperForm());
  let filterForm = $state(emptyFilterForm());

  onMount(async () => {
    if (!(await ensureSession())) {
      await goto(loginPath('/equipment'));
      return;
    }
    await load();
  });

  async function load() {
    loading = true;
    error = '';
    try {
      const [grinderItems, dripperItems, filterItems, usageResponse] = await Promise.all([
        api<Grinder[]>('/grinders'),
        api<Dripper[]>('/drippers'),
        api<BrewFilter[]>('/filters'),
        api<CatalogUsageResponse>('/catalog/usage')
      ]);
      grinders = grinderItems;
      drippers = dripperItems;
      filters = filterItems;
      usage = usageResponse.items;
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not load equipment.';
    } finally {
      loading = false;
    }
  }

  function startAdding(kind: EquipmentKind) {
    adding = adding === kind ? null : kind;
    photoFile = null;
    error = '';
    message = '';
  }

  function closeAdding() {
    adding = null;
    photoFile = null;
  }

  async function createWithPhoto<T extends { id: number }>(
    action: () => Promise<T>,
    endpoint: string,
    success: string
  ): Promise<boolean> {
    error = '';
    message = '';
    try {
      const item = await action();
      if (photoFile) {
        try {
          await uploadCatalogPhoto(`${endpoint}/${item.id}/photo`, photoFile);
        } catch (caught) {
          message = success;
          error = `The item was saved, but the photo failed: ${caught instanceof Error ? caught.message : 'Could not upload photo.'}`;
          adding = null;
          photoFile = null;
          await load();
          return true;
        }
      }
      message = success;
      adding = null;
      photoFile = null;
      await load();
      return true;
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not save equipment.';
      return false;
    }
  }

  async function addGrinder(event: SubmitEvent) {
    event.preventDefault();
    if (
      await createWithPhoto(
        () =>
          api<Grinder>('/grinders', {
            method: 'POST',
            body: jsonBody(grinderPayload(grinderForm))
          }),
        '/grinders',
        'Grinder added.'
      )
    )
      grinderForm = emptyGrinderForm();
  }

  async function addDripper(event: SubmitEvent) {
    event.preventDefault();
    if (
      await createWithPhoto(
        () =>
          api<Dripper>('/drippers', {
            method: 'POST',
            body: jsonBody(dripperPayload(dripperForm))
          }),
        '/drippers',
        'Dripper added.'
      )
    )
      dripperForm = emptyDripperForm();
  }

  async function addFilter(event: SubmitEvent) {
    event.preventDefault();
    if (
      await createWithPhoto(
        () =>
          api<BrewFilter>('/filters', {
            method: 'POST',
            body: jsonBody(filterPayload(filterForm))
          }),
        '/filters',
        'Filter added.'
      )
    )
      filterForm = emptyFilterForm();
  }
</script>

<svelte:head><title>Equipment · Filter Coffee Club</title></svelte:head>

<div class="catalog-page">
  <div class="catalog-heading">
    <div>
      <p class="eyebrow">Shared equipment</p>
      <h1>{$deviceModeStore === 'kiosk' ? 'The club rack.' : 'Keep the rack current.'}</h1>
      <p class="lede">
        {$deviceModeStore === 'kiosk'
          ? 'Equipment is read-only on this shared display.'
          : 'Browse the shared rack. Open an item to see its full brew history or make a correction.'}
      </p>
    </div>
    {#if $deviceModeStore !== 'kiosk'}
      <div class="actions add-actions">
        <button class="primary" onclick={() => startAdding('grinder')}>+ Grinder</button>
        <button class="secondary" onclick={() => startAdding('dripper')}>+ Dripper</button>
        <button class="secondary" onclick={() => startAdding('filter')}>+ Filter</button>
      </div>
    {/if}
  </div>

  {#if page.url.searchParams.get('message')}<p class="success" role="status">
      {page.url.searchParams.get('message')}
    </p>{/if}
  {#if message}<p class="success" role="status">{message}</p>{/if}
  {#if error}<p class="error" role="alert">{error}</p>{/if}

  {#if adding && $deviceModeStore !== 'kiosk'}
    <section class="panel create-panel">
      {#if adding === 'grinder'}
        <form onsubmit={addGrinder}>
          <div class="form-heading">
            <p class="eyebrow">New catalog item</p>
            <h2>Add a grinder.</h2>
          </div>
          <GrinderFields bind:form={grinderForm} />
          {#if !$appSettingsStore?.demo_mode}<PhotoPicker
              bind:file={photoFile}
              label="Photo (optional)"
            />{/if}
          <div class="actions">
            <button class="primary">Save grinder</button><button
              class="secondary"
              type="button"
              onclick={closeAdding}>Cancel</button
            >
          </div>
        </form>
      {:else if adding === 'dripper'}
        <form onsubmit={addDripper}>
          <div class="form-heading">
            <p class="eyebrow">New catalog item</p>
            <h2>Add a dripper.</h2>
          </div>
          <DripperFields bind:form={dripperForm} />
          {#if !$appSettingsStore?.demo_mode}<PhotoPicker
              bind:file={photoFile}
              label="Photo (optional)"
            />{/if}
          <div class="actions">
            <button class="primary">Save dripper</button><button
              class="secondary"
              type="button"
              onclick={closeAdding}>Cancel</button
            >
          </div>
        </form>
      {:else}
        <form onsubmit={addFilter}>
          <div class="form-heading">
            <p class="eyebrow">New catalog item</p>
            <h2>Add a filter.</h2>
          </div>
          <FilterFields bind:form={filterForm} />
          {#if !$appSettingsStore?.demo_mode}<PhotoPicker
              bind:file={photoFile}
              label="Photo (optional)"
            />{/if}
          <div class="actions">
            <button class="primary">Save filter</button><button
              class="secondary"
              type="button"
              onclick={closeAdding}>Cancel</button
            >
          </div>
        </form>
      {/if}
    </section>
  {/if}

  {#if loading}
    <div class="empty" role="status">Loading the equipment rack…</div>
  {:else}
    <div class="equipment-sections">
      <section class="equipment-section" aria-labelledby="grinder-heading">
        <div class="section-heading">
          <p class="eyebrow">Preparation</p>
          <h2 id="grinder-heading">Grinders</h2>
        </div>
        {#if grinders.length === 0}<div class="empty">No grinders registered.</div>{:else}
          <div class="summary-grid">
            {#each grinders as item}
              <CatalogCard
                href={`/equipment/grinders/${item.id}`}
                photoPath={item.photo_path}
                photoEndpoint={`/grinders/${item.id}/photo`}
                alt={`${item.manufacturer} ${item.model}`}
                eyebrow={item.manufacturer}
                title={item.model}
                metadata={`${item.setting_unit} · step ${item.setting_step} · usual range ${item.soft_min ?? '—'}–${item.soft_max ?? '—'}`}
                notes={item.guidance}
                usage={usageFor(usage, 'grinder', item.id)}
              />
            {/each}
          </div>
        {/if}
      </section>
      <section class="equipment-section" aria-labelledby="dripper-heading">
        <div class="section-heading">
          <p class="eyebrow">Brewing</p>
          <h2 id="dripper-heading">Drippers</h2>
        </div>
        {#if drippers.length === 0}<div class="empty">No drippers registered.</div>{:else}
          <div class="summary-grid">
            {#each drippers as item}
              <CatalogCard
                href={`/equipment/drippers/${item.id}`}
                photoPath={item.photo_path}
                photoEndpoint={`/drippers/${item.id}/photo`}
                alt={`${item.manufacturer ?? ''} ${item.model}`.trim()}
                eyebrow={item.manufacturer ?? 'Dripper'}
                title={item.model}
                metadata={item.notes ?? 'No notes recorded'}
                usage={usageFor(usage, 'dripper', item.id)}
              />
            {/each}
          </div>
        {/if}
      </section>
      <section class="equipment-section" aria-labelledby="filter-heading">
        <div class="section-heading">
          <p class="eyebrow">Brewing</p>
          <h2 id="filter-heading">Filters</h2>
        </div>
        {#if filters.length === 0}<div class="empty">No filters registered.</div>{:else}
          <div class="summary-grid">
            {#each filters as item}
              <CatalogCard
                href={`/equipment/filters/${item.id}`}
                photoPath={item.photo_path}
                photoEndpoint={`/filters/${item.id}/photo`}
                alt={item.name}
                eyebrow="Filter"
                title={item.name}
                metadata={item.notes ?? 'No notes recorded'}
                usage={usageFor(usage, 'filter', item.id)}
              />
            {/each}
          </div>
        {/if}
      </section>
    </div>
  {/if}
</div>

<style>
  .catalog-page {
    --catalog-gap-xs: 4px;
    --catalog-gap-sm: 8px;
    --catalog-gap-md: 16px;
    --catalog-gap-lg: 28px;
    --catalog-card-padding: clamp(16px, 2.5vw, 22px);
    display: grid;
    gap: var(--catalog-gap-lg);
  }
  .catalog-page :global(h1),
  .catalog-page :global(h2),
  .catalog-page :global(p) {
    margin: 0;
  }
  .catalog-heading {
    display: flex;
    justify-content: space-between;
    align-items: end;
    gap: 24px;
  }
  .catalog-heading > div:first-child,
  .form-heading,
  .section-heading {
    display: grid;
    gap: var(--catalog-gap-sm);
  }
  .catalog-heading h1 {
    margin: 0;
  }
  .add-actions {
    flex: 0 0 auto;
  }
  .create-panel,
  .create-panel form {
    display: grid;
    gap: 18px;
  }
  .form-heading h2,
  .section-heading h2 {
    font-size: clamp(1.7rem, 4vw, 2.5rem);
  }
  .equipment-sections,
  .equipment-section {
    display: grid;
    min-width: 0;
  }
  .equipment-sections {
    gap: clamp(38px, 7vw, 68px);
  }
  .equipment-section {
    gap: var(--catalog-gap-md);
  }
  .summary-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 255px), 1fr));
    gap: var(--catalog-gap-md);
    align-items: stretch;
  }
  @media (min-width: 900px) and (max-height: 650px) {
    .catalog-page {
      gap: 20px;
    }
    .catalog-heading h1 {
      font-size: clamp(3rem, 5vw, 3.5rem);
    }
    .summary-grid {
      grid-template-columns: repeat(auto-fit, minmax(min(100%, 360px), 1fr));
    }
    :global(.equipment-section .catalog-summary) {
      grid-template-columns: minmax(145px, 0.45fr) minmax(0, 1fr);
      align-items: start;
    }
  }
  @media (max-width: 680px) {
    .catalog-heading {
      display: grid;
      align-items: start;
    }
  }
</style>
