<script lang="ts">
  import { onMount } from 'svelte';
  import { api, formatTime, jsonBody, sessionStore } from '$lib/api';
  import type { Brew } from '$lib/types';

  let brews: Brew[] = $state([]);
  let loading = $state(true);
  let error = $state('');

  onMount(load);

  async function load() {
    try {
      brews = await api<Brew[]>('/brews?limit=12');
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not load brews.';
    } finally {
      loading = false;
    }
  }

  async function repeat(brew: Brew) {
    const clone = await api<Brew>(`/brews/${brew.id}/clone`, {
      method: 'POST',
      body: jsonBody({})
    });
    location.href = `/brews/${clone.id}`;
  }
</script>

<svelte:head><title>Filter Coffee Club</title></svelte:head>

<section class="hero">
  <div>
    <p class="eyebrow">Coffee, under observation</p>
    <h1>Make the next brew measurable.</h1>
    <p class="lede">
      Record the recipe, keep it visible while pouring, then gather everyone’s tasting signal.
    </p>
    <div class="actions">
      {#if $sessionStore}
        <a class="button" href="/brews/new">Start a brew</a>
        <a class="button secondary" href="/analytics">Explore results</a>
      {:else}
        <a class="button" href="/login?next=/brews/new">Sign in to brew</a>
      {/if}
    </div>
  </div>
  <div class="orbit-art" aria-hidden="true">
    <div class="ring one"></div>
    <div class="ring two"></div>
    <div class="cup">FCC</div>
    <i></i>
  </div>
</section>

<section class="section">
  <div class="section-heading">
    <div>
      <p class="eyebrow">Latest observations</p>
      <h2>Recent brews</h2>
    </div>
    <a href="/coffees">Browse coffees →</a>
  </div>
  {#if loading}
    <div class="empty">Loading brew log…</div>
  {:else if error}
    <p class="error">{error}</p>
  {:else if brews.length === 0}
    <div class="empty">No brews yet. The first measurement is waiting.</div>
  {:else}
    <div class="card-grid">
      {#each brews as brew}
        <article class="card brew-card">
          <div class="card-top">
            <span class="status {brew.status}">{brew.status}</span><small
              >{new Date(brew.created_at).toLocaleDateString()}</small
            >
          </div>
          <h3>{brew.coffee_name}</h3>
          <p class="muted">{brew.coffee_roaster} · brewed by {brew.operator_name}</p>
          <div class="mini-metrics">
            <span><b>1:{brew.ratio}</b> ratio</span>
            <span><b>{brew.grinder_setting}</b> {brew.grinder_unit}</span>
            <span><b>{brew.temperature_c}°</b> water</span>
            <span><b>{formatTime(brew.total_brew_time_s)}</b> time</span>
          </div>
          <div class="actions">
            <a class="button small" href={`/brews/${brew.id}`}
              >{brew.status === 'completed'
                ? 'Open invitation'
                : brew.status === 'draft'
                  ? 'Continue brew'
                  : 'View record'}</a
            >
            {#if $sessionStore && brew.status === 'completed'}
              <button class="secondary" onclick={() => repeat(brew)}>Repeat</button>
            {/if}
          </div>
        </article>
      {/each}
    </div>
  {/if}
</section>

<style>
  .hero {
    display: grid;
    grid-template-columns: 1.25fr 0.75fr;
    gap: 40px;
    align-items: center;
    min-height: 58vh;
  }
  .orbit-art {
    position: relative;
    min-height: 390px;
    display: grid;
    place-items: center;
  }
  .ring {
    position: absolute;
    width: min(32vw, 340px);
    aspect-ratio: 1;
    border: 3px solid var(--cyan);
    border-radius: 50%;
    opacity: 0.52;
  }
  .ring.one {
    border-style: dashed;
    transform: rotate(24deg);
  }
  .ring.two {
    height: min(18vw, 190px);
    transform: rotate(-22deg);
  }
  .cup {
    z-index: 1;
    display: grid;
    place-items: center;
    width: 150px;
    height: 120px;
    border-radius: 18px 18px 60px 60px;
    background: var(--coffee);
    color: white;
    font:
      700 2.3rem Georgia,
      serif;
    box-shadow: var(--shadow);
  }
  .orbit-art i {
    position: absolute;
    top: 15%;
    right: 14%;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    background: var(--amber);
    box-shadow: 0 0 0 9px color-mix(in srgb, var(--amber) 18%, transparent);
  }
  .section-heading,
  .card-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 16px;
  }
  .card-top small {
    color: var(--muted);
  }
  .brew-card h3 {
    margin: 22px 0 4px;
    font-size: 1.35rem;
  }
  .mini-metrics {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    margin: 22px 0;
  }
  .mini-metrics span {
    display: grid;
    color: var(--muted);
    font-size: 0.75rem;
  }
  .mini-metrics b {
    color: var(--ink);
    font-size: 1.05rem;
  }
  @media (max-width: 760px) {
    .hero {
      grid-template-columns: 1fr;
      min-height: auto;
    }
    .orbit-art {
      display: none;
    }
  }
</style>
