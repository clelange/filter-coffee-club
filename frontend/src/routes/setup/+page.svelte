<script lang="ts">
  import { goto } from '$app/navigation';
  import { deviceModeStore } from '$lib/device';
  import { api, jsonBody, setSession } from '$lib/api';
  import type { Session } from '$lib/types';

  let displayName = $state('');
  let pin = $state('');
  let confirmPin = $state('');
  let error = $state('');
  let saving = $state(false);

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    error = '';
    if (pin !== confirmPin) {
      error = 'The PINs do not match.';
      return;
    }
    saving = true;
    try {
      const session = await api<Session>('/auth/bootstrap', {
        method: 'POST',
        body: jsonBody({ display_name: displayName, pin, device_mode: 'personal' })
      });
      setSession(session);
      await goto('/admin');
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Setup failed.';
    } finally {
      saving = false;
    }
  }

  async function checkAgain() {
    error = '';
    const status = await api<{ required: boolean }>('/auth/bootstrap-status');
    if (status.required) {
      error = 'Setup is not complete yet. Finish it on a phone or computer, then check again.';
    } else {
      await goto('/login');
    }
  }
</script>

<svelte:head><title>Set up · Filter Coffee Club</title></svelte:head>

<div class="setup-wrap">
  <section>
    <p class="eyebrow">First run</p>
    <h1>Open the club.</h1>
    <p class="lede">
      Create the first administrator. More members and shared equipment can be added next.
    </p>
  </section>
  {#if $deviceModeStore === 'kiosk'}
    <section class="panel kiosk-setup">
      <p class="eyebrow">Another device required</p>
      <h2>Complete setup on a phone or computer.</h2>
      <p class="muted">
        Open this club address on a personal device to create the first administrator. This shared
        display will remain keyboard-free.
      </p>
      {#if error}<p class="error" role="alert">{error}</p>{/if}
      <button class="primary" type="button" onclick={checkAgain}>Check again</button>
    </section>
  {:else}
    <form class="panel" onsubmit={submit}>
      <label>
        Your display name
        <input bind:value={displayName} autocomplete="name" required maxlength="80" />
      </label>
      <label>
        Four-digit PIN
        <input
          bind:value={pin}
          inputmode="numeric"
          autocomplete="new-password"
          pattern="[0-9][0-9][0-9][0-9]"
          maxlength="4"
          required
        />
      </label>
      <label>
        Repeat PIN
        <input
          bind:value={confirmPin}
          inputmode="numeric"
          autocomplete="new-password"
          pattern="[0-9][0-9][0-9][0-9]"
          maxlength="4"
          required
        />
      </label>
      {#if error}<p class="error" role="alert">{error}</p>{/if}
      <button class="primary" disabled={saving}
        >{saving ? 'Creating…' : 'Create administrator'}</button
      >
    </form>
  {/if}
</div>

<style>
  .setup-wrap {
    display: grid;
    grid-template-columns: 1.1fr minmax(300px, 0.7fr);
    gap: clamp(30px, 8vw, 100px);
    align-items: center;
    min-height: 66vh;
  }
  .kiosk-setup {
    display: grid;
    gap: 14px;
  }
  .kiosk-setup > * {
    margin-bottom: 0;
  }
  .kiosk-setup button {
    justify-self: start;
  }
  @media (max-width: 760px) {
    .setup-wrap {
      grid-template-columns: 1fr;
    }
  }
</style>
