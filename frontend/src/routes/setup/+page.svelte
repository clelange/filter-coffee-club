<script lang="ts">
  import { goto } from '$app/navigation';
  import { api, jsonBody, setSession } from '$lib/api';
  import type { Session } from '$lib/types';

  let displayName = $state('');
  let pin = $state('');
  let confirmPin = $state('');
  let deviceMode: 'kiosk'|'personal' = $state('personal');
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
        body: jsonBody({ display_name: displayName, pin, device_mode: deviceMode })
      });
      setSession(session);
      await goto('/admin');
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Setup failed.';
    } finally {
      saving = false;
    }
  }
</script>

<svelte:head><title>Set up · Filter Coffee Club</title></svelte:head>

<div class="setup-wrap">
  <section>
    <p class="eyebrow">First run</p>
    <h1>Open the club.</h1>
    <p class="lede">Create the first administrator. More members and shared equipment can be added next.</p>
  </section>
  <form class="panel" onsubmit={submit}>
    <label>
      Your display name
      <input bind:value={displayName} autocomplete="name" required maxlength="80" />
    </label>
    <label>
      Four-digit PIN
      <input bind:value={pin} inputmode="numeric" autocomplete="new-password" pattern="[0-9][0-9][0-9][0-9]" maxlength="4" required />
    </label>
    <label>
      Repeat PIN
      <input bind:value={confirmPin} inputmode="numeric" autocomplete="new-password" pattern="[0-9][0-9][0-9][0-9]" maxlength="4" required />
    </label>
    <fieldset><legend>This device is…</legend><label class="choice"><input type="radio" bind:group={deviceMode} value="personal" /><span><strong>My phone or tablet</strong><small>Stay signed in for 3.5 days.</small></span></label><label class="choice"><input type="radio" bind:group={deviceMode} value="kiosk" /><span><strong>Shared touch display</strong><small>Require a PIN for each brew or rating.</small></span></label></fieldset>
    {#if error}<p class="error" role="alert">{error}</p>{/if}
    <button class="primary" disabled={saving}>{saving ? 'Creating…' : 'Create administrator'}</button>
  </form>
</div>

<style>
  .setup-wrap {
    display: grid;
    grid-template-columns: 1.1fr minmax(300px, 0.7fr);
    gap: clamp(30px, 8vw, 100px);
    align-items: center;
    min-height: 66vh;
  }
  .choice { grid-template-columns:24px 1fr; align-items:center; padding:10px; border:1px solid var(--line); border-radius:13px; cursor:pointer; }.choice input{width:20px;min-height:20px}.choice span{display:grid}.choice small{color:var(--muted);font-weight:500}
  @media (max-width: 760px) {
    .setup-wrap { grid-template-columns: 1fr; }
  }
</style>
