<script lang="ts">
  import { onMount } from 'svelte';
  import { deviceModeStore } from '$lib/device';
  import CatalogPhoto from '$lib/CatalogPhoto.svelte';
  import PhotoPicker from '$lib/PhotoPicker.svelte';
  import { api, appSettingsStore, jsonBody, sessionStore, uploadCatalogPhoto } from '$lib/api';
  import type { Coffee } from '$lib/types';

  let coffees: Coffee[] = $state([]);
  let showForm = $state(false);
  let editId: number | null = $state(null);
  let error = $state('');
  let photoFile: File | null = $state(null);
  let form = $state({
    roaster: '',
    name: '',
    country: '',
    region: '',
    producer: '',
    process: '',
    roast_level: '',
    roast_date: '',
    opened_date: '',
    variety: '',
    package_notes: ''
  });

  onMount(load);
  async function load() {
    coffees = await api<Coffee[]>('/coffees');
  }
  async function submit(event: SubmitEvent) {
    event.preventDefault();
    error = '';
    try {
      const coffee = await api<Coffee>(editId ? `/coffees/${editId}` : '/coffees', {
        method: editId ? 'PUT' : 'POST',
        body: jsonBody(
          Object.fromEntries(Object.entries(form).map(([key, value]) => [key, value || null]))
        )
      });
      if (photoFile) {
        try {
          await uploadCatalogPhoto<Coffee>(`/coffees/${coffee.id}/photo`, photoFile);
        } catch (caught) {
          editId = coffee.id;
          showForm = true;
          await load();
          error = `Coffee details were saved, but the photo failed: ${caught instanceof Error ? caught.message : 'Could not upload photo.'}`;
          return;
        }
      }
      form = {
        roaster: '',
        name: '',
        country: '',
        region: '',
        producer: '',
        process: '',
        roast_level: '',
        roast_date: '',
        opened_date: '',
        variety: '',
        package_notes: ''
      };
      editId = null;
      photoFile = null;
      showForm = false;
      await load();
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not add coffee.';
    }
  }
  async function cloneCoffee(id: number) {
    await api(`/coffees/${id}/clone`, { method: 'POST', body: jsonBody({}) });
    await load();
  }
  async function archiveCoffee(id: number) {
    await api(`/coffees/${id}/archive`, { method: 'POST', body: jsonBody({}) });
    await load();
  }
  function editCoffee(coffee: Coffee) {
    editId = coffee.id;
    form = {
      roaster: coffee.roaster,
      name: coffee.name,
      country: coffee.country ?? '',
      region: coffee.region ?? '',
      producer: coffee.producer ?? '',
      process: coffee.process ?? '',
      roast_level: coffee.roast_level ?? '',
      roast_date: coffee.roast_date ?? '',
      opened_date: coffee.opened_date ?? '',
      variety: coffee.variety ?? '',
      package_notes: coffee.package_notes ?? ''
    };
    photoFile = null;
    showForm = true;
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
  function closeForm() {
    showForm = false;
    editId = null;
    photoFile = null;
  }
</script>

<svelte:head><title>Coffees · Filter Coffee Club</title></svelte:head>

<div class="heading">
  <div>
    <p class="eyebrow">Bean catalog</p>
    <h1>Coffees in orbit.</h1>
    <p class="lede">
      Each entry represents a particular bag or lot, so roast and opening dates remain meaningful.
    </p>
  </div>
  {#if $sessionStore && $deviceModeStore !== 'kiosk'}<button
      class="primary"
      onclick={() => (showForm ? closeForm() : (showForm = true))}
      >{showForm ? 'Close' : '+ Add coffee'}</button
    >{/if}
</div>

{#if showForm}
  <form class="panel section" onsubmit={submit}>
    <h2>{editId ? 'Update this bag' : 'Register a bag'}</h2>
    <div class="field-grid">
      <label>Roaster / brand<input bind:value={form.roaster} required /></label><label
        >Coffee name<input bind:value={form.name} required /></label
      >
      <label>Country<input bind:value={form.country} /></label><label
        >Region<input bind:value={form.region} /></label
      >
      <label>Producer / farm<input bind:value={form.producer} /></label><label
        >Variety<input bind:value={form.variety} /></label
      >
      <label
        >Process<input bind:value={form.process} placeholder="Washed, natural, anaerobic…" /></label
      >
      <label
        >Roast level<select bind:value={form.roast_level}
          ><option value="">Not recorded</option
          >{#each ['Light', 'Medium-light', 'Medium', 'Medium-dark', 'Dark'] as level}<option
              >{level}</option
            >{/each}</select
        ></label
      >
      <label>Roast date<input type="date" bind:value={form.roast_date} /></label><label
        >Opened date<input type="date" bind:value={form.opened_date} /></label
      >
    </div>
    <label>Package tasting notes<textarea bind:value={form.package_notes}></textarea></label>
    {#if !$appSettingsStore?.demo_mode}
      <PhotoPicker
        bind:file={photoFile}
        label={editId ? 'Replace photo (optional)' : 'Photo (optional)'}
      />
    {/if}
    {#if error}<p class="error">{error}</p>{/if}<button class="primary"
      >{editId ? 'Save changes' : 'Save coffee'}</button
    >
  </form>
{/if}

<section class="section">
  {#if coffees.length === 0}<div class="empty">No coffee bags registered yet.</div>{:else}<div
      class="card-grid"
    >
      {#each coffees as coffee}
        <article class="card coffee-card">
          <CatalogPhoto
            photoPath={coffee.photo_path}
            alt={`${coffee.roaster} ${coffee.name}`}
            endpoint={`/coffees/${coffee.id}/photo`}
            beanFallback
            editable={Boolean(
              $sessionStore && $deviceModeStore !== 'kiosk' && !$appSettingsStore?.demo_mode
            )}
            onchanged={(photoPath) => {
              coffee.photo_path = photoPath;
            }}
          />
          <p class="eyebrow">{coffee.roaster}</p>
          <h2>{coffee.name}</h2>
          <p class="muted">
            {[coffee.country, coffee.region, coffee.process, coffee.roast_level]
              .filter(Boolean)
              .join(' · ') || 'Details not recorded yet'}
          </p>
          {#if coffee.package_notes}<p class="notes">“{coffee.package_notes}”</p>{/if}
          <div class="actions">
            <a class="button small" href={`/brews/new?coffee=${coffee.id}`}>Brew this</a
            >{#if $sessionStore && $deviceModeStore !== 'kiosk'}<button
                class="secondary"
                onclick={() => editCoffee(coffee)}>Edit</button
              ><button class="secondary" onclick={() => cloneCoffee(coffee.id)}>Clone bag</button
              >{#if $sessionStore.profile.role === 'admin'}<button
                  class="danger"
                  onclick={() => archiveCoffee(coffee.id)}>Archive</button
                >{/if}{/if}
          </div>
        </article>
      {/each}
    </div>{/if}
</section>

<style>
  .heading {
    display: flex;
    justify-content: space-between;
    align-items: end;
    gap: 24px;
  }
  .coffee-card {
    position: relative;
    overflow: hidden;
  }
  .coffee-card h2 {
    margin-bottom: 7px;
  }
  .notes {
    padding: 12px;
    border-left: 3px solid var(--amber);
    background: var(--cream);
    font-style: italic;
  }
  @media (max-width: 600px) {
    .heading {
      display: grid;
      align-items: start;
    }
  }
</style>
