<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import PinPad from '$lib/PinPad.svelte';
  import { deviceModeStore } from '$lib/device';
  import { api, ApiError, jsonBody, setSession } from '$lib/api';
  import type { AppSettings, ProfileIdentity, Session } from '$lib/types';

  let profiles: ProfileIdentity[] = $state([]);
  let settings: AppSettings | null = $state(null);
  let profileId = $state(0);
  let pin = $state('');
  let error = $state('');
  let loading = $state(false);
  let blockedUntilByProfile = $state<Record<number, number>>({});
  let now = $state(Date.now());
  let retrySeconds = $derived(
    Math.max(0, Math.ceil(((blockedUntilByProfile[profileId] ?? 0) - now) / 1000))
  );
  let blocked = $derived(retrySeconds > 0);

  function countdown(value: number): string {
    if (value < 60) return `${value} second${value === 1 ? '' : 's'}`;
    return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, '0')}`;
  }

  function safeNext(): string {
    const requested = $page.url.searchParams.get('next');
    return requested?.startsWith('/') && !requested.startsWith('//') ? requested : '/';
  }

  onMount(async () => {
    [profiles, settings] = await Promise.all([
      api<ProfileIdentity[]>('/auth/profiles'),
      api<AppSettings>('/settings')
    ]);
    profileId = Number($page.url.searchParams.get('profile')) || profiles[0]?.id || 0;
  });

  onMount(() => {
    const timer = window.setInterval(() => {
      now = Date.now();
      for (const [id, deadline] of Object.entries(blockedUntilByProfile)) {
        if (deadline <= now) delete blockedUntilByProfile[Number(id)];
      }
    }, 250);
    return () => window.clearInterval(timer);
  });

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    if (blocked) return;
    loading = true;
    error = '';
    const submittedProfileId = profileId;
    try {
      const session = await api<Session>('/auth/login', {
        method: 'POST',
        body: jsonBody({ profile_id: submittedProfileId, pin, device_mode: $deviceModeStore })
      });
      setSession(session);
      const next = safeNext();
      await goto(
        session.profile.pin_change_required ? `/account/pin?next=${encodeURIComponent(next)}` : next
      );
    } catch (caught) {
      if (
        caught instanceof ApiError &&
        caught.status === 429 &&
        caught.retryAfterSeconds !== null &&
        caught.retryAfterSeconds > 0
      ) {
        now = Date.now();
        blockedUntilByProfile[submittedProfileId] = now + caught.retryAfterSeconds * 1000;
      } else {
        error = caught instanceof Error ? caught.message : 'Sign-in failed.';
      }
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
      <select
        bind:value={profileId}
        required
        onchange={() => {
          pin = '';
          error = '';
        }}
      >
        {#each profiles as profile}
          <option value={profile.id}>{profile.display_name}</option>
        {/each}
      </select>
    </label>
    {#if $deviceModeStore === 'kiosk'}
      <div class="kiosk-note" role="note">
        <strong>Shared touch display</strong>
        <span>You will be signed out when this activity is complete.</span>
      </div>
      <PinPad label="PIN" bind:value={pin} disabled={loading || blocked} />
    {:else}
      <label>
        PIN
        <input
          bind:value={pin}
          inputmode="numeric"
          autocomplete="current-password"
          pattern="[0-9][0-9][0-9][0-9]"
          maxlength="4"
          disabled={loading || blocked}
          required
        />
      </label>
    {/if}
    {#if blocked}
      <p class="error" role="alert">
        Too many incorrect PINs. Try again in {countdown(retrySeconds)}.
      </p>
    {:else if error}
      <p class="error" role="alert">{error}</p>
    {/if}
    <button class="primary" disabled={loading || blocked || !profileId || pin.length !== 4}
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
  .kiosk-note {
    display: grid;
    gap: 3px;
    padding: 12px 14px;
    border: 1px solid var(--line);
    border-radius: 13px;
    background: color-mix(in srgb, var(--cyan) 7%, var(--surface));
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
  .kiosk-note span {
    color: var(--muted);
    font-weight: 500;
  }
  @media (max-width: 760px) {
    .login-layout {
      grid-template-columns: 1fr;
    }
  }
</style>
