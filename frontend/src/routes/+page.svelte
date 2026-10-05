<script lang="ts">
  import { onMount } from 'svelte';
  import { brewStatusStore, refreshBrewStatusAfterMutation } from '$lib/brew-status';
  import { loginPath } from '$lib/device';
  import { api, appSettingsStore, jsonBody, sessionStore } from '$lib/api';
  import BrewCard from '$lib/BrewCard.svelte';
  import Logo from '$lib/Logo.svelte';
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
  let repeatingBrewId = $state<number | null>(null);
  const repeatKeys = new Map<number, string>();
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
    if (repeatingBrewId !== null) return;
    repeatingBrewId = brew.id;
    const key = repeatKeys.get(brew.id) ?? crypto.randomUUID();
    repeatKeys.set(brew.id, key);
    try {
      const clone = await api<Brew>(`/brews/${brew.id}/clone`, {
        headers: { 'Idempotency-Key': key },
        method: 'POST',
        body: jsonBody({})
      });
      await refreshBrewStatusAfterMutation().catch(() => undefined);
      location.href = `/brews/${clone.id}`;
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not start another brew.';
      await refreshBrewStatusAfterMutation().catch(() => undefined);
    } finally {
      repeatingBrewId = null;
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
        <BrewCard
          {brew}
          {comparison}
          profileId={$sessionStore?.profile.id}
          repeatDisabled={repeatingBrewId !== null}
          onrepeat={$sessionStore ? repeat : undefined}
        />
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
  .section-heading {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 16px;
  }
  .section-links {
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
  .active-card h3 {
    margin: 14px 0 4px;
  }
  .button.disabled {
    opacity: 0.55;
    cursor: not-allowed;
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
  @media (max-width: 560px) {
    .section-heading {
      flex-direction: column;
    }
    .section-heading h2 {
      margin-bottom: 0;
    }
    .section-links {
      justify-content: start;
      justify-items: start;
    }
  }
</style>
