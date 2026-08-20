<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { beforeNavigate, goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { refreshBrewStatusAfterMutation } from '$lib/brew-status';
  import {
    brewRatioIsUnusual,
    calculateBrewRatio,
    unusualBrewRatioDescription
  } from '$lib/brew-ratio';
  import {
    applyRecipeCalculation,
    isClickGrinder,
    presetGrinderSetting,
    presetDeviations as getPresetDeviations,
    recipeAmountError,
    type RecipeCalculationAction,
    type RecipeCalculationState
  } from '$lib/brew-recipe';
  import CoffeeColorPicker from '$lib/CoffeeColorPicker.svelte';
  import ConfirmDialog from '$lib/ConfirmDialog.svelte';
  import ProfileLink from '$lib/ProfileLink.svelte';
  import { deviceModeStore, loginPath } from '$lib/device';
  import { ApiError, api, appSettingsStore, ensureSession, jsonBody } from '$lib/api';
  import NumberStepper from '$lib/NumberStepper.svelte';
  import { formatGrinderSetting } from '$lib/catalog';
  import type {
    ActiveBrews,
    Brew,
    BrewActivityItem,
    BrewFilter,
    BrewInput,
    Coffee,
    Dripper,
    Grinder,
    GrinderDefinition,
    Preset,
    ProfileIdentity
  } from '$lib/types';

  type BrewDraft = Omit<BrewInput, 'grinder_setting'> & { grinder_setting: number | null };

  let coffees: Coffee[] = $state([]);
  let coffeeColorPeers: Coffee[] = $state([]);
  let grinders: Grinder[] = $state([]);
  let grinderDefinitions: GrinderDefinition[] = $state([]);
  let drippers: Dripper[] = $state([]);
  let filters: BrewFilter[] = $state([]);
  let presets: Preset[] = $state([]);
  let operators: ProfileIdentity[] = $state([]);
  let history: Brew[] = $state([]);
  let editId = $state<number | null>(null);
  let sourceRevision = $state(0);
  let editorChangedExternally = $state(false);
  let active: ActiveBrews | null = $state(null);
  let revisionTimer: ReturnType<typeof setInterval> | null = null;
  let capacityTimer: ReturnType<typeof setTimeout> | null = null;
  let checkingCapacity = $state(false);
  let joiningBrewId = $state<number | null>(null);
  let destroyed = false;
  let correctionId = $state<number | null>(null);
  let correctionMinutes = $state(3);
  let correctionSeconds = $state(0);
  let correctionOperatorId = $state(0);
  let originalOperatorId = $state(0);
  let originalOperatorName = $state('');
  let grinderSettingNeedsReview = $state(false);
  let ratioConfirmationOpen = $state(false);
  let showCoffeeForm = $state(false);
  let coffeeError = $state('');
  let addingCoffee = $state(false);
  let coffeeCreationKey = $state('');
  let brewCreationKey = $state('');
  let error = $state('');
  let saving = $state(false);
  let ready = $state(false);
  let baseline = $state('');
  let newCoffee = $state({
    roaster: '',
    name: '',
    country: '',
    purchase_location: '',
    process: '',
    roast_level: '',
    chart_color: ''
  });
  let form: BrewDraft = $state({
    coffee_id: 0,
    grinder_id: 0,
    dripper_id: null,
    filter_id: null,
    source_preset_id: null,
    dose_g: 8,
    water_g: 128,
    target_ratio: 16,
    temperature_c: 94,
    grinder_setting: null,
    servings: 1,
    target_flow_g_s: 4.5,
    bloom_water_g: null,
    bloom_time_s: null,
    pour_count: null,
    technique_note: null
  });
  let recipeState: RecipeCalculationState = $state({
    basis: 'coffee',
    dose_g: 8,
    water_g: 128,
    target_ratio: 16,
    bloom_water_g: null,
    servings: 1
  });

  const ratio = $derived(calculateBrewRatio(form.water_g, form.dose_g));
  const unusualRatio = $derived(brewRatioIsUnusual(form.water_g, form.dose_g));
  const grinder = $derived(grinders.find((item) => item.id === Number(form.grinder_id)));
  const grinderDefinition = $derived(
    grinderDefinitions.find((item) => item.key === grinder?.definition_key)
  );
  const selectedCoffee = $derived(coffees.find((item) => item.id === Number(form.coffee_id)));
  const selectedPreset = $derived(
    presets.find((item) => item.id === Number(form.source_preset_id))
  );
  const visiblePresets = $derived(
    presets.filter((item) => item.active || item.id === Number(form.source_preset_id))
  );
  const selectedPresetGrinderRange = $derived(
    selectedPreset?.grinder_ranges.find((item) => item.grinder_id === Number(form.grinder_id))
  );
  const clickGrinder = $derived(isClickGrinder(grinder));
  const settingWarning = $derived(
    grinder &&
      form.grinder_setting !== null &&
      ((grinder.soft_min !== null && form.grinder_setting < grinder.soft_min) ||
        (grinder.soft_max !== null && form.grinder_setting > grinder.soft_max))
  );
  const grinderSettingInvalid = $derived(
    Boolean(
      form.grinder_setting !== null && clickGrinder && !Number.isInteger(form.grinder_setting)
    )
  );
  const bloomWaterInvalid = $derived(
    form.bloom_water_g !== null && form.bloom_water_g > form.water_g
  );
  const amountError = $derived(recipeAmountError(form.dose_g, form.water_g));
  const presetDeviations = $derived(
    getPresetDeviations(form, selectedPreset, Number(form.grinder_id))
  );
  const recipeInvalid = $derived(
    Boolean(
      amountError ||
      bloomWaterInvalid ||
      grinderSettingInvalid ||
      !form.grinder_id ||
      form.grinder_setting === null
    )
  );
  const editorDirty = $derived(ready && baseline !== '' && editorSnapshot() !== baseline);

  function editorSnapshot(): string {
    return JSON.stringify({
      form,
      correctionMinutes,
      correctionSeconds,
      correctionOperatorId,
      showCoffeeForm,
      newCoffee
    });
  }

  beforeNavigate(({ cancel, willUnload }) => {
    if (!editorDirty || saving) return;
    if (willUnload || !window.confirm('Discard your unsaved recipe changes and leave this page?'))
      cancel();
  });

  function updateRecipe(action: RecipeCalculationAction) {
    recipeState = applyRecipeCalculation(
      { ...recipeState, bloom_water_g: form.bloom_water_g },
      action
    );
    form.dose_g = recipeState.dose_g;
    form.water_g = recipeState.water_g;
    form.target_ratio = recipeState.target_ratio;
    form.bloom_water_g = recipeState.bloom_water_g;
    form.servings = recipeState.servings;
  }

  onMount(async () => {
    const session = await ensureSession();
    if (!session) {
      await goto(loginPath($page.url.pathname + $page.url.search));
      return;
    }
    correctionId = Number($page.url.searchParams.get('correct')) || null;
    editId = Number($page.url.searchParams.get('edit')) || null;
    const repeatId = Number($page.url.searchParams.get('repeat')) || null;
    if (correctionId) {
      if ($deviceModeStore === 'kiosk') {
        await goto(`/brews/${correctionId}`);
        return;
      }
    }
    try {
      if (!editId && !correctionId) {
        active = await api<ActiveBrews>('/brews/active');
        if (!active.can_start) {
          scheduleCapacityRefresh();
          return;
        }
      }
      const [
        coffeeItems,
        grinderItems,
        definitionItems,
        dripperItems,
        filterItems,
        presetItems,
        operatorItems
      ] = await Promise.all([
        api<Coffee[]>('/coffees?include_finished=true'),
        api<Grinder[]>('/grinders'),
        api<GrinderDefinition[]>('/grinder-definitions'),
        api<Dripper[]>('/drippers'),
        api<BrewFilter[]>('/filters'),
        api<Preset[]>('/presets?active_only=false'),
        correctionId ? api<ProfileIdentity[]>('/auth/profiles') : Promise.resolve([])
      ]);
      coffeeColorPeers = coffeeItems;
      coffees = coffeeItems.filter((coffee) => coffee.available);
      grinders = grinderItems;
      grinderDefinitions = definitionItems;
      drippers = dripperItems;
      filters = filterItems;
      presets = presetItems;
      operators = operatorItems;
      const requestedCoffeeId = Number($page.url.searchParams.get('coffee')) || 0;
      form.coffee_id =
        coffees.find((coffee) => coffee.id === requestedCoffeeId)?.id || coffees[0]?.id || 0;
      if (requestedCoffeeId && form.coffee_id !== requestedCoffeeId) {
        error = 'That coffee is no longer available for brewing. Choose an available bag.';
      }
      form.grinder_id = grinders.length === 1 ? grinders[0].id : 0;
      if (editId || repeatId || correctionId) {
        const source = await api<Brew>(`/brews/${editId || repeatId || correctionId}`);
        if (
          correctionId &&
          session.profile.role !== 'admin' &&
          session.profile.id !== source.operator_id
        ) {
          await goto(`/brews/${correctionId}`);
          return;
        }
        if (!grinderItems.some((item) => item.id === source.grinder_id)) {
          const sourceGrinder = await api<Grinder>(`/grinders/${source.grinder_id}`);
          grinders = [...grinders, sourceGrinder];
        }
        copyBrew(source);
        let sourceCoffee = coffeeItems.find((coffee) => coffee.id === source.coffee_id);
        if (!sourceCoffee && (editId || correctionId)) {
          sourceCoffee = await api<Coffee>(`/coffees/${source.coffee_id}`);
          coffeeColorPeers = [...coffeeColorPeers, sourceCoffee];
        }
        if ((editId || correctionId) && sourceCoffee && !sourceCoffee.available) {
          coffees = [sourceCoffee, ...coffees.filter((coffee) => coffee.id !== sourceCoffee.id)];
        } else if (repeatId && !sourceCoffee?.available) {
          form.coffee_id = coffees[0]?.id || 0;
          error =
            'The coffee from that recipe is no longer available. Choose an available bag before saving.';
        }
        sourceRevision = source.revision;
        if (editId) revisionTimer = setInterval(checkEditorRevision, 3000);
        if (correctionId) {
          correctionOperatorId = source.operator_id;
          originalOperatorId = source.operator_id;
          originalOperatorName = source.operator_name;
          if (source.total_brew_time_s) {
            correctionMinutes = Math.floor(source.total_brew_time_s / 60);
            correctionSeconds = source.total_brew_time_s % 60;
          }
        }
      }
      await loadHistory();
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not load the recipe form.';
    } finally {
      baseline = editorSnapshot();
      ready = true;
    }
  });

  onDestroy(() => {
    destroyed = true;
    if (revisionTimer) clearInterval(revisionTimer);
    if (capacityTimer) clearTimeout(capacityTimer);
  });

  function scheduleCapacityRefresh() {
    if (destroyed || capacityTimer || active?.can_start) return;
    capacityTimer = setTimeout(async () => {
      capacityTimer = null;
      await refreshCapacity();
      scheduleCapacityRefresh();
    }, 3000);
  }

  async function refreshCapacity() {
    if (checkingCapacity) return;
    checkingCapacity = true;
    try {
      active = await api<ActiveBrews>('/brews/active');
      if (active.can_start) location.reload();
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not refresh brew capacity.';
    } finally {
      checkingCapacity = false;
    }
  }

  async function checkEditorRevision() {
    if (!editId || editorChangedExternally) return;
    try {
      const latest = await api<Brew>(`/brews/${editId}`);
      if (latest.revision !== sourceRevision) editorChangedExternally = true;
    } catch {
      // Submission remains the authoritative conflict check when polling is unavailable.
    }
  }

  function copyBrew(source: Brew) {
    form = {
      coffee_id: source.coffee_id,
      grinder_id: source.grinder_id,
      dripper_id: source.dripper_id,
      filter_id: source.filter_id,
      source_preset_id: source.source_preset_id,
      dose_g: source.dose_g,
      water_g: source.water_g,
      target_ratio: source.target_ratio,
      temperature_c: source.temperature_c,
      grinder_setting: source.grinder_setting,
      servings: source.servings,
      target_flow_g_s: source.target_flow_g_s,
      bloom_water_g: source.bloom_water_g,
      bloom_time_s: source.bloom_time_s,
      pour_count: source.pour_count,
      technique_note: source.technique_note
    };
    recipeState = {
      basis: 'coffee',
      dose_g: source.dose_g,
      water_g: source.water_g,
      target_ratio: source.target_ratio,
      bloom_water_g: source.bloom_water_g,
      servings: source.servings
    };
    grinderSettingNeedsReview = false;
  }

  async function loadHistory() {
    history = form.coffee_id
      ? await api<Brew[]>(`/brews?coffee_id=${form.coffee_id}&status=completed&limit=12`)
      : [];
  }

  function applyPreset(preset: Preset) {
    if (!preset.active || !grinder) return;
    form.source_preset_id = preset.id;
    form.temperature_c = Math.round((preset.temperature_min_c + preset.temperature_max_c) / 2);
    const presetSetting = presetGrinderSetting(preset, grinder);
    if (presetSetting !== null) {
      form.grinder_setting = presetSetting;
      grinderSettingNeedsReview = false;
    } else {
      form.grinder_setting = null;
      grinderSettingNeedsReview = true;
    }
    updateRecipe({ type: 'ratio', value: preset.ratio });
    updateRecipe({ type: 'coffee-shortcut' });
  }

  function useWaterBasis() {
    updateRecipe({ type: 'water-shortcut' });
  }

  function useCoffeeBasis() {
    updateRecipe({ type: 'coffee-shortcut' });
  }

  function changeDose(value: number | null) {
    if (value === null || value <= 0) return;
    updateRecipe({ type: 'dose', value });
  }

  function changeWater(value: number | null) {
    if (value === null || value <= 0 || form.target_ratio <= 0) return;
    updateRecipe({ type: 'water', value });
  }

  function changeRatio(value: number | null) {
    if (value === null || value <= 0) return;
    updateRecipe({ type: 'ratio', value });
  }

  function changeGrinder() {
    const nextGrinder = grinders.find((item) => item.id === Number(form.grinder_id));
    const presetSetting =
      nextGrinder && selectedPreset ? presetGrinderSetting(selectedPreset, nextGrinder) : null;
    form.grinder_setting = null;
    if (presetSetting !== null) {
      form.grinder_setting = presetSetting;
      grinderSettingNeedsReview = false;
    } else {
      grinderSettingNeedsReview = true;
    }
  }

  function rangeForPreset(preset: Preset) {
    return preset.grinder_ranges.find((range) => range.grinder_id === Number(form.grinder_id));
  }

  function presetGrindLabel(preset: Preset): string {
    if (!grinder) return 'Choose a grinder to see its range';
    const range = rangeForPreset(preset);
    if (!range) return `No guidance for ${grinder.manufacturer} ${grinder.model}`;
    return `${range.setting_min}–${range.setting_max} ${grinder.setting_unit}`;
  }

  function confirmGrinderSetting() {
    grinderSettingNeedsReview = false;
  }

  function rescaleServings(value: number | null) {
    if (value === null || value <= 0) return;
    updateRecipe({ type: 'servings', value });
  }

  async function addCoffee(event: SubmitEvent) {
    event.preventDefault();
    if (addingCoffee) return;
    addingCoffee = true;
    coffeeError = '';
    const idempotencyKey = coffeeCreationKey || crypto.randomUUID();
    coffeeCreationKey = idempotencyKey;
    try {
      const coffee = await api<Coffee>('/coffees', {
        method: 'POST',
        headers: { 'Idempotency-Key': idempotencyKey },
        body: jsonBody({
          ...newCoffee,
          country: newCoffee.country || null,
          purchase_location: newCoffee.purchase_location || null,
          process: newCoffee.process || null,
          roast_level: newCoffee.roast_level || null,
          chart_color: newCoffee.chart_color || null
        })
      });
      coffees = [...coffees, coffee];
      coffeeColorPeers = [...coffeeColorPeers, coffee];
      form.coffee_id = coffee.id;
      newCoffee = {
        roaster: '',
        name: '',
        country: '',
        purchase_location: '',
        process: '',
        roast_level: '',
        chart_color: ''
      };
      showCoffeeForm = false;
      coffeeCreationKey = '';
      await loadHistory();
    } catch (caught) {
      if (caught instanceof ApiError && caught.status < 500)
        coffeeCreationKey = crypto.randomUUID();
      coffeeError = caught instanceof Error ? caught.message : 'Could not add this coffee.';
    } finally {
      addingCoffee = false;
    }
  }

  function toggleCoffeeForm() {
    if (addingCoffee) return;
    showCoffeeForm = !showCoffeeForm;
    coffeeCreationKey = showCoffeeForm ? crypto.randomUUID() : '';
    if (showCoffeeForm) coffeeError = '';
  }

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    if (recipeInvalid) return;
    if (unusualRatio) {
      ratioConfirmationOpen = true;
      return;
    }
    await saveBrew(false);
  }

  async function saveBrew(confirmUnusualRatio: boolean) {
    if (saving || form.grinder_setting === null) return;
    const brewForm: BrewInput = { ...form, grinder_setting: form.grinder_setting };
    ratioConfirmationOpen = false;
    saving = true;
    error = '';
    const creatingBrew = !editId && !correctionId;
    const idempotencyKey = creatingBrew ? brewCreationKey || crypto.randomUUID() : '';
    if (creatingBrew) brewCreationKey = idempotencyKey;
    const requestHeaders: Record<string, string> = {};
    if (creatingBrew) requestHeaders['Idempotency-Key'] = idempotencyKey;
    if (confirmUnusualRatio) requestHeaders['X-Confirm-Unusual-Ratio'] = 'true';
    try {
      const path = correctionId
        ? `/brews/${correctionId}/correction`
        : editId
          ? `/brews/${editId}`
          : '/brews';
      const brew = await api<Brew>(path, {
        method: editId || correctionId ? 'PUT' : 'POST',
        headers: requestHeaders,
        body: jsonBody(
          correctionId
            ? {
                ...brewForm,
                operator_id:
                  correctionOperatorId !== originalOperatorId ? correctionOperatorId : undefined,
                total_brew_time_s: correctionMinutes * 60 + correctionSeconds
              }
            : editId
              ? { ...brewForm, revision: sourceRevision }
              : brewForm
        )
      });
      await refreshBrewStatusAfterMutation().catch(() => undefined);
      await goto(`/brews/${brew.id}`);
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not save the brew.';
      if (!editId && !correctionId && caught instanceof ApiError && caught.status === 409) {
        if (caught.code === 'coffee_unavailable') {
          coffees = await api<Coffee[]>('/coffees');
          if (!coffees.some((coffee) => coffee.id === form.coffee_id)) {
            form.coffee_id = coffees[0]?.id || 0;
            await loadHistory();
          }
        } else if (caught.code === 'brew_capacity_reached') {
          active = await api<ActiveBrews>('/brews/active');
        }
      }
    } finally {
      saving = false;
    }
  }

  async function clone(source: Brew) {
    error = '';
    try {
      const brew = await api<Brew>(`/brews/${source.id}/clone`, {
        method: 'POST',
        body: jsonBody({})
      });
      await refreshBrewStatusAfterMutation().catch(() => undefined);
      await goto(`/brews/${brew.id}`);
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not repeat this brew.';
    }
  }

  async function join(source: BrewActivityItem) {
    if (joiningBrewId !== null) return;
    joiningBrewId = source.id;
    try {
      await api<Brew>(`/brews/${source.id}/join`, { method: 'POST', body: jsonBody({}) });
      await goto(`/brews/${source.id}`);
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not join this brew.';
    } finally {
      joiningBrewId = null;
    }
  }
</script>

<svelte:head
  ><title
    >{correctionId ? 'Correct brew' : editId ? 'Edit brew' : 'New brew'} · Filter Coffee Club</title
  ></svelte:head
>

<p class="eyebrow">{correctionId ? 'Administrator correction' : 'Operator console'}</p>
<h1>
  {correctionId
    ? 'Correct the recorded brew.'
    : editId
      ? 'Adjust the recipe.'
      : 'Prepare the next brew.'}
</h1>
<p class="lede">
  {correctionId
    ? 'Update an incorrect measurement while preserving the brew, invitation, and ratings.'
    : 'Start from club experience, an FCC preset, or your own settings. Everything remains editable.'}
</p>

{#if !ready}
  <div class="empty section">Loading the equipment rack…</div>
{:else if active && !active.can_start && !editId && !correctionId}
  <section class="panel section capacity-panel">
    <p class="eyebrow">Brew capacity reached</p>
    <h2>{active.active_count} of {active.max_active_brews} brews are active.</h2>
    <p class="muted">Join one of them, or wait until an active brew is finished or cancelled.</p>
    <div class="active-list">
      {#each active.brews as brew}
        <article>
          <div>
            <strong>{brew.coffee_roaster} · {brew.coffee_name}</strong>
            <small>{brew.operators.map((operator) => operator.display_name).join(', ')}</small>
          </div>
          <button class="secondary" onclick={() => join(brew)} disabled={joiningBrewId !== null}
            >{joiningBrewId === brew.id ? 'Joining…' : 'Join brew'}</button
          >
        </article>
      {/each}
    </div>
    {#if error}<p class="error" role="alert">{error}</p>{/if}
    <div class="actions">
      <button class="secondary" onclick={refreshCapacity} disabled={checkingCapacity}
        >{checkingCapacity ? 'Checking…' : 'Check again'}</button
      >
      <a class="button secondary" href="/">Return home</a>
    </div>
  </section>
{:else if $deviceModeStore === 'kiosk' && (!coffees.length || !grinders.length)}
  <section class="panel section kiosk-missing-data">
    <p class="eyebrow">Personal device required</p>
    <h2>Make a coffee and grinder available first.</h2>
    <p class="muted">
      Add or restore at least one coffee and register a grinder from a phone or computer, then
      return to this shared display.
    </p>
    <a class="button secondary" href="/">Return home</a>
  </section>
{:else}
  <form id="coffee-form" onsubmit={addCoffee}></form>
  <div class="split section">
    <form class="panel" onsubmit={submit}>
      <div class="field-row">
        <label>
          Coffee
          <select bind:value={form.coffee_id} onchange={loadHistory} required>
            {#each coffees as coffee}<option value={coffee.id}
                >{coffee.roaster} · {coffee.name}{coffee.available
                  ? ''
                  : ' · unavailable (current brew)'}</option
              >{/each}
          </select>
        </label>
        {#if $deviceModeStore !== 'kiosk'}
          <button
            class="secondary compact"
            type="button"
            aria-expanded={showCoffeeForm}
            onclick={toggleCoffeeForm}>+ Coffee</button
          >
        {/if}
      </div>
      {#if selectedCoffee && !selectedCoffee.available}
        <p class="warning" role="status">
          This bag is no longer available for new brews, but it can remain on this existing brew.
        </p>
      {/if}
      {#if showCoffeeForm && $deviceModeStore !== 'kiosk'}
        <div class="inline-form">
          <h3>Add this bag</h3>
          <div class="field-grid">
            <label
              >Roaster / brand<input
                bind:value={newCoffee.roaster}
                required
                form="coffee-form"
              /></label
            >
            <label
              >Coffee name<input bind:value={newCoffee.name} required form="coffee-form" /></label
            >
            <label>Country<input bind:value={newCoffee.country} form="coffee-form" /></label>
            <label
              >Purchased from<input
                bind:value={newCoffee.purchase_location}
                maxlength="160"
                placeholder="Shop, city, or country"
                form="coffee-form"
              /></label
            >
            <label>Process<input bind:value={newCoffee.process} form="coffee-form" /></label>
          </div>
          <CoffeeColorPicker
            bind:value={newCoffee.chart_color}
            coffees={coffeeColorPeers}
            surfaceColor={$appSettingsStore?.color_surface ?? '#FFFDFC'}
          />
          {#if coffeeError}<p class="error" role="alert">{coffeeError}</p>{/if}
          <button class="secondary" type="submit" form="coffee-form" disabled={addingCoffee}
            >{addingCoffee ? 'Saving coffee…' : 'Save coffee'}</button
          >
        </div>
      {/if}

      <div class="grinder-choice">
        <label>
          Choose a grinder
          <select bind:value={form.grinder_id} onchange={changeGrinder} required>
            {#if grinders.length !== 1}
              <option value={0} disabled>Choose a grinder</option>
            {/if}
            {#each grinders as item}
              <option value={item.id}
                >{item.manufacturer}
                {item.model}{item.archived ? ' · archived (recorded)' : ''}</option
              >
            {/each}
          </select>
        </label>
        <p class="muted">
          Preset ranges update for the selected grinder. For click grinders, saved settings remain
          total clicks.
        </p>
      </div>

      <fieldset>
        <legend>FCC starting point</legend>
        <div class="preset-grid">
          {#each visiblePresets as preset}
            <button
              class:chosen={form.source_preset_id === preset.id}
              class="preset"
              type="button"
              disabled={!preset.active || !form.grinder_id}
              onclick={() => applyPreset(preset)}
            >
              <strong>{preset.name}</strong><span
                >1:{preset.ratio} · {preset.temperature_min_c}–{preset.temperature_max_c}°C</span
              >
              <span class:no-guidance={Boolean(grinder && !rangeForPreset(preset))}
                >{presetGrindLabel(preset)}</span
              >
              {#if !preset.active}<span class="preset-state">Inactive starting point</span>{/if}
              {#if form.source_preset_id === preset.id}
                <span class:customized={presetDeviations.length > 0} class="preset-state">
                  {presetDeviations.length
                    ? `Customized · ${presetDeviations.join(', ')}`
                    : selectedPresetGrinderRange
                      ? 'Matches preset'
                      : 'Matches guided fields · grinder not covered'}
                </span>
              {/if}
            </button>
          {/each}
        </div>
      </fieldset>

      <div class="calculator">
        <NumberStepper
          label="Servings"
          bind:value={form.servings}
          onchange={rescaleServings}
          min={1}
          max={30}
          step={1}
          inputmode="numeric"
        />
        <NumberStepper
          label="Target ratio"
          bind:value={form.target_ratio}
          onchange={changeRatio}
          min={0.1}
          max={5000}
          step={0.1}
        />
        <button class="secondary" type="button" onclick={useWaterBasis}>120 g water/person</button>
        <button class="secondary" type="button" onclick={useCoffeeBasis}>8 g coffee/person</button>
        <p class="calculator-hint" role="status">
          Changing servings scales the whole batch. Ratio changes preserve
          <strong>{recipeState.basis === 'coffee' ? 'coffee dose' : 'total water'}</strong>.
        </p>
      </div>

      <div class="big-inputs">
        <NumberStepper
          label="Total coffee dose"
          bind:value={form.dose_g}
          onchange={changeDose}
          min={1}
          max={500}
          step={0.1}
          unit="g"
        />
        <div class="ratio-readout"><span>live ratio</span><strong>1:{ratio}</strong></div>
        <NumberStepper
          label="Total water"
          bind:value={form.water_g}
          onchange={changeWater}
          min={1}
          max={5000}
          step={1}
          unit="g"
          inputmode="numeric"
        />
      </div>
      {#if amountError}<p class="error consistency-message" role="alert">{amountError}</p>{/if}
      {#if unusualRatio}
        <p class="warning ratio-warning" role="alert">
          A 1:{ratio} ratio is outside the normal 1:10–1:25 range. Check that coffee and water are totals
          for the whole batch.
        </p>
      {/if}

      <div class="field-grid">
        <NumberStepper
          label="Temperature"
          bind:value={form.temperature_c}
          min={50}
          max={100}
          step={1}
          unit="°C"
          inputmode="numeric"
        />
        <NumberStepper
          label="Target flow"
          bind:value={form.target_flow_g_s}
          min={0.1}
          max={50}
          step={0.1}
          unit="g/s"
          nullable
        />
        <div>
          {#if grinder}
            <NumberStepper
              label="Grinder setting"
              bind:value={form.grinder_setting}
              onchange={confirmGrinderSetting}
              min={0}
              max={1000}
              step={clickGrinder ? 1 : grinder.setting_step}
              unit={grinder.setting_unit}
              inputmode={clickGrinder ? 'numeric' : 'decimal'}
              nullable
            />
            {#if form.grinder_setting !== null && grinderDefinition?.clicks_per_rotation}
              <span class="setting-helper"
                >{formatGrinderSetting(form.grinder_setting, grinder, grinderDefinition)}</span
              >
            {/if}
            {#if grinderSettingNeedsReview}<span class="warning" role="status"
                >{selectedPreset
                  ? 'This preset has no guidance for the selected grinder. Enter a setting manually.'
                  : 'Enter a grinder setting manually.'}</span
              >{/if}{#if grinderSettingInvalid}<span class="error" role="alert"
                >Click-based grinder settings must be whole numbers.</span
              >{:else if settingWarning}<span class="warning"
                >Outside this grinder’s usual range; it will still be saved.</span
              >{/if}
          {:else}
            <div class="setting-placeholder">
              <strong>Grinder setting</strong>
              <span>Choose a grinder first.</span>
            </div>
          {/if}
        </div>
        <label
          >Dripper<select bind:value={form.dripper_id}
            ><option value={null}>Not recorded</option>{#each drippers as item}<option
                value={item.id}>{item.manufacturer ?? ''} {item.model}</option
              >{/each}</select
          ></label
        >
        <label
          >Filter<select bind:value={form.filter_id}
            ><option value={null}>Not recorded</option>{#each filters as item}<option
                value={item.id}>{item.name}</option
              >{/each}</select
          ></label
        >
      </div>

      <details>
        <summary>More pour details</summary>
        <div class="field-grid">
          <div>
            <NumberStepper
              label="Bloom water"
              bind:value={form.bloom_water_g}
              min={0}
              max={form.water_g}
              step={1}
              unit="g"
              inputmode="numeric"
              nullable
            />
            {#if bloomWaterInvalid}<span class="error" role="alert">
                Bloom water must not exceed total water.
              </span>{/if}
          </div>
          <NumberStepper
            label="Bloom time"
            bind:value={form.bloom_time_s}
            min={0}
            step={1}
            unit="s"
            inputmode="numeric"
            nullable
          />
          <NumberStepper
            label="Pour count"
            bind:value={form.pour_count}
            min={1}
            max={30}
            inputmode="numeric"
            nullable
          />
          {#if $deviceModeStore === 'kiosk'}
            {#if form.technique_note}<div class="readonly-note">
                <span>Technique note</span>
                <p>{form.technique_note}</p>
              </div>{/if}
          {:else}
            <label
              >Technique note<textarea bind:value={form.technique_note} maxlength="1000"
              ></textarea></label
            >
          {/if}
        </div>
      </details>
      {#if correctionId}
        <fieldset>
          <legend>Recorded result</legend>
          <label>
            Operator
            <select bind:value={correctionOperatorId} required>
              {#if !operators.some((operator) => operator.id === originalOperatorId)}
                <option value={originalOperatorId}
                  >{originalOperatorName} (current; inactive)</option
                >
              {/if}
              {#each operators as operator}
                <option value={operator.id}>{operator.display_name}</option>
              {/each}
            </select>
          </label>
          <div class="field-grid correction-time">
            <label
              >Minutes<input
                type="number"
                bind:value={correctionMinutes}
                min="0"
                max="59"
                inputmode="numeric"
              /></label
            >
            <label
              >Seconds<input
                type="number"
                bind:value={correctionSeconds}
                min="0"
                max="59"
                inputmode="numeric"
              /></label
            >
          </div>
        </fieldset>
      {/if}
      {#if error}<p class="error" role="alert">{error}</p>{/if}
      {#if editorChangedExternally}
        <p class="warning" role="alert">
          This brew changed on another device. Reload before saving to avoid overwriting newer
          settings.
        </p>
      {/if}
      <div class="actions">
        <button
          class="primary"
          disabled={saving ||
            !form.coffee_id ||
            !form.grinder_id ||
            recipeInvalid ||
            Boolean(correctionId && correctionMinutes * 60 + correctionSeconds <= 0)}
          >{saving
            ? 'Saving…'
            : correctionId
              ? 'Save correction'
              : editId
                ? 'Save and return to brew mode'
                : 'Save and open brew mode'}</button
        ><a class="button secondary" href={correctionId ? `/brews/${correctionId}` : '/'}>Cancel</a>
      </div>
    </form>

    <aside class="stack">
      <section class="card">
        <p class="eyebrow">Live recipe</p>
        <div class="metric">
          <strong>{form.dose_g} → {form.water_g}</strong><span>grams coffee → water</span>
        </div>
        <p class="muted">
          1:{ratio} · {form.temperature_c} °C ·
          {form.grinder_setting === null
            ? 'grind not set'
            : grinder
              ? formatGrinderSetting(form.grinder_setting, grinder, grinderDefinition)
              : form.grinder_setting}
        </p>
        {#if selectedPreset}
          <div class="preset-conformance" role="status">
            <strong>
              {presetDeviations.length
                ? `Customized from ${selectedPreset.name}`
                : selectedPreset.name}
            </strong>
            {#if presetDeviations.length}<span>Changed: {presetDeviations.join(', ')}</span
              >{:else}<span>Current guided values match the preset.</span>{/if}
            {#if !selectedPresetGrinderRange}<span
                >No guidance for {grinder?.manufacturer} {grinder?.model}.</span
              >{/if}
          </div>
        {/if}
      </section>
      <section class="card">
        <h2>Previous trials</h2>
        {#if history.length === 0}<p class="muted">
            No completed brews for this coffee yet.
          </p>{:else}
          <div class="trial-list">
            {#each history as brew}<article>
                <div>
                  <strong>1:{brew.ratio} · {brew.temperature_c}°</strong><small>
                    {brew.grinder_setting}
                    {brew.grinder_unit} · <ProfileLink
                      profileId={brew.operator_id}
                      displayName={brew.operator_name}
                    /></small
                  >
                </div>
                <button class="secondary" type="button" onclick={() => clone(brew)}>Repeat</button>
              </article>{/each}
          </div>
        {/if}
      </section>
    </aside>
  </div>
{/if}

<ConfirmDialog
  open={ratioConfirmationOpen}
  title={`Save unusual 1:${ratio} ratio?`}
  description={unusualBrewRatioDescription(form.dose_g, form.water_g)}
  confirmLabel={`Save 1:${ratio} anyway`}
  cancelLabel="Review amounts"
  busy={saving}
  onconfirm={() => saveBrew(true)}
  oncancel={() => (ratioConfirmationOpen = false)}
/>

<style>
  .field-row {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 10px;
    align-items: end;
  }
  .compact {
    min-height: 50px;
  }
  .kiosk-missing-data {
    max-width: 720px;
  }
  .capacity-panel {
    max-width: 760px;
  }
  .active-list,
  .active-list article,
  .active-list small {
    display: grid;
  }
  .active-list {
    gap: 8px;
    margin: 20px 0;
  }
  .active-list article {
    grid-template-columns: 1fr auto;
    align-items: center;
    gap: 12px;
    padding: 12px;
    border: 1px solid var(--line);
    border-radius: 12px;
  }
  .active-list small {
    margin-top: 4px;
    color: var(--muted);
  }
  .readonly-note {
    display: grid;
    gap: 7px;
    font-weight: 750;
  }
  .readonly-note p {
    margin: 0;
    padding: 12px 14px;
    border: 1px solid var(--line);
    border-radius: 12px;
    background: var(--surface);
    font-weight: 500;
  }
  .inline-form,
  .calculator {
    padding: 16px;
    border-radius: 16px;
    background: color-mix(in srgb, var(--amber) 10%, var(--surface));
  }
  .grinder-choice {
    display: grid;
    gap: 6px;
    padding: 14px;
    border: 1px solid color-mix(in srgb, var(--cyan) 40%, var(--line));
    border-radius: 14px;
    background: color-mix(in srgb, var(--cyan) 7%, var(--surface));
  }
  .grinder-choice p {
    margin: 0;
    font-size: 0.8rem;
  }
  .preset-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
  }
  .preset {
    min-height: 70px;
    padding: 11px;
    border: 1px solid var(--line);
    border-radius: 12px;
    background: var(--surface);
    color: var(--ink);
    text-align: left;
    cursor: pointer;
  }
  .preset.chosen {
    border-color: var(--cyan);
    background: color-mix(in srgb, var(--cyan) 9%, var(--surface));
  }
  .preset:disabled {
    cursor: default;
    opacity: 1;
  }
  .preset span,
  .preset strong {
    display: block;
  }
  .preset span {
    margin-top: 4px;
    color: var(--muted);
    font-size: 0.76rem;
  }
  .preset .preset-state {
    margin-top: 7px;
    color: var(--cyan);
    font-weight: 750;
  }
  .preset .preset-state.customized {
    color: #8a4a00;
  }
  .preset .no-guidance {
    color: #8a4a00;
  }
  .calculator {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }
  .calculator-hint {
    grid-column: 1 / -1;
    margin: 0;
    color: var(--muted);
    font-size: 0.82rem;
  }
  .calculator-hint strong {
    color: var(--ink);
  }
  .correction-time {
    max-width: 360px;
  }
  .big-inputs {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    gap: 12px;
    align-items: end;
  }
  .ratio-readout {
    display: grid;
    padding-bottom: 8px;
    text-align: center;
  }
  .ratio-readout span {
    color: var(--muted);
    font-size: 0.7rem;
    text-transform: uppercase;
  }
  .ratio-readout strong {
    font-size: 1.4rem;
  }
  .warning {
    color: #8a4a00;
    font-size: 0.78rem;
  }
  .setting-helper {
    display: block;
    margin-top: 5px;
    color: var(--muted);
    font-size: 0.8rem;
  }
  .setting-placeholder {
    display: grid;
    gap: 8px;
    min-height: 78px;
    padding: 12px;
    border: 1px dashed var(--line);
    border-radius: 12px;
    color: var(--muted);
  }
  .ratio-warning {
    margin-top: -8px;
    padding: 10px 12px;
    border: 1px solid color-mix(in srgb, var(--amber) 55%, var(--line));
    border-radius: 12px;
    background: color-mix(in srgb, var(--amber) 10%, var(--surface));
  }
  .consistency-message {
    margin-top: -8px;
  }
  .preset-conformance {
    display: grid;
    gap: 3px;
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid var(--line);
    font-size: 0.8rem;
  }
  .preset-conformance span {
    color: var(--muted);
  }
  .trial-list {
    display: grid;
    gap: 8px;
  }
  .trial-list article {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    padding: 10px 0;
    border-bottom: 1px solid var(--line);
  }
  .trial-list small {
    display: block;
    color: var(--muted);
    margin-top: 3px;
  }
  @media (max-width: 600px) {
    .preset-grid,
    .calculator {
      grid-template-columns: 1fr;
    }
    .big-inputs {
      grid-template-columns: 1fr;
    }
    .ratio-readout {
      text-align: left;
    }
  }
</style>
