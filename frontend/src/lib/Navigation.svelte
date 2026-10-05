<script lang="ts">
  import { onMount } from 'svelte';
  import { afterNavigate, goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { logout, sessionStore } from '$lib/api';
  import { deviceModeStore, loginPath } from '$lib/device';

  let { ready, demoMode }: { ready: boolean; demoMode: boolean } = $props();
  let navOpen = $state(false);
  let navToggle: HTMLButtonElement;
  let navPanel: HTMLElement;

  function closeNav() {
    navOpen = false;
  }

  async function signOut() {
    closeNav();
    await logout();
    await goto(loginPath());
  }

  function containsTarget(target: EventTarget | null): boolean {
    return (
      target instanceof Node && Boolean(navToggle?.contains(target) || navPanel?.contains(target))
    );
  }

  function handleNavKeydown(event: KeyboardEvent) {
    if (event.key !== 'Escape' || !navOpen || !containsTarget(event.target)) return;
    closeNav();
    navToggle?.focus();
  }

  function handleOutsideInteraction(event: MouseEvent | FocusEvent) {
    if (navOpen && !containsTarget(event.target)) closeNav();
  }

  afterNavigate(closeNav);

  onMount(() => {
    const mobile = window.matchMedia('(max-width: 820px)');
    mobile.addEventListener('change', closeNav);
    return () => mobile.removeEventListener('change', closeNav);
  });
</script>

<svelte:window
  onkeydown={handleNavKeydown}
  onclick={handleOutsideInteraction}
  onfocusin={handleOutsideInteraction}
/>

<button
  class="nav-toggle"
  type="button"
  bind:this={navToggle}
  aria-expanded={navOpen}
  aria-controls="main-navigation"
  onclick={() => (navOpen = !navOpen)}>Menu</button
>
<nav
  id="main-navigation"
  class="main-navigation"
  class:open={navOpen}
  aria-label="Main navigation"
  bind:this={navPanel}
>
  {#if ready}
    {#if $sessionStore}
      {#if $sessionStore.profile.pin_change_required}
        {#if !demoMode}
          <a
            class:active={$page.url.pathname === '/account/pin'}
            href="/account/pin"
            onclick={closeNav}>Change PIN</a
          >
        {/if}
      {:else}
        <a
          class:active={$page.url.pathname.startsWith('/coffees')}
          href="/coffees"
          onclick={closeNav}>Coffees</a
        >
        <a
          class:active={$page.url.pathname.startsWith('/equipment')}
          href="/equipment"
          onclick={closeNav}>Equipment</a
        >
        <a
          class:active={$page.url.pathname === '/profiles' ||
            ($page.url.pathname.startsWith('/profiles/') &&
              $page.url.pathname !== `/profiles/${$sessionStore.profile.id}`)}
          href="/profiles"
          onclick={closeNav}>Members</a
        >
        <a
          class:active={$page.url.pathname.startsWith('/analytics')}
          href="/analytics"
          onclick={closeNav}>Analytics</a
        >
        {#if $sessionStore.profile.role === 'admin' && $deviceModeStore !== 'kiosk'}
          <a class:active={$page.url.pathname.startsWith('/admin')} href="/admin" onclick={closeNav}
            >Admin</a
          >
        {/if}
        {#if !demoMode}
          <a
            class:active={$page.url.pathname === '/account/pin'}
            href="/account/pin"
            onclick={closeNav}>Change PIN</a
          >
        {/if}
      {/if}
      {#if !$sessionStore.profile.pin_change_required}
        <a
          class:active={$page.url.pathname === `/profiles/${$sessionStore.profile.id}`}
          href={`/profiles/${$sessionStore.profile.id}`}
          onclick={closeNav}>{$sessionStore.profile.display_name}</a
        >
      {/if}
      <button class="nav-action" onclick={signOut}>Sign out</button>
    {:else}
      <a class:active={$page.url.pathname === '/'} href="/" onclick={closeNav}>Home</a>
      <a class:active={$page.url.pathname.startsWith('/coffees')} href="/coffees" onclick={closeNav}
        >Coffees</a
      >
      <a href={loginPath()} onclick={closeNav}>Sign in</a>
    {/if}
  {/if}
</nav>
