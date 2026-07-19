<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import PinPad from '$lib/PinPad.svelte';
  import { deviceModeStore, loginPath } from '$lib/device';
  import { api, ensureSession, jsonBody, logout } from '$lib/api';

  let currentPin = $state('');
  let newPin = $state('');
  let confirmPin = $state('');
  let required = $state(false);
  let ready = $state(false);
  let saving = $state(false);
  let message = $state('');
  let error = $state('');
  let kioskStep: 'current' | 'new' | 'confirm' = $state('current');

  function nextPath(): string {
    const requested = $page.url.searchParams.get('next');
    if (
      !requested?.startsWith('/') ||
      requested.startsWith('//') ||
      requested.startsWith('/account/pin')
    )
      return '/';
    return requested;
  }

  onMount(async () => {
    const session = await ensureSession(true);
    if (!session) {
      await goto(loginPath($page.url.pathname + $page.url.search));
      return;
    }
    required = session.profile.pin_change_required;
    ready = true;
  });

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    error = '';
    message = '';
    if (newPin !== confirmPin) {
      error = 'The new PINs do not match.';
      return;
    }
    saving = true;
    try {
      await api<void>('/auth/pin', {
        method: 'POST',
        body: jsonBody({ current_pin: currentPin, new_pin: newPin })
      });
      await ensureSession(true);
      currentPin = '';
      newPin = '';
      confirmPin = '';
      kioskStep = 'current';
      if (required) {
        await goto(nextPath());
      } else {
        message = 'Your PIN has been changed.';
      }
      required = false;
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'The PIN could not be changed.';
      currentPin = '';
      kioskStep = 'current';
    } finally {
      saving = false;
    }
  }

  async function signOut() {
    await logout();
    await goto(loginPath());
  }

  function advanceKioskStep() {
    const value = kioskStep === 'current' ? currentPin : newPin;
    if (value.length !== 4) return;
    kioskStep = kioskStep === 'current' ? 'new' : 'confirm';
  }

  function retreatKioskStep() {
    if (kioskStep === 'confirm') {
      confirmPin = '';
      kioskStep = 'new';
    } else if (kioskStep === 'new') {
      newPin = '';
      kioskStep = 'current';
    }
  }
</script>

<svelte:head><title>Change PIN · Filter Coffee Club</title></svelte:head>

<div class="pin-layout">
  <section>
    <p class="eyebrow">Account security</p>
    <h1>{required ? 'Choose your own PIN.' : 'Change your PIN.'}</h1>
    <p class="lede">
      {required
        ? 'Your account was created with a temporary PIN. Replace it before continuing.'
        : 'Enter your current PIN, then choose a new four-digit PIN.'}
    </p>
  </section>
  {#if ready}
    <form class="panel" onsubmit={submit}>
      {#if $deviceModeStore === 'kiosk'}
        <div class="kiosk-pin-step">
          <p class="eyebrow">
            {kioskStep === 'current'
              ? 'Step 1 of 3'
              : kioskStep === 'new'
                ? 'Step 2 of 3'
                : 'Step 3 of 3'}
          </p>
          {#if kioskStep === 'current'}
            <h2>Enter current PIN</h2>
            <PinPad label="Current PIN" bind:value={currentPin} disabled={saving} />
          {:else if kioskStep === 'new'}
            <h2>Enter new PIN</h2>
            <PinPad label="New PIN" bind:value={newPin} disabled={saving} />
          {:else}
            <h2>Repeat new PIN</h2>
            <PinPad label="Repeat new PIN" bind:value={confirmPin} disabled={saving} />
          {/if}
        </div>
      {:else}
        <label>
          Current PIN
          <input
            bind:value={currentPin}
            inputmode="numeric"
            autocomplete="current-password"
            pattern="[0-9][0-9][0-9][0-9]"
            maxlength="4"
            required
          />
        </label>
        <label>
          New PIN
          <input
            bind:value={newPin}
            inputmode="numeric"
            autocomplete="new-password"
            pattern="[0-9][0-9][0-9][0-9]"
            maxlength="4"
            required
          />
        </label>
        <label>
          Repeat new PIN
          <input
            bind:value={confirmPin}
            inputmode="numeric"
            autocomplete="new-password"
            pattern="[0-9][0-9][0-9][0-9]"
            maxlength="4"
            required
          />
        </label>
      {/if}
      {#if message}<p class="success" role="status">{message}</p>{/if}
      {#if error}<p class="error" role="alert">{error}</p>{/if}
      <div class="actions">
        {#if $deviceModeStore === 'kiosk' && kioskStep !== 'confirm'}
          <button
            class="primary"
            type="button"
            onclick={advanceKioskStep}
            disabled={(kioskStep === 'current' ? currentPin : newPin).length !== 4}>Continue</button
          >
        {:else}
          <button class="primary" disabled={saving || confirmPin.length !== 4}
            >{saving ? 'Changing…' : required ? 'Change PIN and continue' : 'Change PIN'}</button
          >
        {/if}
        {#if $deviceModeStore === 'kiosk' && kioskStep !== 'current'}
          <button class="secondary" type="button" onclick={retreatKioskStep} disabled={saving}
            >Back</button
          >
        {/if}
        {#if required}<button class="secondary" type="button" onclick={signOut}
            >Sign out instead</button
          >{/if}
      </div>
    </form>
  {:else}
    <div class="loading-card">Checking your account…</div>
  {/if}
</div>

<style>
  .pin-layout {
    display: grid;
    grid-template-columns: 1.1fr minmax(320px, 0.72fr);
    gap: clamp(30px, 8vw, 100px);
    align-items: center;
    min-height: 66vh;
  }
  .kiosk-pin-step {
    display: grid;
    gap: 14px;
  }
  .kiosk-pin-step > p,
  .kiosk-pin-step > h2 {
    margin-bottom: 0;
    text-align: center;
  }
  @media (max-width: 760px) {
    .pin-layout {
      grid-template-columns: 1fr;
    }
  }
</style>
