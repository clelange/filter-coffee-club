<script lang="ts">
  import { onMount } from 'svelte';
  import { browser } from '$app/environment';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import BrewActivityRail from '$lib/BrewActivityRail.svelte';
  import Logo from '$lib/Logo.svelte';
  import Navigation from '$lib/Navigation.svelte';
  import { brewStatusStore } from '$lib/brew-status';
  import { adoptSessionDeviceMode, deviceModeStore, initializeDeviceMode } from '$lib/device';
  import { api, appSettingsStore, ensureSession, logout, sessionStore } from '$lib/api';
  import { applyTheme } from '$lib/theme';
  import type { AppSettings } from '$lib/types';
  import '../styles.css';

  const repositoryUrl = 'https://github.com/clelange/filter-coffee-club';

  let { children } = $props();
  const fallbackSettings: AppSettings = {
    app_name: 'Filter Coffee Club',
    app_version: 'development',
    subtitle: 'High-Energy Physics coffee breaks at PSI',
    public_base_url: null,
    logo_path: null,
    brewing_logo_path: null,
    color_cream: '#F6F1E8',
    color_surface: '#FFFDFC',
    color_ink: '#241C19',
    color_coffee: '#6B3F2A',
    color_cyan: '#00728F',
    color_amber: '#D88700',
    max_active_brews: 2,
    public_url_needs_configuration: false,
    demo_mode: false,
    demo_notice: null,
    demo_pin: null,
    demo_profile_names: []
  };
  const settings = $derived($appSettingsStore ?? fallbackSettings);
  let ready = $state(false);
  let settingsLoaded = $state(false);
  let appBootstrapped = $state(false);
  let bootstrapError = $state('');
  const brewing = $derived(Boolean($brewStatusStore?.active_count));

  $effect(() => {
    if (browser) {
      applyTheme(settings);
      document.title = settings.app_name;
    }
  });

  function versionUrl(version: string): string {
    if (/^v\d{4}\.\d{2}\.\d+$/.test(version)) {
      return `${repositoryUrl}/releases/tag/${encodeURIComponent(version)}`;
    }
    if (/^[0-9a-f]{7,40}$/i.test(version)) {
      return `${repositoryUrl}/commit/${encodeURIComponent(version)}`;
    }
    return repositoryUrl;
  }

  function issueUrl(version: string): string {
    const body = encodeURIComponent(`\n\nDeployed version: ${version}`);
    return `${repositoryUrl}/issues/new?body=${body}`;
  }

  function pinChangePath(url: URL): string {
    const next = `${url.pathname}${url.search}${url.hash}`;
    return `/account/pin?next=${encodeURIComponent(next)}`;
  }

  function allowsRequiredPinChange(pathname: string): boolean {
    return pathname === '/account/pin' || pathname === '/login' || pathname === '/setup';
  }

  async function bootstrapApp() {
    ready = false;
    appBootstrapped = false;
    bootstrapError = '';
    try {
      const device = initializeDeviceMode($page.url);
      const loadedSettings = await api<AppSettings>('/settings');
      settingsLoaded = true;
      appSettingsStore.set(loadedSettings);
      const bootstrap = await api<{ required: boolean }>('/auth/bootstrap-status');
      if (bootstrap.required && $page.url.pathname !== '/setup') {
        await goto('/setup');
      } else {
        const session = await ensureSession();
        let activeMode = device.mode;
        if (session && !device.configured) {
          adoptSessionDeviceMode(session.device_mode);
          activeMode = session.device_mode;
        } else if (session && session.device_mode !== device.mode) {
          await logout();
        }
        if (
          session?.device_mode === activeMode &&
          session?.profile.pin_change_required &&
          !allowsRequiredPinChange($page.url.pathname)
        ) {
          await goto(pinChangePath($page.url));
        }
      }
      appBootstrapped = true;
    } catch (caught) {
      bootstrapError =
        caught instanceof Error
          ? caught.message
          : 'The club could not be started. Check the connection and try again.';
    } finally {
      ready = true;
    }
  }

  onMount(() => {
    void bootstrapApp();
  });

  $effect(() => {
    const currentUrl = $page.url;
    if (
      ready &&
      $sessionStore?.profile.pin_change_required &&
      !allowsRequiredPinChange(currentUrl.pathname)
    ) {
      void goto(pinChangePath(currentUrl));
    }
  });
</script>

<svelte:head>
  <meta name="theme-color" content={settings.color_cream} />
  {#if settings.demo_mode}<meta name="robots" content="noindex, nofollow, noarchive" />{/if}
</svelte:head>

<a class="skip-link" href="#main-content">Skip to main content</a>

<header class="site-header">
  <div class="header-main">
    <a class="brand" href="/" aria-label={`${settings.app_name} home`}>
      <Logo
        logoPath={settings.logo_path}
        brewingLogoPath={settings.brewing_logo_path}
        {brewing}
        compact
      />
      <span>
        <strong>{settings.app_name}</strong>
        <small>{settings.subtitle}</small>
      </span>
    </a>
    <Navigation {ready} demoMode={settings.demo_mode} />
  </div>
  {#if ready && appBootstrapped && $page.url.pathname !== '/setup'}
    <BrewActivityRail />
  {/if}
</header>

{#if settings.public_url_needs_configuration && $sessionStore?.profile.role === 'admin' && !$sessionStore.profile.pin_change_required && $deviceModeStore !== 'kiosk'}
  <a class="config-warning" href="/admin">Set the public URL before printing or sharing QR codes.</a
  >
{/if}

{#if settings.demo_mode && settings.demo_notice}
  <div class="demo-banner" role="note">{settings.demo_notice}</div>
{/if}

<main id="main-content" tabindex="-1" class:loading={!ready}>
  {#if ready}
    {#if bootstrapError}
      <section class="panel bootstrap-error" role="alert" aria-labelledby="bootstrap-error-title">
        <p class="eyebrow">Connection problem</p>
        <h1 id="bootstrap-error-title">The club could not start.</h1>
        <p class="lede">{bootstrapError}</p>
        <button class="primary" type="button" onclick={bootstrapApp}>Try again</button>
      </section>
    {:else}
      {@render children()}
    {/if}
  {:else}
    <div class="loading-card" aria-live="polite">Warming up the club…</div>
  {/if}
</main>

<footer>
  <span>Filter Coffee Club · Measure carefully, brew gently.</span>
  {#if settingsLoaded}
    <span class="footer-detail">
      <span class="footer-separator" aria-hidden="true">·</span>
      <a href={versionUrl(settings.app_version)} target="_blank" rel="noopener noreferrer"
        >Version {settings.app_version}</a
      >
    </span>
    <span class="footer-detail">
      <span class="footer-separator" aria-hidden="true">·</span>
      <a href={issueUrl(settings.app_version)} target="_blank" rel="noopener noreferrer"
        >Report an issue</a
      >
    </span>
  {/if}
</footer>
