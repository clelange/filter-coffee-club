<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { deviceModeStore } from '$lib/device';
  import CatalogCard from '$lib/CatalogCard.svelte';
  import CoffeeFields from '$lib/CoffeeFields.svelte';
  import PhotoPicker from '$lib/PhotoPicker.svelte';
  import { api, appSettingsStore, jsonBody, sessionStore, uploadCatalogPhoto } from '$lib/api';
  import { coffeePayload, emptyCoffeeForm, usageFor } from '$lib/catalog';
  import type { CatalogUsageResponse, Coffee } from '$lib/types';

  let coffees: Coffee[] = $state([]);
  let usage: CatalogUsageResponse['items'] = $state([]);
  let showForm = $state(false);
  let loading = $state(true);
  let error = $state('');
  let photoFile: File | null = $state(null);
  let form = $state(emptyCoffeeForm());

  onMount(load);

  async function load() {
    loading = true;
    error = '';
    try {
      const [coffeeItems, usageResponse] = await Promise.all([
        api<Coffee[]>('/coffees'),
        api<CatalogUsageResponse>('/catalog/usage')
      ]);
      coffees = coffeeItems;
      usage = usageResponse.items;
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not load the coffee catalog.';
    } finally {
      loading = false;
    }
  }

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    error = '';
    try {
      const coffee = await api<Coffee>('/coffees', {
        method: 'POST',
        body: jsonBody(coffeePayload(form))
      });
      if (photoFile) {
        try {
          await uploadCatalogPhoto<Coffee>(`/coffees/${coffee.id}/photo`, photoFile);
        } catch (caught) {
          await goto(`/coffees/${coffee.id}?edit=1&photoError=1`);
          return;
        }
      }
      form = emptyCoffeeForm();
      photoFile = null;
      showForm = false;
      await load();
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not add coffee.';
    }
  }

  function closeForm() {
    showForm = false;
    photoFile = null;
    form = emptyCoffeeForm();
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
      <button class="primary" onclick={() => (showForm ? closeForm() : (showForm = true))}
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
      <CoffeeFields bind:form />
      {#if !$appSettingsStore?.demo_mode}<PhotoPicker
          bind:file={photoFile}
          label="Photo (optional)"
        />{/if}
      {#if error}<p class="error" role="alert">{error}</p>{/if}
      <div class="actions">
        <button class="primary">Save coffee</button>
        <button class="secondary" type="button" onclick={closeForm}>Cancel</button>
      </div>
    </form>
  {:else if error}
    <p class="error" role="alert">{error}</p>
  {/if}

  <section class="catalog-section" aria-label="Coffee bags">
    {#if loading}
      <div class="empty" role="status">Loading coffee catalog…</div>
    {:else if coffees.length === 0}
      <div class="empty">No coffee bags registered yet.</div>
    {:else}
      <div class="summary-grid">
        {#each coffees as coffee}
          <CatalogCard
            href={`/coffees/${coffee.id}`}
            photoPath={coffee.photo_path}
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
            primaryHref={`/brews/new?coffee=${coffee.id}`}
            primaryLabel="Brew this"
          />
        {/each}
      </div>
    {/if}
  </section>
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
