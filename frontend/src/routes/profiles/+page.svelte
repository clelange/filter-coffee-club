<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { api, ensureSession } from '$lib/api';
  import { loginPath } from '$lib/device';
  import type { ProfileDirectoryItem } from '$lib/types';

  let members: ProfileDirectoryItem[] = $state([]);
  let loading = $state(true);
  let error = $state('');

  onMount(load);

  async function load() {
    loading = true;
    error = '';
    try {
      const session = await ensureSession();
      if (!session) {
        await goto(loginPath('/profiles'));
        return;
      }
      members = await api<ProfileDirectoryItem[]>('/profiles');
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not load the member directory.';
    } finally {
      loading = false;
    }
  }

  function countLabel(member: ProfileDirectoryItem): string {
    if (member.rating_count === 0)
      return member.is_complete_history ? 'No ratings yet' : 'No shared ratings yet';
    if (member.is_complete_history)
      return `${member.rating_count} ${member.rating_count === 1 ? 'brew' : 'brews'} rated`;
    return `${member.rating_count} shared ${member.rating_count === 1 ? 'brew' : 'brews'}`;
  }
</script>

<svelte:head><title>Members · Filter Coffee Club</title></svelte:head>

<section class="directory-hero">
  <div>
    <p class="eyebrow">Club palates</p>
    <h1>Members</h1>
    <p class="lede">Open a tasting profile to compare favorite coffees and brew-by-brew ratings.</p>
  </div>
  <p class="visibility-note">
    Other profiles show only brews you have both rated. Your own profile and administrator views
    include complete history.
  </p>
</section>

{#if loading}
  <div class="empty" aria-live="polite">Gathering member profiles…</div>
{:else if error}
  <section class="panel directory-error">
    <p class="eyebrow">Member directory</p>
    <h2>Profiles are temporarily unavailable.</h2>
    <p class="error" role="alert">{error}</p>
    <button class="secondary" onclick={load}>Try again</button>
  </section>
{:else if members.length === 0}
  <div class="empty">
    <h2>No active members yet.</h2>
    <p>An administrator can add members from the People section.</p>
  </div>
{:else}
  <div class="member-grid">
    {#each members as member}
      <a class="member-card" href={`/profiles/${member.id}`}>
        <div class="member-heading">
          <h2>{member.display_name}</h2>
          {#if member.is_self}<span class="you-badge">You</span>{/if}
        </div>
        <p>{countLabel(member)}</p>
        <span class="view-profile">View tasting profile <span aria-hidden="true">→</span></span>
      </a>
    {/each}
  </div>
{/if}

<style>
  .directory-hero {
    display: grid;
    grid-template-columns: minmax(0, 1.2fr) minmax(280px, 0.8fr);
    gap: clamp(24px, 6vw, 72px);
    align-items: end;
    padding: clamp(36px, 8vw, 86px) 0 clamp(28px, 6vw, 58px);
  }
  .directory-hero h1 {
    margin: 4px 0 12px;
  }
  .directory-hero .lede,
  .visibility-note {
    margin: 0;
  }
  .visibility-note {
    padding: 15px 18px;
    border-left: 3px solid var(--amber);
    color: var(--muted);
  }
  .member-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 14px;
    margin-bottom: clamp(48px, 8vw, 90px);
  }
  .member-card {
    display: grid;
    gap: 20px;
    min-width: 0;
    padding: clamp(20px, 4vw, 30px);
    border: 1px solid var(--line);
    border-radius: 22px;
    background: var(--surface);
    color: var(--ink);
    text-decoration: none;
    box-shadow: var(--shadow);
  }
  .member-card:hover,
  .member-card:focus-visible {
    border-color: var(--cyan);
    transform: translateY(-2px);
  }
  .member-heading {
    display: flex;
    justify-content: space-between;
    align-items: start;
    gap: 12px;
  }
  .member-heading h2,
  .member-card p {
    margin: 0;
  }
  .member-heading h2 {
    overflow-wrap: anywhere;
    font-size: clamp(1.35rem, 3vw, 1.8rem);
  }
  .member-card p {
    color: var(--muted);
  }
  .you-badge {
    flex: 0 0 auto;
    padding: 4px 8px;
    border-radius: 999px;
    background: color-mix(in srgb, var(--cyan) 12%, var(--surface));
    color: var(--cyan);
    font-size: 0.7rem;
    font-weight: 900;
    letter-spacing: 0.07em;
    text-transform: uppercase;
  }
  .view-profile {
    align-self: end;
    color: var(--cyan);
    font-size: 0.8rem;
    font-weight: 850;
  }
  .directory-error {
    display: grid;
    justify-items: start;
    gap: 12px;
    margin-bottom: 70px;
  }
  .directory-error > * {
    margin: 0;
  }
  @media (max-width: 900px) {
    .member-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
  @media (max-width: 640px) {
    .directory-hero,
    .member-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
