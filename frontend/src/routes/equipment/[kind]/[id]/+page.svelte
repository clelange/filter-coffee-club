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
    updateCatalogPhotoFraming,
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
    grinderUpdatePayload,
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
    GrinderFormData,
    PhotoFraming
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
  let photoFramingDraft: PhotoFraming | null = $state(null);
  let photoFramingBaseline = $state('null');
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
    editMode &&
      (currentFormSnapshot !== baseline ||
        photoFile !== null ||
        removePhotoDraft ||
        JSON.stringify(photoFramingDraft) !== photoFramingBaseline)
  );
  function canManage(): boolean {
    return Boolean($sessionStore && $deviceModeStore !== 'kiosk' && item && !item.archived);
  }

  beforeNavigate(({ cancel, willUnload }) => {
    if (!dirty) return;
    if (willUnload || !window.confirm('Discard your unsaved equipment changes?')) cancel();
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
    photoFramingDraft = item.photo_framing;
    photoFramingBaseline = JSON.stringify(item.photo_framing);
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
    if (!item) return;
    resetForm();
    photoFile = null;
    photoFramingDraft = item.photo_framing;
    photoFramingBaseline = JSON.stringify(item.photo_framing);
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
      const framingChanged = JSON.stringify(photoFramingDraft) !== photoFramingBaseline;
      const predefinedGrinder =
        routeKind === 'grinders' && (item as Grinder).definition_key !== 'custom';
      if (!predefinedGrinder) {
        const body =
          routeKind === 'grinders'
            ? grinderUpdatePayload(grinderForm)
            : routeKind === 'drippers'
              ? dripperPayload(dripperForm)
              : filterPayload(filterForm);
        item = await api<EquipmentItem>(`/${routeKind}/${item.id}`, {
          method: 'PUT',
          body: jsonBody(body)
        });
      }
      resetForm();
      try {
        if (photoFile) {
          item = await uploadCatalogPhoto<EquipmentItem>(
            `/${routeKind}/${item.id}/photo`,
            photoFile,
            photoFramingDraft
          );
        } else if (removePhotoDraft && item.photo_path) {
          item = await api<EquipmentItem>(`/${routeKind}/${item.id}/photo`, { method: 'DELETE' });
        } else if (framingChanged) {
          item = await updateCatalogPhotoFraming<EquipmentItem>(
            `/${routeKind}/${item.id}/photo`,
            photoFramingDraft
          );
        }
      } catch (caught) {
        photoError = `Equipment details were saved, but the photo failed: ${caught instanceof Error ? caught.message : 'Could not update the photo.'}`;
        return;
      }
      photoFile = null;
      photoFramingDraft = item.photo_framing;
      photoFramingBaseline = JSON.stringify(item.photo_framing);
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
          photoFraming={editMode ? photoFramingDraft : item.photo_framing}
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
        {#if routeKind === 'grinders'}
          {#if (item as Grinder).definition_key === 'custom'}
            <GrinderFields bind:form={grinderForm} editing />
          {:else}
            <div class="predefined-note" role="note">
              <strong>{title()}</strong>
              <span>{summary()}</span>
              <span>
                This predefined grinder’s identity and adjustment specifications are managed by FCC.
                You can still update its photo.
              </span>
            </div>
          {/if}
        {:else if routeKind === 'drippers'}<DripperFields
            bind:form={dripperForm}
          />{:else}<FilterFields bind:form={filterForm} />{/if}
        {#if !$appSettingsStore?.demo_mode}
          <div class="photo-edit">
            <PhotoPicker
              bind:file={photoFile}
              bind:framing={photoFramingDraft}
              photoPath={removePhotoDraft ? null : item.photo_path}
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
              <dt>Definition</dt>
              <dd>{grinder.definition_key === 'custom' ? 'Custom' : 'Predefined'}</dd>
            </div>
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
  .predefined-note {
    display: grid;
    gap: 6px;
    padding: 16px;
    border: 1px solid var(--line);
    border-radius: 14px;
    background: color-mix(in srgb, var(--cyan) 7%, var(--surface));
  }
  .predefined-note span {
    color: var(--muted);
  }
</style>
