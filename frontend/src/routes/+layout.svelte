<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import Logo from '$lib/Logo.svelte';
  import { api, ensureSession, logout, sessionStore } from '$lib/api';
  import type { AppSettings } from '$lib/types';
  import '../styles.css';

  let { children } = $props();
  let settings: AppSettings = $state({
    app_name: 'Filter Coffee Club',
    subtitle: 'High-Energy Physics coffee breaks at PSI',
    public_base_url: null,
    logo_path: null,
    color_cream: '#F6F1E8',
    color_surface: '#FFFDFC',
    color_ink: '#241C19',
    color_coffee: '#6B3F2A',
    color_cyan: '#007F9E',
    color_amber: '#D88700',
    public_url_needs_configuration: false
  });
  let ready = $state(false);

  function applyTheme(value: AppSettings) {
    const root = document.documentElement;
    root.style.setProperty('--cream', value.color_cream);
    root.style.setProperty('--surface', value.color_surface);
    root.style.setProperty('--ink', value.color_ink);
    root.style.setProperty('--coffee', value.color_coffee);
    root.style.setProperty('--cyan', value.color_cyan);
    root.style.setProperty('--amber', value.color_amber);
    document.title = value.app_name;
  }

  onMount(async () => {
    try {
      settings = await api<AppSettings>('/settings');
      applyTheme(settings);
      const bootstrap = await api<{ required: boolean }>('/auth/bootstrap-status');
      if (bootstrap.required && $page.url.pathname !== '/setup') {
        await goto('/setup');
      } else {
        await ensureSession();
      }
    } finally {
      ready = true;
    }
  });

  async function signOut() {
    await logout();
    await goto('/login');
  }
</script>

<svelte:head>
  <meta name="theme-color" content={settings.color_cream} />
</svelte:head>

<header class="site-header">
  <a class="brand" href="/" aria-label={`${settings.app_name} home`}>
    <Logo logoPath={settings.logo_path} compact />
    <span>
      <strong>{settings.app_name}</strong>
      <small>{settings.subtitle}</small>
    </span>
  </a>
  <nav aria-label="Main navigation">
    <a class:active={$page.url.pathname === '/'} href="/">Home</a>
    <a class:active={$page.url.pathname.startsWith('/coffees')} href="/coffees">Coffees</a>
    {#if $sessionStore}
      <a class:active={$page.url.pathname.startsWith('/equipment')} href="/equipment">Equipment</a>
      <a class:active={$page.url.pathname.startsWith('/analytics')} href="/analytics">Analytics</a>
      {#if $sessionStore.profile.role === 'admin'}
        <a class:active={$page.url.pathname.startsWith('/admin')} href="/admin">Admin</a>
      {/if}
      <button class="nav-action" onclick={signOut}>{$sessionStore.profile.display_name} · Sign out</button>
    {:else}
      <a class="button small" href="/login">Sign in</a>
    {/if}
  </nav>
</header>

{#if settings.public_url_needs_configuration && $sessionStore?.profile.role === 'admin'}
  <a class="config-warning" href="/admin">Set the public URL before printing or sharing QR codes.</a>
{/if}

<main class:loading={!ready}>
  {#if ready}
    {@render children()}
  {:else}
    <div class="loading-card" aria-live="polite">Warming up the club…</div>
  {/if}
</main>

<footer>Filter Coffee Club · Brew gently, measure carefully.</footer>
