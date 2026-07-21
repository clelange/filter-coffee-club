<script lang="ts">
  import { tick } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { api, ensureSession } from '$lib/api';
  import { loginPath } from '$lib/device';
  import RatingComparison from '$lib/RatingComparison.svelte';
  import type { ProfileRatings } from '$lib/types';

  let data: ProfileRatings | null = $state(null);
  let loading = $state(true);
  let loadingMore = $state(false);
  let error = $state('');
  let historyError = $state('');
  let requestVersion = 0;

  const PAGE_SIZE = 25;

  const profileId = $derived(Number($page.params.id));
  const metrics = [
    { key: 'liking', label: 'Liking', maximum: 9 },
    { key: 'acidity', label: 'Acidity', maximum: 5 },
    { key: 'bitterness', label: 'Bitterness', maximum: 5 },
    { key: 'sweetness', label: 'Sweetness', maximum: 5 },
    { key: 'body', label: 'Body', maximum: 5 }
  ];

  $effect(() => {
    const id = profileId;
    void load(id);
  });

  async function load(id: number) {
    const version = ++requestVersion;
    data = null;
    loading = true;
    loadingMore = false;
    error = '';
    historyError = '';
    const session = await ensureSession();
    if (version !== requestVersion) return;
    if (!session) {
      await goto(loginPath(`/profiles/${id}${location.hash}`));
      return;
    }
    try {
      const response = await api<ProfileRatings>(
        `/profiles/${id}/ratings?limit=${PAGE_SIZE}&offset=0`
      );
      if (version !== requestVersion) return;
      data = response;
      await tick();
      const anchor = location.hash.match(/^#brew-(\d+)$/)?.[0].slice(1);
      if (anchor) document.getElementById(anchor)?.scrollIntoView();
    } catch (caught) {
      if (version !== requestVersion) return;
      error = caught instanceof Error ? caught.message : 'Could not load this tasting profile.';
    } finally {
      if (version === requestVersion) loading = false;
    }
  }

  async function loadMoreRatings() {
    if (!data || data.next_offset === null || loadingMore) return;
    const version = requestVersion;
    const id = profileId;
    const offset = data.next_offset;
    loadingMore = true;
    historyError = '';
    try {
      const response = await api<ProfileRatings>(
        `/profiles/${id}/ratings?limit=${PAGE_SIZE}&offset=${offset}`
      );
      if (version !== requestVersion || id !== profileId || !data) return;
      data = { ...response, ratings: [...data.ratings, ...response.ratings] };
    } catch (caught) {
      if (version !== requestVersion) return;
      historyError =
        caught instanceof Error ? caught.message : 'Could not load more rating history.';
    } finally {
      if (version === requestVersion) loadingMore = false;
    }
  }

  function formatScore(value: number | undefined): string {
    if (value === undefined) return '—';
    return Number.isInteger(value) ? String(value) : value.toFixed(1);
  }
</script>

<svelte:head>
  <title
    >{data ? `${data.profile.display_name} · Ratings` : 'Tasting profile'} · Filter Coffee Club</title
  >
</svelte:head>

{#if loading}
  <div class="empty">Gathering tasting notes…</div>
{:else if error}
  <section class="panel">
    <p class="eyebrow">Tasting profile</p>
    <h1>There is nothing to show here.</h1>
    <p class="error">{error}</p>
    <a class="button secondary" href="/">Return home</a>
  </section>
{:else if data}
  <section class="profile-hero">
    <div>
      <p class="eyebrow">{data.is_self ? 'Your tasting profile' : 'Club tasting profile'}</p>
      <h1>{data.profile.display_name}</h1>
      <p class="lede">
        {data.rating_count}
        {data.rating_count === 1 ? 'brew rated' : 'brews rated'}
        {data.is_complete_history ? '' : ' in common with you'}.
      </p>
      {#if !data.is_complete_history}
        <p class="visibility-note">
          Only shared brews are visible. Rate a brew before seeing how another member scored it.
        </p>
      {/if}
    </div>
    <div class="profile-signal" aria-label={`${data.rating_count} ratings`}>
      <strong>{data.rating_count}</strong><span>tasting signals</span>
    </div>
  </section>

  {#if data.rating_count > 0}
    <section class="section">
      <div class="section-heading">
        <div>
          <p class="eyebrow">Across the history below</p>
          <h2>
            {data.is_self
              ? 'Your average palate.'
              : `${data.profile.display_name}’s average palate.`}
          </h2>
        </div>
      </div>
      <div class="average-grid">
        {#each metrics as metric}
          <article>
            <span>{metric.label}</span>
            <strong>{formatScore(data.averages[metric.key])}<i>/{metric.maximum}</i></strong>
          </article>
        {/each}
      </div>
    </section>

    <section class="section">
      <div class="section-heading">
        <div>
          <p class="eyebrow">Highest average liking</p>
          <h2>Most-liked coffees.</h2>
        </div>
      </div>
      <div class="favorite-grid">
        {#each data.favorite_coffees as coffee, index}
          <a href={`/coffees/${coffee.coffee_id}`} class="favorite-card">
            <span class="rank">#{index + 1}</span>
            <div>
              <small>{coffee.coffee_roaster}</small>
              <h3>{coffee.coffee_name}</h3>
              <p>
                {coffee.rating_count}
                {coffee.rating_count === 1 ? 'rating' : 'ratings'}
              </p>
            </div>
            <strong>{formatScore(coffee.average_liking)}<i>/9</i></strong>
          </a>
        {/each}
      </div>
    </section>

    <section class="section history-section">
      <div class="section-heading">
        <div>
          <p class="eyebrow">Brew by brew</p>
          <h2>Rating history.</h2>
        </div>
        <span class="muted">Every scored dimension compared with other tasters</span>
      </div>
      <div class="rating-history">
        {#each data.ratings as result}
          <article class="rating-card" id={`brew-${result.brew.id}`}>
            <div class="rating-heading">
              <div>
                <small>
                  {new Date(
                    result.brew.completed_at ?? result.brew.created_at
                  ).toLocaleDateString()}
                  · brew #{result.brew.id}
                </small>
                <h3>{result.brew.coffee_name}</h3>
                <p>
                  {result.brew.coffee_roaster} · {result.total_rating_count} club {result.total_rating_count ===
                  1
                    ? 'rating'
                    : 'ratings'}
                </p>
              </div>
              <a class="button secondary small" href={`/brews/${result.brew.id}`}>View brew</a>
            </div>
            <RatingComparison
              {result}
              subjectLabel={data.is_self ? 'You' : data.profile.display_name}
            />
          </article>
        {/each}
      </div>
      {#if historyError}<p class="error" role="alert">{historyError}</p>{/if}
      {#if data.next_offset !== null}
        <div class="load-more">
          <button class="secondary" onclick={loadMoreRatings} disabled={loadingMore}>
            {loadingMore ? 'Loading…' : 'Load more ratings'}
          </button>
        </div>
      {/if}
    </section>
  {:else}
    <div class="empty profile-empty">
      <h2>{data.is_complete_history ? 'No ratings yet.' : 'No shared ratings yet.'}</h2>
      <p>
        {data.is_self
          ? 'Your first completed tasting will start this profile.'
          : data.is_complete_history
            ? 'This member has not rated a completed brew yet.'
            : 'Once you have both rated the same brew, the comparison will appear here.'}
      </p>
      <a class="button" href="/">Browse past brews</a>
    </div>
  {/if}
{/if}

<style>
  .profile-hero {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 32px;
    min-height: 38vh;
    padding: clamp(30px, 7vw, 76px) 0;
  }
  .profile-hero h1 {
    margin-bottom: 10px;
  }
  .visibility-note {
    max-width: 640px;
    padding: 12px 15px;
    border-left: 3px solid var(--amber);
    color: var(--muted);
  }
  .profile-signal {
    display: grid;
    flex: 0 0 auto;
    place-items: center;
    width: clamp(150px, 22vw, 230px);
    aspect-ratio: 1;
    border: 2px solid var(--cyan);
    border-radius: 50%;
    background: color-mix(in srgb, var(--cyan) 7%, var(--surface));
    text-align: center;
  }
  .profile-signal strong {
    align-self: end;
    font:
      700 clamp(3rem, 8vw, 6rem)/0.9 Georgia,
      serif;
  }
  .profile-signal span {
    align-self: start;
    color: var(--muted);
    font-size: 0.75rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .section-heading,
  .rating-heading {
    display: flex;
    justify-content: space-between;
    align-items: end;
    gap: 18px;
  }
  .average-grid {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 10px;
  }
  .average-grid article {
    display: grid;
    gap: 8px;
    padding: clamp(16px, 3vw, 24px);
    border-radius: 18px;
    background: var(--coffee);
    color: white;
  }
  .average-grid span {
    font-size: 0.72rem;
    font-weight: 800;
    letter-spacing: 0.07em;
    text-transform: uppercase;
  }
  .average-grid strong {
    font-size: clamp(1.7rem, 4vw, 2.7rem);
  }
  .average-grid i,
  .favorite-card i {
    font-size: 0.75rem;
    font-style: normal;
    font-weight: 500;
    opacity: 0.72;
  }
  .favorite-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
  }
  .favorite-card {
    display: grid;
    grid-template-columns: auto 1fr auto;
    align-items: center;
    gap: 14px;
    padding: 20px;
    border: 1px solid var(--line);
    border-radius: 18px;
    background: var(--surface);
    color: var(--ink);
    text-decoration: none;
  }
  .favorite-card:hover {
    border-color: var(--cyan);
  }
  .favorite-card h3,
  .favorite-card p {
    margin: 2px 0;
  }
  .favorite-card small,
  .favorite-card p {
    color: var(--muted);
  }
  .favorite-card > strong {
    color: var(--coffee);
    font-size: 1.6rem;
  }
  .rank {
    color: var(--cyan);
    font-size: 0.75rem;
    font-weight: 900;
  }
  .history-section {
    scroll-margin-top: 100px;
  }
  .rating-history {
    display: grid;
    gap: 14px;
  }
  .rating-card {
    display: grid;
    gap: 20px;
    padding: clamp(18px, 4vw, 28px);
    scroll-margin-top: 100px;
    border: 1px solid var(--line);
    border-radius: 22px;
    background: var(--surface);
    box-shadow: var(--shadow);
  }
  .load-more {
    display: flex;
    justify-content: center;
    margin-top: 20px;
  }
  .rating-heading h3 {
    margin: 5px 0 2px;
    font-size: 1.35rem;
  }
  .rating-heading p,
  .rating-heading small {
    margin: 0;
    color: var(--muted);
  }
  .profile-empty {
    margin: 32px 0 80px;
  }
  @media (max-width: 820px) {
    .favorite-grid {
      grid-template-columns: 1fr;
    }
  }
  @media (max-width: 720px) {
    .profile-hero {
      align-items: start;
    }
    .profile-signal {
      width: 130px;
    }
    .average-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .average-grid article:first-child {
      grid-column: 1 / -1;
    }
  }
  @media (max-width: 560px) {
    .profile-hero,
    .section-heading,
    .rating-heading {
      display: grid;
    }
    .profile-signal {
      display: none;
    }
    .section-heading > .muted {
      margin-top: -10px;
    }
    .rating-heading .button {
      justify-self: start;
    }
  }
</style>
