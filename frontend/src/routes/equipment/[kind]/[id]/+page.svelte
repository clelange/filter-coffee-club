<script lang="ts">
  import { onMount } from 'svelte';
  import { beforeNavigate, goto } from '$app/navigation';
  import { page } from '$app/stores';
  import CatalogMetrics from '$lib/CatalogMetrics.svelte';
  import CatalogPhoto from '$lib/CatalogPhoto.svelte';
  import ConfirmDialog from '$lib/ConfirmDialog.svelte';
  import DripperFields from '$lib/DripperFields.svelte';
  import FilterFields from '$lib/FilterFields.svelte';
  import GrinderFields from '$lib/GrinderFields.svelte';
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
  import {
    dripperPayload,
    dripperToForm,
    emptyDripperForm,
    emptyFilterForm,
    emptyGrinderForm,
    filterPayload,
    filterToForm,
    formatCatalogNumber,
    grinderPayload,
    grinderToForm
  } from '$lib/catalog';
  import { deviceModeStore, loginPath } from '$lib/device';
  import type {
    BrewFilter,
    CatalogInsights,
    CatalogKind,
    Dripper,
    DripperFormData,
    FilterFormData,
    Grinder,
    GrinderFormData
  } from '$lib/types';

  type EquipmentItem = Grinder | Dripper | BrewFilter;
  type RouteKind = 'grinders' | 'drippers' | 'filters';

  let item: EquipmentItem | null = $state(null);
  let insights: CatalogInsights | null = $state(null);
  let grinderForm: GrinderFormData = $state(emptyGrinderForm());
  let dripperForm: DripperFormData = $state(emptyDripperForm());
  let filterForm: FilterFormData = $state(emptyFilterForm());
  let baseline = $state('');
  let editMode = $state(false);
  let loading = $state(true);
  let notFound = $state(false);
  let error = $state('');
  let insightsError = $state('');
  let success = $state('');
  let photoError = $state('');
  let photoFile: File | null = $state(null);
  let removePhotoDraft = $state(false);
  let saving = $state(false);
  let archiveOpen = $state(false);
  let archiving = $state(false);

  const routeKind = $derived($page.params.kind as RouteKind);
  const validKind = $derived(['grinders', 'drippers', 'filters'].includes(routeKind));
  const singularKind = $derived(
    (routeKind === 'grinders'
      ? 'grinder'
      : routeKind === 'drippers'
        ? 'dripper'
        : 'filter') as CatalogKind
  );
  const id = $derived(Number($page.params.id));
  const currentFormSnapshot = $derived(
    routeKind === 'grinders'
      ? JSON.stringify(grinderForm)
      : routeKind === 'drippers'
        ? JSON.stringify(dripperForm)
        : JSON.stringify(filterForm)
  );
  const dirty = $derived(
    editMode && (currentFormSnapshot !== baseline || photoFile !== null || removePhotoDraft)
  );
  function canManage(): boolean {
    return Boolean($sessionStore && $deviceModeStore !== 'kiosk' && item && !item.archived);
  }

  beforeNavigate(({ cancel }) => {
    if (dirty && !confirm('Discard your unsaved equipment changes?')) cancel();
  });

  onMount(async () => {
    if (!validKind) {
      notFound = true;
      loading = false;
      return;
    }
    if (!(await ensureSession())) {
      await goto(loginPath(`/equipment/${routeKind}/${id}`));
      return;
    }
    await load();
    if (item && $page.url.searchParams.get('edit') === '1' && canManage()) startEdit();
  });

  function guardUnload(event: BeforeUnloadEvent) {
    if (!dirty) return;
    event.preventDefault();
    event.returnValue = '';
  }

  async function load() {
    loading = true;
    error = '';
    notFound = false;
    try {
      item = await api<EquipmentItem>(`/${routeKind}/${id}`);
      resetForm();
      try {
        insights = await api<CatalogInsights>(`/catalog/${singularKind}/${id}/insights?limit=12`);
        insightsError = '';
      } catch (caught) {
        insightsError =
          caught instanceof Error ? caught.message : 'Brew results are temporarily unavailable.';
      }
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 404) notFound = true;
      else error = caught instanceof Error ? caught.message : 'Could not load this equipment.';
    } finally {
      loading = false;
    }
  }

  function resetForm() {
    if (!item) return;
    if (routeKind === 'grinders') grinderForm = grinderToForm(item as Grinder);
    else if (routeKind === 'drippers') dripperForm = dripperToForm(item as Dripper);
    else filterForm = filterToForm(item as BrewFilter);
    baseline =
      routeKind === 'grinders'
        ? JSON.stringify(grinderForm)
        : routeKind === 'drippers'
          ? JSON.stringify(dripperForm)
          : JSON.stringify(filterForm);
  }

  function startEdit() {
    if (!item || !canManage()) return;
    resetForm();
    photoFile = null;
    removePhotoDraft = false;
    photoError = '';
    success = '';
    editMode = true;
  }

  function clearEditQuery() {
    const url = new URL(window.location.href);
    url.searchParams.delete('edit');
    history.replaceState(history.state, '', `${url.pathname}${url.search}${url.hash}`);
  }

  function cancelEdit() {
    resetForm();
    photoFile = null;
    removePhotoDraft = false;
    photoError = '';
    editMode = false;
    clearEditQuery();
  }

  async function save(event: SubmitEvent) {
    event.preventDefault();
    if (!item) return;
    saving = true;
    error = '';
    success = '';
    photoError = '';
    try {
      const body =
        routeKind === 'grinders'
          ? grinderPayload(grinderForm)
          : routeKind === 'drippers'
            ? dripperPayload(dripperForm)
            : filterPayload(filterForm);
      item = await api<EquipmentItem>(`/${routeKind}/${item.id}`, {
        method: 'PUT',
        body: jsonBody(body)
      });
      resetForm();
      try {
        if (photoFile) {
          item = await uploadCatalogPhoto<EquipmentItem>(
            `/${routeKind}/${item.id}/photo`,
            photoFile
          );
        } else if (removePhotoDraft && item.photo_path) {
          item = await api<EquipmentItem>(`/${routeKind}/${item.id}/photo`, { method: 'DELETE' });
        }
      } catch (caught) {
        photoError = `Equipment details were saved, but the photo failed: ${caught instanceof Error ? caught.message : 'Could not update the photo.'}`;
        return;
      }
      photoFile = null;
      removePhotoDraft = false;
      editMode = false;
      clearEditQuery();
      success = 'Equipment updated.';
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not update this equipment.';
    } finally {
      saving = false;
    }
  }

  async function archiveItem() {
    if (!item) return;
    archiving = true;
    error = '';
    try {
      await api<EquipmentItem>(`/${routeKind}/${item.id}/archive`, {
        method: 'POST',
        body: jsonBody({})
      });
      editMode = false;
      await goto('/equipment?message=Equipment%20archived.');
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not archive this equipment.';
      archiveOpen = false;
    } finally {
      archiving = false;
    }
  }

  function title(): string {
    if (!item) return 'Equipment';
    if (routeKind === 'grinders')
      return `${(item as Grinder).manufacturer} ${(item as Grinder).model}`;
    if (routeKind === 'drippers')
      return `${(item as Dripper).manufacturer ?? ''} ${(item as Dripper).model}`.trim();
    return (item as BrewFilter).name;
  }

  function eyebrow(): string {
    if (routeKind === 'grinders') return 'Grinder';
    if (routeKind === 'drippers') return 'Dripper';
    return 'Filter';
  }

  function summary(): string {
    if (!item) return '';
    if (routeKind === 'grinders') {
      const grinder = item as Grinder;
      return `${grinder.setting_unit} · step ${grinder.setting_step} · usual range ${grinder.soft_min ?? '—'}–${grinder.soft_max ?? '—'}`;
    }
    if (routeKind === 'drippers')
      return (item as Dripper).notes ?? 'No notes have been recorded yet.';
    return (item as BrewFilter).notes ?? 'No notes have been recorded yet.';
  }
</script>

<svelte:window onbeforeunload={guardUnload} />
<svelte:head
  ><title>{item ? `${title()} · Equipment` : 'Equipment details'} · Filter Coffee Club</title
  ></svelte:head
>

<div class="detail-page">
  <a class="back-link" href="/equipment">← Back to equipment</a>

  {#if loading}
    <div class="empty" role="status">Loading equipment details…</div>
  {:else if notFound}
    <section class="empty-state">
      <p class="eyebrow">404</p>
      <h1>Equipment not found.</h1>
      <p>This item may never have existed, or its address is incorrect.</p>
      <a class="button secondary" href="/equipment">Browse equipment</a>
    </section>
  {:else if error && !item}
    <p class="error" role="alert">{error}</p>
  {:else if item}
    <section class="detail-hero">
      <div class="detail-photo" data-testid="detail-photo">
        <CatalogPhoto
          photoPath={editMode && removePhotoDraft ? null : item.photo_path}
          alt={title()}
          endpoint={`/${routeKind}/${item.id}/photo`}
        />
      </div>
      <div class="detail-identity" data-testid="detail-identity">
        <div class="identity-topline">
          <p class="eyebrow">{eyebrow()}</p>
          {#if item.archived}<span class="status archived">Archived</span>{/if}
        </div>
        <h1>{title()}</h1>
        <p class="lede">{summary()}</p>
        {#if canManage() && !editMode}<div class="detail-actions">
            <button class="primary" onclick={startEdit}>Edit</button>
          </div>{/if}
        {#if canManage() && !editMode && $sessionStore?.profile.role === 'admin'}
          <details class="more-actions">
            <summary>More actions</summary>
            <div class="actions">
              <button class="danger" onclick={() => (archiveOpen = true)}>Archive</button>
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
          <h2>Update {eyebrow().toLowerCase()} details.</h2>
          <p class="muted">Changes stay local until you press Save changes.</p>
        </div>
        {#if routeKind === 'grinders'}<GrinderFields
            bind:form={grinderForm}
          />{:else if routeKind === 'drippers'}<DripperFields
            bind:form={dripperForm}
          />{:else}<FilterFields bind:form={filterForm} />{/if}
        {#if !$appSettingsStore?.demo_mode}
          <div class="photo-edit">
            <PhotoPicker
              bind:file={photoFile}
              label={item.photo_path ? 'Replacement photo (optional)' : 'Photo (optional)'}
            />
            {#if item.photo_path && !photoFile}
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
          <h2 id="metadata-heading">About this {eyebrow().toLowerCase()}.</h2>
        </div>
        <dl class="metadata-grid">
          {#if routeKind === 'grinders'}
            {@const grinder = item as Grinder}
            <div>
              <dt>Manufacturer</dt>
              <dd>{grinder.manufacturer}</dd>
            </div>
            <div>
              <dt>Model</dt>
              <dd>{grinder.model}</dd>
            </div>
            <div>
              <dt>Setting unit</dt>
              <dd>{grinder.setting_unit}</dd>
            </div>
            <div>
              <dt>Setting step</dt>
              <dd>{formatCatalogNumber(grinder.setting_step)}</dd>
            </div>
            <div>
              <dt>Soft minimum</dt>
              <dd>{formatCatalogNumber(grinder.soft_min)}</dd>
            </div>
            <div>
              <dt>Soft maximum</dt>
              <dd>{formatCatalogNumber(grinder.soft_max)}</dd>
            </div>
            <div class="wide">
              <dt>Guidance</dt>
              <dd>{grinder.guidance ?? 'Not recorded'}</dd>
            </div>
          {:else if routeKind === 'drippers'}
            {@const dripper = item as Dripper}
            <div>
              <dt>Manufacturer</dt>
              <dd>{dripper.manufacturer ?? 'Not recorded'}</dd>
            </div>
            <div>
              <dt>Model</dt>
              <dd>{dripper.model}</dd>
            </div>
            <div class="wide">
              <dt>Notes</dt>
              <dd>{dripper.notes ?? 'Not recorded'}</dd>
            </div>
          {:else}
            {@const brewFilter = item as BrewFilter}
            <div>
              <dt>Name</dt>
              <dd>{brewFilter.name}</dd>
            </div>
            <div class="wide">
              <dt>Notes</dt>
              <dd>{brewFilter.notes ?? 'Not recorded'}</dd>
            </div>
          {/if}
        </dl>
      </section>
    {/if}

    {#if insightsError}<p class="error partial" role="status">
        Equipment details are available, but brew results could not be loaded: {insightsError}
      </p>{/if}
    {#if insights}<CatalogMetrics {insights} /><RecentBrews {insights} />{/if}
  {/if}
</div>

<ConfirmDialog
  open={archiveOpen}
  title={`Archive this ${eyebrow().toLowerCase()}?`}
  description="It will disappear from the equipment catalog. Existing brews and this direct detail address will remain available, but no restore action will be added."
  confirmLabel="Archive equipment"
  busy={archiving}
  onconfirm={archiveItem}
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
  .photo-edit {
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
    max-width: 17ch;
    margin: 0;
    font-size: clamp(2.5rem, 7vw, 5.5rem);
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
