<script lang="ts">
  import { onMount } from 'svelte';
  import { brewStatusStore, refreshBrewStatusAfterMutation } from '$lib/brew-status';
  import { loginPath } from '$lib/device';
  import { api, appSettingsStore, formatTime, jsonBody, sessionStore } from '$lib/api';
  import Logo from '$lib/Logo.svelte';
  import ProfileLink from '$lib/ProfileLink.svelte';
  import RatingComparison from '$lib/RatingComparison.svelte';
  import type {
    Brew,
    BrewActivityItem,
    RatingComparison as RatingComparisonData
  } from '$lib/types';

  let brews: Brew[] = $state([]);
  let comparisons: RatingComparisonData[] = $state([]);
  let loading = $state(true);
  let error = $state('');
  let comparisonError = $state('');
  let joiningBrewId = $state<number | null>(null);
  const active = $derived($brewStatusStore);

  onMount(() => {
    void load();
  });

  async function load() {
    try {
      brews = await api<Brew[]>('/brews?exclude_status=draft&limit=12');
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not load brews.';
      return;
    } finally {
      loading = false;
    }
    if ($sessionStore && brews.length > 0) await loadComparisons();
  }

  async function loadComparisons() {
    const params = new URLSearchParams();
    for (const brew of brews) params.append('brew_id', String(brew.id));
    try {
      comparisons = await api<RatingComparisonData[]>(
        `/ratings/me/comparisons?${params.toString()}`
      );
    } catch (caught) {
      // Comparisons enhance the brew log but must not make the log itself unavailable.
      comparisonError =
        caught instanceof Error
          ? caught.message
          : 'Rating comparisons are temporarily unavailable.';
    }
  }

  async function repeat(brew: Brew) {
    try {
      const clone = await api<Brew>(`/brews/${brew.id}/clone`, {
        method: 'POST',
        body: jsonBody({})
      });
      await refreshBrewStatusAfterMutation().catch(() => undefined);
      location.href = `/brews/${clone.id}`;
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not start another brew.';
      await refreshBrewStatusAfterMutation().catch(() => undefined);
    }
  }

  async function join(brew: BrewActivityItem) {
    if (joiningBrewId !== null) return;
    joiningBrewId = brew.id;
    try {
      await api<Brew>(`/brews/${brew.id}/join`, { method: 'POST', body: jsonBody({}) });
      await refreshBrewStatusAfterMutation().catch(() => undefined);
      location.href = `/brews/${brew.id}`;
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not join this brew.';
    } finally {
      joiningBrewId = null;
    }
  }

  function participates(brew: BrewActivityItem): boolean {
    return Boolean(
      $sessionStore && brew.operators.some((operator) => operator.id === $sessionStore?.profile.id)
    );
  }

  function ratingForBrew(brewId: number): RatingComparisonData | undefined {
    return comparisons.find((item) => item.brew_id === brewId);
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
        {#if active?.can_start ?? true}
          <a class="button" href="/brews/new">Start a brew</a>
        {:else}
          <span class="button disabled" aria-disabled="true">Brew capacity reached</span>
        {/if}
        <a class="button secondary" href="/analytics">Explore results</a>
      {:else}
        <a class="button" href={loginPath('/brews/new')}>Sign in to brew</a>
      {/if}
    </div>
  </div>
  <div class="hero-logo" aria-hidden="true">
    <Logo
      logoPath={$appSettingsStore?.logo_path ?? null}
      brewingLogoPath={$appSettingsStore?.brewing_logo_path ?? null}
      brewing={Boolean(active?.active_count)}
      large
    />
  </div>
</section>

{#if active && active.brews.length > 0}
  <section class="section active-section">
    <div class="section-heading">
      <div>
        <p class="eyebrow">Brewing now</p>
        <h2>{active.active_count} of {active.max_active_brews} active</h2>
      </div>
    </div>
    <div class="card-grid">
      {#each active.brews as brew}
        <article class="card active-card">
          <span class="status draft">active #{brew.id}</span>
          <h3>{brew.coffee_name}</h3>
          <p class="muted">
            {brew.coffee_roaster} · {brew.operators
              .map((operator) => operator.display_name)
              .join(', ')}
          </p>
          {#if $sessionStore}
            {#if participates(brew)}
              <a class="button small" href={`/brews/${brew.id}`}>Continue brew</a>
            {:else}
              <button class="small" onclick={() => join(brew)} disabled={joiningBrewId !== null}
                >{joiningBrewId === brew.id ? 'Joining…' : 'Join brew'}</button
              >
            {/if}
          {/if}
        </article>
      {/each}
    </div>
  </section>
{/if}

<section class="section">
  <div class="section-heading">
    <div>
      <p class="eyebrow">Latest observations</p>
      <h2>Past brews</h2>
    </div>
    <div class="section-links">
      {#if $sessionStore}
        <a href={`/profiles/${$sessionStore.profile.id}`}>My rating profile →</a>
      {/if}
      <a href="/coffees">Browse coffees →</a>
    </div>
  </div>
  {#if loading}
    <div class="empty">Loading brew log…</div>
  {:else if error}
    <p class="error" role="alert">{error}</p>
  {:else if brews.length === 0}
    <div class="empty">No brews yet. The first measurement is waiting.</div>
  {:else}
    {#if comparisonError && $sessionStore}
      <p class="comparison-error">Past brews are available, but your comparisons could not load.</p>
    {/if}
    <div class="card-grid">
      {#each brews as brew}
        {@const comparison = ratingForBrew(brew.id)}
        <article class="card brew-card">
          <div class="card-top">
            <span class="status {brew.status}">{brew.status}</span><small
              >{new Date(brew.created_at).toLocaleDateString()}</small
            >
          </div>
          <h3>{brew.coffee_name}</h3>
          <p class="muted">
            {brew.coffee_roaster} · brewed by
            <ProfileLink profileId={brew.operator_id} displayName={brew.operator_name} />
          </p>
          <div class="mini-metrics">
            <span><b>1:{brew.ratio}</b> ratio</span>
            <span><b>{brew.grinder_setting}</b> {brew.grinder_unit}</span>
            <span><b>{brew.temperature_c}°</b> water</span>
            <span><b>{formatTime(brew.total_brew_time_s)}</b> time</span>
          </div>
          {#if comparison}
            <div class="own-comparison">
              <div class="comparison-heading">
                <strong>Your rating vs other tasters</strong>
                <a href={`/profiles/${$sessionStore?.profile.id}#brew-${brew.id}`}>Full details →</a
                >
              </div>
              <RatingComparison result={comparison} compact />
            </div>
          {/if}
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
  .hero-logo {
    display: grid;
    min-height: 390px;
    place-items: center;
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
  .section-links,
  .comparison-heading {
    display: flex;
    align-items: center;
    gap: 16px;
  }
  .section-links {
    flex-wrap: wrap;
    justify-content: flex-end;
  }
  .comparison-error {
    margin: -8px 0 18px;
    color: var(--muted);
    font-size: 0.82rem;
  }
  .brew-card h3 {
    margin: 22px 0 4px;
    font-size: 1.35rem;
  }
  .active-card h3 {
    margin: 14px 0 4px;
  }
  .button.disabled {
    opacity: 0.55;
    cursor: not-allowed;
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
  .own-comparison {
    display: grid;
    gap: 10px;
    margin: 20px 0;
    padding-top: 18px;
    border-top: 1px solid var(--line);
  }
  .comparison-heading {
    justify-content: space-between;
    font-size: 0.78rem;
  }
  @media (max-width: 820px) {
    .hero {
      grid-template-columns: 1fr;
      min-height: auto;
    }
    .hero-logo {
      display: none;
    }
    .section-heading {
      align-items: start;
    }
    .section-links {
      display: grid;
      justify-items: end;
    }
  }
</style>
