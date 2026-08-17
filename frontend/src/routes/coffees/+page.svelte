<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { deviceModeStore } from '$lib/device';
  import CatalogCard from '$lib/CatalogCard.svelte';
  import CoffeeFields from '$lib/CoffeeFields.svelte';
  import PhotoPicker from '$lib/PhotoPicker.svelte';
  import {
    ApiError,
    api,
    appSettingsStore,
    jsonBody,
    sessionStore,
    uploadCatalogPhoto
  } from '$lib/api';
  import { coffeePayload, emptyCoffeeForm, usageFor } from '$lib/catalog';
  import type { CatalogUsageResponse, Coffee, PhotoFraming } from '$lib/types';

  let coffees: Coffee[] = $state([]);
  let finishedCoffees: Coffee[] = $state([]);
  let coffeeColorPeers: Coffee[] = $state([]);
  let usage: CatalogUsageResponse['items'] = $state([]);
  let showForm = $state(false);
  let creating = $state(false);
  let creationKey = $state('');
  let loading = $state(true);
  let error = $state('');
  let photoFile: File | null = $state(null);
  let photoFraming: PhotoFraming | null = $state(null);
  let form = $state(emptyCoffeeForm());

  onMount(load);

  async function load() {
    loading = true;
    error = '';
    try {
      const [coffeeItems, usageResponse] = await Promise.all([
        api<Coffee[]>('/coffees?include_finished=true'),
        api<CatalogUsageResponse>('/catalog/usage')
      ]);
      coffees = coffeeItems.filter((coffee) => coffee.available);
      finishedCoffees = coffeeItems.filter((coffee) => !coffee.available);
      coffeeColorPeers = coffeeItems;
      usage = usageResponse.items;
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not load the coffee catalog.';
    } finally {
      loading = false;
    }
  }

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    if (creating) return;
    creating = true;
    error = '';
    const idempotencyKey = creationKey || crypto.randomUUID();
    creationKey = idempotencyKey;
    try {
      const coffee = await api<Coffee>('/coffees', {
        method: 'POST',
        headers: { 'Idempotency-Key': idempotencyKey },
        body: jsonBody(coffeePayload(form))
      });
      if (photoFile) {
        try {
          await uploadCatalogPhoto<Coffee>(`/coffees/${coffee.id}/photo`, photoFile, photoFraming);
        } catch (caught) {
          await goto(`/coffees/${coffee.id}?edit=1&photoError=1`);
          return;
        }
      }
      form = emptyCoffeeForm();
      photoFile = null;
      photoFraming = null;
      showForm = false;
      creationKey = '';
      await load();
    } catch (caught) {
      if (caught instanceof ApiError && caught.status < 500) creationKey = crypto.randomUUID();
      error = caught instanceof Error ? caught.message : 'Could not add coffee.';
    } finally {
      creating = false;
    }
  }

  function closeForm() {
    if (creating) return;
    showForm = false;
    creationKey = '';
    photoFile = null;
    photoFraming = null;
    form = emptyCoffeeForm();
  }

  function openForm() {
    creationKey = crypto.randomUUID();
    showForm = true;
  }
</script>

<svelte:head><title>Coffees · Filter Coffee Club</title></svelte:head>

<div class="catalog-page">
  <div class="catalog-heading">
    <div>
      <p class="eyebrow">Bean catalog</p>
      <h1>Coffees in orbit.</h1>
      <p class="lede">
        Each entry represents a particular bag or lot, so roast and opening dates remain meaningful.
      </p>
    </div>
    {#if $sessionStore && $deviceModeStore !== 'kiosk'}
      <button
        class="primary"
        disabled={creating}
        onclick={() => (showForm ? closeForm() : openForm())}
        >{showForm ? 'Close' : '+ Add coffee'}</button
      >
    {/if}
  </div>

  {#if page.url.searchParams.get('message')}
    <p class="success" role="status">{page.url.searchParams.get('message')}</p>
  {/if}

  {#if showForm}
    <form class="panel create-panel" onsubmit={submit}>
      <div class="form-heading">
        <p class="eyebrow">New catalog item</p>
        <h2>Register a bag.</h2>
      </div>
      <CoffeeFields
        bind:form
        coffees={coffeeColorPeers}
        surfaceColor={$appSettingsStore?.color_surface ?? '#FFFDFC'}
      />
      {#if !$appSettingsStore?.demo_mode}<PhotoPicker
          bind:file={photoFile}
          bind:framing={photoFraming}
          label="Photo (optional)"
        />{/if}
      {#if error}<p class="error" role="alert">{error}</p>{/if}
      <div class="actions">
        <button class="primary" disabled={creating}
          >{creating ? 'Saving coffee…' : 'Save coffee'}</button
        >
        <button class="secondary" type="button" disabled={creating} onclick={closeForm}
          >Cancel</button
        >
      </div>
    </form>
  {:else if error}
    <p class="error" role="alert">{error}</p>
  {/if}

  <section class="catalog-section" aria-label="Coffee bags">
    {#if loading}
      <div class="empty" role="status">Loading coffee catalog…</div>
    {:else if coffees.length === 0}
      <div class="empty">
        {finishedCoffees.length
          ? 'No coffee bags are currently available.'
          : 'No coffee bags registered yet.'}
      </div>
    {:else}
      <div class="summary-grid">
        {#each coffees as coffee}
          <CatalogCard
            href={`/coffees/${coffee.id}`}
            photoPath={coffee.photo_path}
            photoFraming={coffee.photo_framing}
            photoEndpoint={`/coffees/${coffee.id}/photo`}
            alt={`${coffee.roaster} ${coffee.name}`}
            eyebrow={coffee.roaster}
            title={coffee.name}
            metadata={[
              coffee.country,
              coffee.region,
              coffee.process,
              coffee.roast_level,
              coffee.purchase_location ? `Purchased from ${coffee.purchase_location}` : null
            ]
              .filter(Boolean)
              .join(' · ')}
            notes={coffee.package_notes}
            usage={usageFor(usage, 'coffee', coffee.id)}
            beanFallback
            primaryHref={`/brews/new?coffee=${coffee.id}`}
            primaryLabel="Brew this"
          />
        {/each}
      </div>
    {/if}
  </section>

  {#if !loading && finishedCoffees.length > 0}
    <details class="finished-section">
      <summary>
        <span>Finished bags</span>
        <small>{finishedCoffees.length} {finishedCoffees.length === 1 ? 'bag' : 'bags'}</small>
      </summary>
      <p class="muted">These bags remain available for brew history and can be restored.</p>
      <div class="summary-grid">
        {#each finishedCoffees as coffee}
          <CatalogCard
            href={`/coffees/${coffee.id}`}
            photoPath={coffee.photo_path}
            photoFraming={coffee.photo_framing}
            photoEndpoint={`/coffees/${coffee.id}/photo`}
            alt={`${coffee.roaster} ${coffee.name}`}
            eyebrow={coffee.roaster}
            title={coffee.name}
            metadata={[coffee.country, coffee.region, coffee.process, coffee.roast_level]
              .filter(Boolean)
              .join(' · ')}
            notes={coffee.package_notes}
            usage={usageFor(usage, 'coffee', coffee.id)}
            beanFallback
            statusLabel="Finished"
          />
        {/each}
      </div>
    </details>
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
  .catalog-heading > div,
  .form-heading {
    display: grid;
    gap: var(--catalog-gap-sm);
  }
  .catalog-heading h1 {
    margin: 0;
  }
  .create-panel {
    display: grid;
    gap: 18px;
  }
  .create-panel h2 {
    font-size: clamp(1.7rem, 4vw, 2.5rem);
  }
  .catalog-section {
    min-width: 0;
  }
  .summary-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 255px), 1fr));
    gap: var(--catalog-gap-md);
    align-items: stretch;
  }
  .finished-section > summary {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
  }
  .finished-section > summary small {
    color: var(--muted);
  }
  @media (min-width: 900px) and (max-height: 650px) {
    .catalog-page {
      gap: 20px;
    }
  }
  @media (max-width: 600px) {
    .catalog-heading {
      display: grid;
      align-items: start;
    }
  }
</style>
