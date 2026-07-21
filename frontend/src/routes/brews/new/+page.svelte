<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { deviceModeStore, loginPath } from '$lib/device';
  import { api, ensureSession, jsonBody } from '$lib/api';
  import NumberStepper from '$lib/NumberStepper.svelte';
  import type {
    Brew,
    BrewFilter,
    BrewInput,
    Coffee,
    Dripper,
    Grinder,
    Preset,
    Profile
  } from '$lib/types';

  let coffees: Coffee[] = $state([]);
  let grinders: Grinder[] = $state([]);
  let drippers: Dripper[] = $state([]);
  let filters: BrewFilter[] = $state([]);
  let presets: Preset[] = $state([]);
  let operators: Profile[] = $state([]);
  let history: Brew[] = $state([]);
  let editId = $state<number | null>(null);
  let correctionId = $state<number | null>(null);
  let correctionMinutes = $state(3);
  let correctionSeconds = $state(0);
  let correctionOperatorId = $state(0);
  let originalOperatorId = $state(0);
  let originalOperatorName = $state('');
  let selectedRatio = $state(16);
  let showCoffeeForm = $state(false);
  let coffeeError = $state('');
  let addingCoffee = $state(false);
  let error = $state('');
  let saving = $state(false);
  let ready = $state(false);
  let newCoffee = $state({ roaster: '', name: '', country: '', process: '', roast_level: '' });
  let form: BrewInput = $state({
    coffee_id: 0,
    grinder_id: 0,
    dripper_id: null,
    filter_id: null,
    source_preset_id: null,
    dose_g: 8,
    water_g: 128,
    temperature_c: 94,
    grinder_setting: 30,
    servings: 1,
    target_flow_g_s: 4.5,
    bloom_water_g: null,
    bloom_time_s: null,
    pour_count: null,
    technique_note: null
  });

  const ratio = $derived(form.dose_g ? Math.round((form.water_g / form.dose_g) * 10) / 10 : 0);
  const grinder = $derived(grinders.find((item) => item.id === Number(form.grinder_id)));
  const clickGrinder = $derived(isClickGrinder(grinder));
  const settingWarning = $derived(
    grinder &&
      ((grinder.soft_min !== null && form.grinder_setting < grinder.soft_min) ||
        (grinder.soft_max !== null && form.grinder_setting > grinder.soft_max))
  );

  function isClickGrinder(item: Grinder | undefined): boolean {
    return ['click', 'clicks'].includes(item?.setting_unit.trim().toLowerCase() ?? '');
  }

  onMount(async () => {
    const session = await ensureSession();
    if (!session) {
      await goto(loginPath($page.url.pathname + $page.url.search));
      return;
    }
    correctionId = Number($page.url.searchParams.get('correct')) || null;
    if (correctionId) {
      if ($deviceModeStore === 'kiosk') {
        await goto(`/brews/${correctionId}`);
        return;
      }
    }
    try {
      [coffees, grinders, drippers, filters, presets, operators] = await Promise.all([
        api<Coffee[]>('/coffees'),
        api<Grinder[]>('/grinders'),
        api<Dripper[]>('/drippers'),
        api<BrewFilter[]>('/filters'),
        api<Preset[]>('/presets'),
        correctionId ? api<Profile[]>('/auth/profiles') : Promise.resolve([])
      ]);
      form.coffee_id = Number($page.url.searchParams.get('coffee')) || coffees[0]?.id || 0;
      form.grinder_id = grinders[0]?.id ?? 0;
      editId = Number($page.url.searchParams.get('edit')) || null;
      const repeatId = Number($page.url.searchParams.get('repeat')) || null;
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
        copyBrew(source);
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
      ready = true;
    }
  });

  function copyBrew(source: Brew) {
    form = {
      coffee_id: source.coffee_id,
      grinder_id: source.grinder_id,
      dripper_id: source.dripper_id,
      filter_id: source.filter_id,
      source_preset_id: source.source_preset_id,
      dose_g: source.dose_g,
      water_g: source.water_g,
      temperature_c: source.temperature_c,
      grinder_setting: source.grinder_setting,
      servings: source.servings,
      target_flow_g_s: source.target_flow_g_s,
      bloom_water_g: source.bloom_water_g,
      bloom_time_s: source.bloom_time_s,
      pour_count: source.pour_count,
      technique_note: source.technique_note
    };
    selectedRatio = Math.round(source.ratio * 10) / 10;
  }

  async function loadHistory() {
    history = form.coffee_id
      ? await api<Brew[]>(`/brews?coffee_id=${form.coffee_id}&status=completed&limit=12`)
      : [];
  }

  function applyPreset(preset: Preset) {
    form.source_preset_id = preset.id;
    selectedRatio = preset.ratio;
    form.temperature_c = Math.round((preset.temperature_min_c + preset.temperature_max_c) / 2);
    const range = preset.grinder_ranges.find((item) => item.grinder_id === Number(form.grinder_id));
    if (range) {
      const midpoint = (range.setting_min + range.setting_max) / 2;
      form.grinder_setting = clickGrinder ? Math.round(midpoint) : Math.round(midpoint * 10) / 10;
    }
    useCoffeeBasis();
  }

  function useWaterBasis() {
    form.water_g = form.servings * 120;
    form.dose_g = Math.round((form.water_g / selectedRatio) * 10) / 10;
  }

  function useCoffeeBasis() {
    form.dose_g = form.servings * 8;
    form.water_g = Math.round(form.dose_g * selectedRatio);
  }

  async function addCoffee(event: SubmitEvent) {
    event.preventDefault();
    addingCoffee = true;
    coffeeError = '';
    try {
      const coffee = await api<Coffee>('/coffees', {
        method: 'POST',
        body: jsonBody({
          ...newCoffee,
          country: newCoffee.country || null,
          process: newCoffee.process || null,
          roast_level: newCoffee.roast_level || null
        })
      });
      coffees = [...coffees, coffee];
      form.coffee_id = coffee.id;
      newCoffee = { roaster: '', name: '', country: '', process: '', roast_level: '' };
      showCoffeeForm = false;
      await loadHistory();
    } catch (caught) {
      coffeeError = caught instanceof Error ? caught.message : 'Could not add this coffee.';
    } finally {
      addingCoffee = false;
    }
  }

  function toggleCoffeeForm() {
    showCoffeeForm = !showCoffeeForm;
    if (showCoffeeForm) coffeeError = '';
  }

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    saving = true;
    error = '';
    try {
      const path = correctionId
        ? `/brews/${correctionId}/correction`
        : editId
          ? `/brews/${editId}`
          : '/brews';
      const brew = await api<Brew>(path, {
        method: editId || correctionId ? 'PUT' : 'POST',
        body: jsonBody(
          correctionId
            ? {
                ...form,
                operator_id:
                  correctionOperatorId !== originalOperatorId ? correctionOperatorId : undefined,
                total_brew_time_s: correctionMinutes * 60 + correctionSeconds
              }
            : form
        )
      });
      await goto(`/brews/${brew.id}`);
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not save the brew.';
    } finally {
      saving = false;
    }
  }

  async function clone(source: Brew) {
    const brew = await api<Brew>(`/brews/${source.id}/clone`, {
      method: 'POST',
      body: jsonBody({})
    });
    await goto(`/brews/${brew.id}`);
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
{:else if $deviceModeStore === 'kiosk' && (!coffees.length || !grinders.length)}
  <section class="panel section kiosk-missing-data">
    <p class="eyebrow">Personal device required</p>
    <h2>Register the brewing setup first.</h2>
    <p class="muted">
      Add at least one coffee and grinder from a phone or computer, then return to this shared
      display.
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
                >{coffee.roaster} · {coffee.name}</option
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
            <label>Process<input bind:value={newCoffee.process} form="coffee-form" /></label>
          </div>
          {#if coffeeError}<p class="error" role="alert">{coffeeError}</p>{/if}
          <button class="secondary" type="submit" form="coffee-form" disabled={addingCoffee}
            >{addingCoffee ? 'Saving coffee…' : 'Save coffee'}</button
          >
        </div>
      {/if}

      <fieldset>
        <legend>FCC starting point</legend>
        <div class="preset-grid">
          {#each presets as preset}
            <button
              class:chosen={form.source_preset_id === preset.id}
              class="preset"
              type="button"
              onclick={() => applyPreset(preset)}
            >
              <strong>{preset.name}</strong><span
                >1:{preset.ratio} · {preset.temperature_min_c}–{preset.temperature_max_c}°C</span
              >
            </button>
          {/each}
        </div>
      </fieldset>

      <div class="calculator">
        <NumberStepper
          label="Servings"
          bind:value={form.servings}
          min={1}
          max={30}
          step={1}
          inputmode="numeric"
        />
        <NumberStepper
          label="Target ratio"
          bind:value={selectedRatio}
          min={10}
          max={25}
          step={0.1}
        />
        <button class="secondary" type="button" onclick={useWaterBasis}>120 g water/person</button>
        <button class="secondary" type="button" onclick={useCoffeeBasis}>8 g coffee/person</button>
      </div>

      <div class="big-inputs">
        <NumberStepper
          label="Coffee dose"
          bind:value={form.dose_g}
          min={1}
          max={500}
          step={0.1}
          unit="g"
        />
        <div class="ratio-readout"><span>live ratio</span><strong>1:{ratio}</strong></div>
        <NumberStepper
          label="Total water"
          bind:value={form.water_g}
          min={1}
          max={5000}
          step={1}
          unit="g"
          inputmode="numeric"
        />
      </div>

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
        <label
          >Grinder<select bind:value={form.grinder_id}
            >{#each grinders as item}<option value={item.id}
                >{item.manufacturer} {item.model}</option
              >{/each}</select
          ></label
        >
        <div>
          <NumberStepper
            label="Grinder setting"
            bind:value={form.grinder_setting}
            min={0}
            max={1000}
            step={clickGrinder ? 1 : (grinder?.setting_step ?? 1)}
            unit={grinder?.setting_unit ?? 'setting'}
            inputmode={clickGrinder ? 'numeric' : 'decimal'}
          />{#if settingWarning}<span class="warning"
              >Outside this grinder’s usual range; it will still be saved.</span
            >{/if}
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
          <NumberStepper
            label="Bloom water"
            bind:value={form.bloom_water_g}
            min={0}
            step={1}
            unit="g"
            inputmode="numeric"
            nullable
          />
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
      <div class="actions">
        <button
          class="primary"
          disabled={saving ||
            !form.coffee_id ||
            !form.grinder_id ||
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
          1:{ratio} · {form.temperature_c} °C · {form.grinder_setting}
          {grinder?.setting_unit}
        </p>
      </section>
      <section class="card">
        <h2>Previous trials</h2>
        {#if history.length === 0}<p class="muted">
            No completed brews for this coffee yet.
          </p>{:else}
          <div class="trial-list">
            {#each history as brew}<article>
                <div>
                  <strong>1:{brew.ratio} · {brew.temperature_c}°</strong><small
                    >{brew.grinder_setting} {brew.grinder_unit} · {brew.operator_name}</small
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
  .preset span,
  .preset strong {
    display: block;
  }
  .preset span {
    margin-top: 4px;
    color: var(--muted);
    font-size: 0.76rem;
  }
  .calculator {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
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
