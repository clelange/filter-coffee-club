<script lang="ts">
  import { onMount } from 'svelte';
  import { beforeNavigate, goto } from '$app/navigation';
  import { page } from '$app/stores';
  import CatalogPhoto from '$lib/CatalogPhoto.svelte';
  import CoffeeTastingAnalysis from '$lib/CoffeeTastingAnalysis.svelte';
  import CoffeeFields from '$lib/CoffeeFields.svelte';
  import ConfirmDialog from '$lib/ConfirmDialog.svelte';
  import PhotoPicker from '$lib/PhotoPicker.svelte';
  import RecentBrews from '$lib/RecentBrews.svelte';
  import {
    ApiError,
    api,
    appSettingsStore,
    ensureSession,
    jsonBody,
    sessionStore,
    uploadCatalogPhoto
  } from '$lib/api';
  import { coffeePayload, coffeeToForm, emptyCoffeeForm, formatCatalogDate } from '$lib/catalog';
  import { deviceModeStore, loginPath } from '$lib/device';
  import type { CatalogInsights, Coffee, CoffeeRatingInsights } from '$lib/types';

  let coffee: Coffee | null = $state(null);
  let insights: CatalogInsights | null = $state(null);
  let ratingInsights: CoffeeRatingInsights | null = $state(null);
  let form = $state(emptyCoffeeForm());
  let baseline = $state('');
  let editMode = $state(false);
  let loading = $state(true);
  let notFound = $state(false);
  let error = $state('');
  let insightsError = $state('');
  let ratingInsightsError = $state('');
  let loadMoreError = $state('');
  let success = $state('');
  let photoError = $state('');
  let photoFile: File | null = $state(null);
  let removePhotoDraft = $state(false);
  let saving = $state(false);
  let cloning = $state(false);
  let archiveOpen = $state(false);
  let archiving = $state(false);
  let loadingMore = $state(false);

  const id = $derived(Number($page.params.id));
  const dirty = $derived(
    editMode && (JSON.stringify(form) !== baseline || photoFile !== null || removePhotoDraft)
  );
  function canManage(): boolean {
    return Boolean($sessionStore && $deviceModeStore !== 'kiosk' && coffee && !coffee.archived);
  }

  beforeNavigate(({ cancel }) => {
    if (dirty && !confirm('Discard your unsaved coffee changes?')) cancel();
  });

  onMount(async () => {
    await ensureSession();
    await load();
    if (coffee && $page.url.searchParams.get('edit') === '1' && canManage()) startEdit();
    if ($page.url.searchParams.get('photoError') === '1') {
      photoError =
        'The bag was created, but its photo could not be uploaded. Choose the photo again to retry.';
    }
  });

  function guardUnload(event: BeforeUnloadEvent) {
    if (!dirty) return;
    event.preventDefault();
    event.returnValue = '';
  }

  async function load() {
    loading = true;
    error = '';
    loadMoreError = '';
    notFound = false;
    try {
      coffee = await api<Coffee>(`/coffees/${id}`);
      form = coffeeToForm(coffee);
      baseline = JSON.stringify(form);
      try {
        insights = await api<CatalogInsights>(`/catalog/coffee/${id}/insights?limit=12`);
        insightsError = '';
      } catch (caught) {
        insightsError =
          caught instanceof Error ? caught.message : 'Brew results are temporarily unavailable.';
      }
      ratingInsights = null;
      ratingInsightsError = '';
      if ($sessionStore && !$sessionStore.profile.pin_change_required) {
        try {
          ratingInsights = await api<CoffeeRatingInsights>(
            `/coffees/${id}/rating-insights?limit=12&offset=0`
          );
        } catch (caught) {
          ratingInsightsError =
            caught instanceof Error
              ? caught.message
              : 'Tasting results are temporarily unavailable.';
        }
      }
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 404) notFound = true;
      else error = caught instanceof Error ? caught.message : 'Could not load this coffee.';
    } finally {
      loading = false;
    }
  }

  function startEdit() {
    if (!coffee || !canManage()) return;
    form = coffeeToForm(coffee);
    baseline = JSON.stringify(form);
    photoFile = null;
    removePhotoDraft = false;
    photoError = '';
    success = '';
    editMode = true;
  }

  function clearEditQuery() {
    const url = new URL(window.location.href);
    url.searchParams.delete('edit');
    url.searchParams.delete('photoError');
    history.replaceState(history.state, '', `${url.pathname}${url.search}${url.hash}`);
  }

  function cancelEdit() {
    if (!coffee) return;
    form = coffeeToForm(coffee);
    baseline = JSON.stringify(form);
    photoFile = null;
    removePhotoDraft = false;
    photoError = '';
    editMode = false;
    clearEditQuery();
  }

  async function save(event: SubmitEvent) {
    event.preventDefault();
    if (!coffee) return;
    saving = true;
    error = '';
    success = '';
    photoError = '';
    try {
      coffee = await api<Coffee>(`/coffees/${coffee.id}`, {
        method: 'PUT',
        body: jsonBody(coffeePayload(form))
      });
      form = coffeeToForm(coffee);
      baseline = JSON.stringify(form);
      try {
        if (photoFile) {
          coffee = await uploadCatalogPhoto<Coffee>(`/coffees/${coffee.id}/photo`, photoFile);
        } else if (removePhotoDraft && coffee.photo_path) {
          coffee = await api<Coffee>(`/coffees/${coffee.id}/photo`, { method: 'DELETE' });
        }
      } catch (caught) {
        photoError = `Coffee details were saved, but the photo failed: ${caught instanceof Error ? caught.message : 'Could not update the photo.'}`;
        return;
      }
      photoFile = null;
      removePhotoDraft = false;
      editMode = false;
      clearEditQuery();
      success = 'Coffee updated.';
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not update this coffee.';
    } finally {
      saving = false;
    }
  }

  async function cloneCoffee() {
    if (!coffee) return;
    cloning = true;
    error = '';
    try {
      const clone = await api<Coffee>(`/coffees/${coffee.id}/clone`, {
        method: 'POST',
        body: jsonBody({})
      });
      await goto(`/coffees/${clone.id}?edit=1`);
      await load();
      startEdit();
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not clone this bag.';
    } finally {
      cloning = false;
    }
  }

  async function archiveCoffee() {
    if (!coffee) return;
    archiving = true;
    error = '';
    try {
      await api<Coffee>(`/coffees/${coffee.id}/archive`, {
        method: 'POST',
        body: jsonBody({})
      });
      editMode = false;
      await goto('/coffees?message=Coffee%20archived.');
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not archive this coffee.';
      archiveOpen = false;
    } finally {
      archiving = false;
    }
  }

  async function loadMoreBrews() {
    if (!ratingInsights || ratingInsights.next_offset === null) return;
    loadingMore = true;
    loadMoreError = '';
    try {
      const next = await api<CoffeeRatingInsights>(
        `/coffees/${id}/rating-insights?limit=12&offset=${ratingInsights.next_offset}`
      );
      const existingIds = new Set(ratingInsights.rated_brews.map((result) => result.brew.id));
      ratingInsights = {
        ...next,
        rated_brews: [
          ...ratingInsights.rated_brews,
          ...next.rated_brews.filter((result) => !existingIds.has(result.brew.id))
        ]
      };
    } catch (caught) {
      loadMoreError =
        caught instanceof Error ? caught.message : 'Could not load older rated brews.';
    } finally {
      loadingMore = false;
    }
  }

  function recorded(value: string | null | undefined): string {
    return value || 'Not recorded';
  }
</script>

<svelte:window onbeforeunload={guardUnload} />
<svelte:head
  ><title>{coffee ? `${coffee.name} · Coffees` : 'Coffee details'} · Filter Coffee Club</title
  ></svelte:head
>

<div class="detail-page">
  <a class="back-link" href="/coffees">← Back to coffees</a>

  {#if loading}
    <div class="empty" role="status">Loading coffee details…</div>
  {:else if notFound}
    <section class="empty-state">
      <p class="eyebrow">404</p>
      <h1>Coffee not found.</h1>
      <p>This bag may never have existed, or its address is incorrect.</p>
      <a class="button secondary" href="/coffees">Browse coffees</a>
    </section>
  {:else if error && !coffee}
    <p class="error" role="alert">{error}</p>
  {:else if coffee}
    <section class="detail-hero">
      <div class="detail-photo" data-testid="detail-photo">
        <CatalogPhoto
          photoPath={editMode && removePhotoDraft ? null : coffee.photo_path}
          alt={`${coffee.roaster} ${coffee.name}`}
          endpoint={`/coffees/${coffee.id}/photo`}
          beanFallback
        />
      </div>
      <div class="detail-identity" data-testid="detail-identity">
        <div class="identity-topline">
          <p class="eyebrow">{coffee.roaster}</p>
          {#if coffee.archived}<span class="status archived">Archived</span>{/if}
        </div>
        <h1>{coffee.name}</h1>
        <p class="lede">
          {[coffee.country, coffee.region, coffee.process, coffee.roast_level]
            .filter(Boolean)
            .join(' · ') || 'Bag details have not been recorded yet.'}
        </p>
        {#if coffee.package_notes}<p class="package-notes">“{coffee.package_notes}”</p>{/if}
        {#if !coffee.archived}
          <div class="detail-actions">
            <a class="button" href={`/brews/new?coffee=${coffee.id}`}>Brew this</a>
            {#if canManage() && !editMode}<button class="secondary" onclick={startEdit}>Edit</button
              >{/if}
          </div>
        {/if}
        {#if canManage() && !editMode}
          <details class="more-actions">
            <summary>More actions</summary>
            <div class="actions">
              <button class="secondary" disabled={cloning} onclick={cloneCoffee}
                >{cloning ? 'Cloning…' : 'Clone bag'}</button
              >
              {#if $sessionStore?.profile.role === 'admin'}<button
                  class="danger"
                  onclick={() => (archiveOpen = true)}>Archive</button
                >{/if}
            </div>
          </details>
        {/if}
      </div>
    </section>

    {#if success}<p class="success" role="status">{success}</p>{/if}
    {#if error}<p class="error" role="alert">{error}</p>{/if}

    {#if editMode}
      <form class="panel edit-panel" onsubmit={save}>
        <div class="section-heading">
          <p class="eyebrow">Edit mode</p>
          <h2>Update bag details.</h2>
          <p class="muted">Changes stay local until you press Save changes.</p>
        </div>
        <CoffeeFields bind:form />
        {#if !$appSettingsStore?.demo_mode}
          <div class="photo-edit">
            <PhotoPicker
              bind:file={photoFile}
              label={coffee.photo_path ? 'Replacement photo (optional)' : 'Photo (optional)'}
            />
            {#if coffee.photo_path && !photoFile}
              {#if removePhotoDraft}<button
                  class="secondary"
                  type="button"
                  onclick={() => (removePhotoDraft = false)}>Keep current photo</button
                >{:else}<button
                  class="secondary"
                  type="button"
                  onclick={() => (removePhotoDraft = true)}>Remove current photo on save</button
                >{/if}
            {/if}
          </div>
        {/if}
        {#if photoError}<p class="error" role="alert">{photoError}</p>{/if}
        <div class="actions">
          <button class="primary" disabled={saving}>{saving ? 'Saving…' : 'Save changes'}</button
          ><button class="secondary" type="button" disabled={saving} onclick={cancelEdit}
            >Cancel</button
          >
        </div>
      </form>
    {:else}
      <section class="metadata-section" aria-labelledby="metadata-heading">
        <div class="section-heading">
          <p class="eyebrow">Recorded details</p>
          <h2 id="metadata-heading">About this bag.</h2>
        </div>
        <dl class="metadata-grid">
          <div>
            <dt>Roaster / brand</dt>
            <dd>{coffee.roaster}</dd>
          </div>
          <div>
            <dt>Coffee name</dt>
            <dd>{coffee.name}</dd>
          </div>
          <div>
            <dt>Country</dt>
            <dd>{recorded(coffee.country)}</dd>
          </div>
          <div>
            <dt>Region</dt>
            <dd>{recorded(coffee.region)}</dd>
          </div>
          <div>
            <dt>Producer / farm</dt>
            <dd>{recorded(coffee.producer)}</dd>
          </div>
          <div>
            <dt>Variety</dt>
            <dd>{recorded(coffee.variety)}</dd>
          </div>
          <div>
            <dt>Process</dt>
            <dd>{recorded(coffee.process)}</dd>
          </div>
          <div>
            <dt>Roast level</dt>
            <dd>{recorded(coffee.roast_level)}</dd>
          </div>
          <div>
            <dt>Roast date</dt>
            <dd>{coffee.roast_date ? formatCatalogDate(coffee.roast_date) : 'Not recorded'}</dd>
          </div>
          <div>
            <dt>Opened date</dt>
            <dd>{coffee.opened_date ? formatCatalogDate(coffee.opened_date) : 'Not recorded'}</dd>
          </div>
          <div>
            <dt>Cataloged</dt>
            <dd>{formatCatalogDate(coffee.created_at)}</dd>
          </div>
          <div>
            <dt>Cloned from</dt>
            <dd>{coffee.cloned_from_id ? `Coffee #${coffee.cloned_from_id}` : 'Original bag'}</dd>
          </div>
          <div class="wide">
            <dt>Package tasting notes</dt>
            <dd>{recorded(coffee.package_notes)}</dd>
          </div>
        </dl>
      </section>
    {/if}

    {#if insightsError}<p class="error partial" role="status">
        Coffee details are available, but brew results could not be loaded: {insightsError}
      </p>{/if}
    {#if ratingInsightsError}<p class="error partial" role="status">
        Coffee details are available, but tasting results could not be loaded: {ratingInsightsError}
      </p>{/if}
    {#if ratingInsights}
      <CoffeeTastingAnalysis
        {coffee}
        insights={ratingInsights}
        {loadingMore}
        {loadMoreError}
        onloadmore={loadMoreBrews}
      />
    {:else if !$sessionStore}
      <section class="analysis-signin panel" aria-labelledby="analysis-signin-heading">
        <p class="eyebrow">Tasting results</p>
        <h2 id="analysis-signin-heading">Sign in to see the club’s tasting analysis.</h2>
        <p class="muted">Coffee details and Latest activity remain available to everyone.</p>
        <a class="button" href={loginPath(`/coffees/${coffee.id}`)}>Sign in</a>
      </section>
    {:else if $sessionStore.profile.pin_change_required}
      <section class="analysis-signin panel" aria-labelledby="analysis-pin-heading">
        <p class="eyebrow">Tasting results</p>
        <h2 id="analysis-pin-heading">Finish setting up your PIN to see tasting analysis.</h2>
        <a class="button" href="/account/pin">Change PIN</a>
      </section>
    {/if}
    {#if insights}<RecentBrews {insights} />{/if}
  {/if}
</div>

<ConfirmDialog
  open={archiveOpen}
  title="Archive this coffee?"
  description="It will disappear from the catalog. Existing brews and this direct detail address will remain available, but no restore action will be added."
  confirmLabel="Archive coffee"
  busy={archiving}
  onconfirm={archiveCoffee}
  oncancel={() => (archiveOpen = false)}
/>

<style>
  .detail-page {
    --catalog-gap-xs: 4px;
    --catalog-gap-sm: 8px;
    --catalog-gap-md: 16px;
    --catalog-gap-lg: clamp(30px, 6vw, 58px);
    display: grid;
    gap: var(--catalog-gap-lg);
    min-width: 0;
  }
  .detail-page :global(h1),
  .detail-page :global(h2),
  .detail-page :global(p) {
    margin: 0;
  }
  .back-link {
    width: fit-content;
    font-weight: 800;
    text-decoration: none;
  }
  .detail-hero {
    display: grid;
    grid-template-columns: minmax(240px, 0.75fr) minmax(0, 1.25fr);
    gap: clamp(22px, 5vw, 52px);
    align-items: center;
  }
  .detail-photo {
    min-width: 0;
  }
  .detail-identity,
  .section-heading,
  .metadata-section,
  .edit-panel,
  .photo-edit,
  .analysis-signin {
    display: grid;
  }
  .detail-identity {
    gap: var(--catalog-gap-md);
  }
  .identity-topline {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .detail-identity h1 {
    max-width: 16ch;
    margin: 0;
    font-size: clamp(2.5rem, 7vw, 5.5rem);
  }
  .package-notes {
    max-width: 55ch;
    padding: 12px 15px;
    border-left: 3px solid var(--amber);
    background: var(--surface);
    font-style: italic;
    line-height: 1.55;
  }
  .detail-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
  }
  .more-actions {
    width: fit-content;
    min-width: min(100%, 260px);
  }
  .section-heading {
    gap: var(--catalog-gap-sm);
  }
  .section-heading h2 {
    font-size: clamp(1.8rem, 4vw, 2.7rem);
  }
  .metadata-section,
  .edit-panel {
    gap: var(--catalog-gap-md);
  }
  .metadata-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 1px;
    margin: 0;
    overflow: hidden;
    border: 1px solid var(--line);
    border-radius: 18px;
    background: var(--line);
  }
  .metadata-grid div {
    display: grid;
    align-content: start;
    gap: 5px;
    min-width: 0;
    padding: 16px;
    background: var(--surface);
  }
  .metadata-grid .wide {
    grid-column: span 2;
  }
  dt {
    color: var(--muted);
    font-size: 0.72rem;
    font-weight: 800;
    letter-spacing: 0.07em;
    text-transform: uppercase;
  }
  dd {
    margin: 0;
    overflow-wrap: anywhere;
    line-height: 1.45;
  }
  .photo-edit {
    gap: 12px;
  }
  .analysis-signin {
    justify-items: start;
    gap: 12px;
  }
  .analysis-signin h2 {
    margin: 0;
    font-size: clamp(1.6rem, 4vw, 2.4rem);
  }
  .photo-edit button {
    width: fit-content;
  }
  .empty-state {
    display: grid;
    justify-items: start;
    gap: 16px;
    padding: clamp(28px, 7vw, 70px);
    border: 1px solid var(--line);
    border-radius: 22px;
    background: var(--surface);
  }
  .empty-state h1 {
    margin: 0;
  }
  @media (max-width: 760px) {
    .detail-hero {
      grid-template-columns: 1fr;
    }
    .detail-photo {
      max-width: 520px;
    }
    .metadata-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
  @media (max-width: 480px) {
    .metadata-grid {
      grid-template-columns: 1fr;
    }
    .metadata-grid .wide {
      grid-column: auto;
    }
  }
</style>
