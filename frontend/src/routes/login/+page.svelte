<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { api, jsonBody, setSession } from '$lib/api';
  import type { AppSettings, Profile, Session } from '$lib/types';

  let profiles: Profile[] = $state([]);
  let settings: AppSettings | null = $state(null);
  let profileId = $state(0);
  let pin = $state('');
  let deviceMode: 'kiosk' | 'personal' = $state('personal');
  let error = $state('');
  let loading = $state(false);

  function safeNext(): string {
    const requested = $page.url.searchParams.get('next');
    return requested?.startsWith('/') && !requested.startsWith('//') ? requested : '/';
  }

  onMount(async () => {
    [profiles, settings] = await Promise.all([
      api<Profile[]>('/auth/profiles'),
      api<AppSettings>('/settings')
    ]);
    profileId = Number($page.url.searchParams.get('profile')) || profiles[0]?.id || 0;
    deviceMode = $page.url.searchParams.get('mode') === 'kiosk' ? 'kiosk' : 'personal';
  });

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    loading = true;
    error = '';
    try {
      const session = await api<Session>('/auth/login', {
        method: 'POST',
        body: jsonBody({ profile_id: profileId, pin, device_mode: deviceMode })
      });
      setSession(session);
      const next = safeNext();
      await goto(
        session.profile.pin_change_required ? `/account/pin?next=${encodeURIComponent(next)}` : next
      );
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Sign-in failed.';
      pin = '';
    } finally {
      loading = false;
    }
  }
</script>

<svelte:head><title>Sign in · Filter Coffee Club</title></svelte:head>

<div class="login-layout">
  <section>
    <p class="eyebrow">Identify your signal</p>
    <h1>Who is brewing?</h1>
    <p class="lede">Choose your profile and enter your four-digit PIN.</p>
  </section>
  <form class="panel" onsubmit={submit}>
    {#if settings?.demo_mode}
      <div class="demo-login" role="note">
        <strong>Demo access</strong>
        <span>Every seeded profile uses PIN <code>{settings.demo_pin}</code>.</span>
        <span>Choose Demo Admin to explore administration.</span>
        <button class="secondary" type="button" onclick={() => (pin = settings?.demo_pin ?? '')}
          >Use demo PIN</button
        >
      </div>
    {/if}
    <label>
      Profile
      <select bind:value={profileId} required>
        {#each profiles as profile}
          <option value={profile.id}>{profile.display_name}</option>
        {/each}
      </select>
    </label>
    <label>
      PIN
      <input
        bind:value={pin}
        inputmode="numeric"
        autocomplete="current-password"
        pattern="[0-9][0-9][0-9][0-9]"
        maxlength="4"
        required
      />
    </label>
    <fieldset>
      <legend>This device is…</legend>
      <label class="choice">
        <input type="radio" bind:group={deviceMode} value="personal" />
        <span><strong>My phone or tablet</strong><small>Stay signed in for 3.5 days.</small></span>
      </label>
      <label class="choice">
        <input type="radio" bind:group={deviceMode} value="kiosk" />
        <span
          ><strong>Shared touch display</strong><small
            >Return to the invitation after each rating.</small
          ></span
        >
      </label>
    </fieldset>
    {#if error}<p class="error" role="alert">{error}</p>{/if}
    <button class="primary" disabled={loading || !profileId}
      >{loading ? 'Signing in…' : 'Sign in'}</button
    >
  </form>
</div>

<style>
  .login-layout {
    display: grid;
    grid-template-columns: 1.2fr minmax(320px, 0.75fr);
    gap: clamp(30px, 8vw, 100px);
    align-items: center;
    min-height: 66vh;
  }
  .choice {
    grid-template-columns: 24px 1fr;
    align-items: center;
    padding: 12px;
    border: 1px solid var(--line);
    border-radius: 13px;
    cursor: pointer;
  }
  .demo-login {
    display: grid;
    gap: 7px;
    padding: 14px;
    border: 1px solid color-mix(in srgb, var(--cyan) 35%, var(--line));
    border-radius: 13px;
    background: color-mix(in srgb, var(--cyan) 7%, var(--surface));
  }
  .demo-login code {
    font-size: 1rem;
    font-weight: 850;
  }
  .demo-login button {
    justify-self: start;
    min-height: 42px;
    padding: 8px 15px;
  }
  .choice input {
    width: 20px;
    min-height: 20px;
  }
  .choice span {
    display: grid;
    gap: 2px;
  }
  .choice small {
    color: var(--muted);
    font-weight: 500;
  }
  @media (max-width: 760px) {
    .login-layout {
      grid-template-columns: 1fr;
    }
  }
</style>
