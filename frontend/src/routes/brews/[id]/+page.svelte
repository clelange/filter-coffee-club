<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { deviceModeStore, loginPath } from '$lib/device';
  import NumberStepper from '$lib/NumberStepper.svelte';
  import { api, ensureSession, formatTime, jsonBody, logout, sessionStore } from '$lib/api';
  import type { Brew } from '$lib/types';

  let brew: Brew | null = $state(null);
  let error = $state('');
  let finishing = $state(false);
  let finalMinutes = $state(3);
  let finalSeconds = $state(0);
  let actualWater = $state(0);
  let copied = $state(false);
  let statusAction: 'cancel' | 'void' | null = $state(null);
  let changingStatus = $state(false);
  let wakeLock: WakeLockSentinel | null = null;

  const id = $derived(Number($page.params.id));

  onMount(async () => {
    await load();
    const session = await ensureSession();
    if (brew?.status === 'draft') {
      if (!session) {
        await goto(loginPath(`/brews/${id}`));
        return;
      }
      await keepAwake();
    }
  });

  onDestroy(() => wakeLock?.release());

  async function load() {
    try {
      brew = await api<Brew>(`/brews/${id}`);
      actualWater = brew.water_g;
      if (brew.total_brew_time_s) {
        finalMinutes = Math.floor(brew.total_brew_time_s / 60);
        finalSeconds = brew.total_brew_time_s % 60;
      }
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not load this brew.';
    }
  }

  async function keepAwake() {
    try {
      wakeLock = (await navigator.wakeLock?.request('screen')) ?? null;
    } catch {
      wakeLock = null;
    }
  }

  async function finalize() {
    if (!brew) return;
    error = '';
    try {
      brew = await api<Brew>(`/brews/${brew.id}/finalize`, {
        method: 'POST',
        body: jsonBody({
          water_g: actualWater,
          total_brew_time_s: finalMinutes * 60 + finalSeconds
        })
      });
      finishing = false;
      await wakeLock?.release();
      const session = await ensureSession();
      if (session?.device_mode === 'kiosk') await logout();
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not finalize the brew.';
    }
  }

  async function copyLink() {
    if (!brew?.rating_token) return;
    const settings = await api<{ public_base_url: string }>('/settings');
    await navigator.clipboard.writeText(`${settings.public_base_url}/rate/${brew.rating_token}`);
    copied = true;
    setTimeout(() => (copied = false), 1800);
  }

  function rateOnScreenHref(): string {
    if (!brew?.rating_token) return '#';
    const ratingPath = `/rate/${brew.rating_token}`;
    return $sessionStore?.device_mode === 'personal' ? ratingPath : loginPath(ratingPath);
  }

  function canManageDraft(): boolean {
    return Boolean(
      brew &&
      $sessionStore &&
      ($sessionStore.profile.id === brew.operator_id || $sessionStore.profile.role === 'admin')
    );
  }

  async function changeStatus() {
    if (!brew || !statusAction) return;
    const action = statusAction;
    changingStatus = true;
    error = '';
    try {
      brew = await api<Brew>(`/brews/${brew.id}/${action}`, {
        method: 'POST',
        body: jsonBody({})
      });
      statusAction = null;
      await wakeLock?.release();
      if (action === 'cancel') {
        const session = await ensureSession();
        if (session?.device_mode === 'kiosk') await logout();
      }
    } catch (caught) {
      error = caught instanceof Error ? caught.message : `Could not ${action} the brew.`;
    } finally {
      changingStatus = false;
    }
  }
</script>

<svelte:head
  ><title>{brew ? `${brew.coffee_name} · Brew` : 'Brew'} · Filter Coffee Club</title></svelte:head
>

{#if error && !brew}
  <p class="error">{error}</p>
{:else if !brew}
  <div class="empty">Finding the brew…</div>
{:else if brew.status === 'draft'}
  <section class="brew-mode">
    <div class="brew-heading">
      <div>
        <p class="eyebrow">Brew mode · settings locked on screen</p>
        <h1>{brew.coffee_name}</h1>
        <p class="lede">{brew.coffee_roaster} · operator {brew.operator_name}</p>
      </div>
      <span class="status draft">draft #{brew.id}</span>
    </div>
    <div class="recipe-display">
      <article class="hero-metric">
        <strong>{brew.dose_g}<i>g</i></strong><span>coffee dose</span>
      </article>
      <div class="arrow">→</div>
      <article class="hero-metric">
        <strong>{brew.water_g}<i>g</i></strong><span>total water</span>
      </article>
      <article class="recipe-cell"><strong>1:{brew.ratio}</strong><span>ratio</span></article>
      <article class="recipe-cell">
        <strong>{brew.temperature_c} °C</strong><span>water</span>
      </article>
      <article class="recipe-cell">
        <strong>{brew.grinder_setting}</strong><span>{brew.grinder_name} · {brew.grinder_unit}</span
        >
      </article>
      <article class="recipe-cell">
        <strong>{brew.target_flow_g_s ?? '—'} {brew.target_flow_g_s ? 'g/s' : ''}</strong><span
          >target pour rate</span
        >
      </article>
      <article class="recipe-cell">
        <strong>{brew.servings}</strong><span>serving{brew.servings === 1 ? '' : 's'}</span>
      </article>
      <article class="recipe-cell">
        <strong>{brew.dripper_name ?? '—'}</strong><span
          >{brew.filter_name ?? 'dripper / filter'}</span
        >
      </article>
    </div>
    {#if brew.bloom_water_g || brew.bloom_time_s || brew.pour_count}
      <div class="pour-strip">
        {#if brew.bloom_water_g}<span><b>{brew.bloom_water_g} g</b> bloom water</span>{/if}
        {#if brew.bloom_time_s}<span><b>{brew.bloom_time_s} s</b> bloom</span>{/if}
        {#if brew.pour_count}<span><b>{brew.pour_count}</b> pours</span>{/if}
      </div>
    {/if}
    {#if brew.technique_note}<p class="technique">{brew.technique_note}</p>{/if}
    {#if error}<p class="error">{error}</p>{/if}
    <div class="actions brew-actions">
      {#if canManageDraft()}
        <button class="danger" onclick={() => (statusAction = 'cancel')}>Cancel brew</button>
        <a class="button secondary" href={`/brews/new?edit=${brew.id}`}>Edit recipe</a>
        <button class="primary" onclick={() => (finishing = true)}>Finish brew</button>
      {/if}
    </div>
  </section>
  {#if finishing}
    <div class="modal-backdrop" role="presentation">
      <div
        class="modal panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="finish-title"
        tabindex="-1"
      >
        <div class="modal-heading">
          <p class="eyebrow">Scale result</p>
          <h2 id="finish-title">Finish this brew</h2>
          <p class="muted">Enter the final TIMEMORE time and confirm the actual water weight.</p>
        </div>
        <div class="field-grid">
          <NumberStepper
            label="Minutes"
            bind:value={finalMinutes}
            min={0}
            max={59}
            inputmode="numeric"
          />
          <NumberStepper
            label="Seconds"
            bind:value={finalSeconds}
            min={0}
            max={59}
            inputmode="numeric"
          />
          <NumberStepper
            label="Actual water"
            bind:value={actualWater}
            min={1}
            max={5000}
            unit="g"
            inputmode="numeric"
          />
        </div>
        <div class="actions">
          <button
            class="primary"
            onclick={finalize}
            disabled={finalMinutes * 60 + finalSeconds <= 0}>Finalize and invite tasters</button
          ><button class="secondary" onclick={() => (finishing = false)}>Back</button>
        </div>
      </div>
    </div>
  {/if}
{:else if brew.status === 'completed'}
  <section class="invitation">
    <div class="invite-copy">
      <p class="eyebrow">Brew #{brew.id} is ready</p>
      <h1>Taste. Scan. Rate.</h1>
      <p class="lede">
        <strong>{brew.coffee_roaster} · {brew.coffee_name}</strong><br />Brewed by {brew.operator_name}
        in {formatTime(brew.total_brew_time_s)}.
      </p>
      <div class="brew-summary">
        <span>1:{brew.ratio}</span><span>{brew.grinder_setting} {brew.grinder_unit}</span><span
          >{brew.temperature_c} °C</span
        >
      </div>
      <div class="actions">
        <a class="button" href={rateOnScreenHref()}>Rate on this screen</a>
        <button class="secondary" onclick={copyLink}>{copied ? 'Copied!' : 'Copy link'}</button>
        {#if $sessionStore?.profile.role === 'admin' && $deviceModeStore !== 'kiosk'}
          <a class="button secondary" href={`/brews/new?correct=${brew.id}`}>Correct brew</a>
          <button class="danger" onclick={() => (statusAction = 'void')}>Void brew</button>
        {/if}
      </div>
      <p class="hint">
        The QR opens this brew only. Each taster still signs in with their own PIN.
      </p>
    </div>
    <div class="qr-card">
      <img
        src={`/api/v1/brews/${brew.id}/qr.svg`}
        alt={`QR code to rate ${brew.coffee_name}`}
      /><strong>Open the camera on your phone</strong><span
        >Personal sessions stay signed in for 3.5 days.</span
      >
    </div>
  </section>
{:else}
  <div class="panel">
    <p class="eyebrow">Brew #{brew.id}</p>
    <h1>This brew is {brew.status}.</h1>
    <p class="lede">It is kept in the log but cannot be rated.</p>
    <a class="button secondary" href="/">Return home</a>
  </div>
{/if}

{#if statusAction && brew}
  <div class="modal-backdrop" role="presentation">
    <div
      class="modal panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby="status-title"
      tabindex="-1"
    >
      <div class="modal-heading">
        <p class="eyebrow">Keep the record</p>
        <h2 id="status-title">
          {statusAction === 'cancel' ? 'Cancel this draft?' : 'Void this completed brew?'}
        </h2>
        <p class="muted">
          {statusAction === 'cancel'
            ? 'The brew will remain in the log as cancelled and cannot be completed or rated.'
            : 'The brew and its ratings will remain stored, but its rating link will close and it will be excluded from analytics.'}
        </p>
      </div>
      {#if error}<p class="error" role="alert">{error}</p>{/if}
      <div class="actions">
        <button class="danger" onclick={changeStatus} disabled={changingStatus}>
          {changingStatus
            ? 'Saving…'
            : statusAction === 'cancel'
              ? 'Cancel draft'
              : 'Void completed brew'}
        </button>
        <button class="secondary" onclick={() => (statusAction = null)} disabled={changingStatus}
          >Keep brew</button
        >
      </div>
    </div>
  </div>
{/if}

<style>
  .brew-mode {
    min-height: 68vh;
    display: grid;
    align-content: center;
    gap: 24px;
  }
  .brew-heading {
    display: flex;
    justify-content: space-between;
    align-items: start;
    gap: 20px;
  }
  .brew-heading h1 {
    margin-bottom: 6px;
  }
  .recipe-display {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 12px;
  }
  .hero-metric,
  .recipe-cell {
    display: grid;
    align-content: center;
    min-height: 130px;
    padding: 20px;
    border: 1px solid var(--line);
    border-radius: 22px;
    background: var(--surface);
    box-shadow: var(--shadow);
  }
  .hero-metric {
    min-height: 190px;
    grid-column: span 2;
    row-gap: 8px;
    text-align: center;
  }
  .hero-metric strong {
    font:
      700 clamp(3.8rem, 10vw, 8rem)/0.9 Georgia,
      serif;
  }
  .hero-metric i {
    font: 700 1.2rem system-ui;
    font-style: normal;
  }
  .hero-metric span,
  .recipe-cell span {
    color: var(--muted);
    font-size: 0.75rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .arrow {
    display: none;
  }
  .recipe-cell strong {
    font-size: clamp(1.3rem, 3vw, 2rem);
    margin-bottom: 5px;
  }
  .pour-strip {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
  }
  .pour-strip span {
    padding: 10px 16px;
    border-radius: 999px;
    background: color-mix(in srgb, var(--cyan) 10%, var(--surface));
  }
  .pour-strip b {
    margin-right: 5px;
  }
  .technique {
    padding: 15px;
    border-left: 4px solid var(--amber);
    background: var(--surface);
  }
  .brew-actions {
    justify-content: flex-end;
  }
  .brew-actions .button,
  .brew-actions button {
    min-width: 180px;
  }
  .modal-backdrop {
    position: fixed;
    z-index: 50;
    inset: 0;
    display: grid;
    place-items: center;
    overflow-y: auto;
    padding: 16px;
    background: rgb(20 15 13 / 64%);
  }
  .modal {
    display: grid;
    gap: 20px;
    width: min(600px, 100%);
    max-height: calc(100dvh - 32px);
    overflow-y: auto;
    background: var(--surface);
  }
  .modal-heading {
    display: grid;
    gap: 8px;
  }
  .modal-heading > * {
    margin: 0;
  }
  .modal .actions {
    margin-top: 0;
  }
  .invitation {
    display: grid;
    grid-template-columns: 1.1fr 0.8fr;
    gap: clamp(30px, 8vw, 100px);
    align-items: center;
    min-height: 68vh;
  }
  .brew-summary {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin: 24px 0;
  }
  .brew-summary span {
    padding: 10px 14px;
    border-radius: 999px;
    background: var(--surface);
    font-weight: 850;
  }
  .qr-card {
    display: grid;
    justify-items: center;
    gap: 12px;
    padding: 24px;
    border: 1px solid var(--line);
    border-radius: 30px;
    background: var(--surface);
    box-shadow: var(--shadow);
    text-align: center;
  }
  .qr-card img {
    width: min(100%, 360px);
    aspect-ratio: 1;
  }
  .qr-card span {
    color: var(--muted);
    font-size: 0.85rem;
  }
  @media (max-height: 650px) {
    .modal {
      gap: 12px;
      padding: 20px;
    }
    .modal-heading {
      gap: 4px;
    }
    .modal .field-grid {
      row-gap: 10px;
    }
  }
  @media (min-width: 900px) and (max-height: 650px) {
    .brew-mode {
      min-height: 0;
      align-content: start;
      gap: 12px;
    }
    .brew-heading h1 {
      font-size: 2.7rem;
    }
    .brew-heading .lede {
      margin-bottom: 0;
    }
    .recipe-display {
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 10px;
    }
    .hero-metric {
      grid-column: span 3;
      min-height: 122px;
      padding: 14px;
    }
    .hero-metric strong {
      font-size: 4.8rem;
    }
    .recipe-cell {
      min-height: 98px;
      padding: 13px;
    }
    .recipe-cell strong {
      font-size: 1.35rem;
    }
    .brew-actions {
      margin-top: 0;
    }
    .invitation {
      min-height: 0;
    }
    .qr-card {
      padding: 14px;
      gap: 6px;
    }
    .qr-card img {
      width: min(100%, 330px);
    }
  }
  @media (max-width: 760px) {
    .recipe-display {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .hero-metric {
      grid-column: span 1;
      min-height: 150px;
    }
    .recipe-cell {
      min-height: 110px;
    }
    .invitation {
      grid-template-columns: 1fr;
    }
    .qr-card {
      order: -1;
    }
    .brew-heading {
      display: block;
    }
  }
</style>
