<script lang="ts">
  import FlavorRadar from '$lib/FlavorRadar.svelte';
  import RatingMetrics from '$lib/RatingMetrics.svelte';
  import { formatTime } from '$lib/api';
  import { formatCatalogDate, formatCatalogNumber } from '$lib/catalog';
  import type { Coffee, CoffeeRatingInsights } from '$lib/types';

  export let coffee: Coffee;
  export let insights: CoffeeRatingInsights;
  export let loadingMore = false;
  export let loadMoreError = '';
  export let onloadmore: () => void;
</script>

<section class="tasting-section" aria-labelledby="tasting-heading">
  <div class="section-heading">
    <p class="eyebrow">Tasting results</p>
    <h2 id="tasting-heading">What the club tasted.</h2>
    <p class="muted">
      {insights.aggregate.count} tasting {insights.aggregate.count === 1 ? 'response' : 'responses'}
      across {insights.rated_brew_count} rated
      {insights.rated_brew_count === 1 ? 'brew' : 'brews'}.
    </p>
  </div>
  <div class="aggregate-layout">
    <RatingMetrics aggregate={insights.aggregate} />
    <div class="radar-card">
      <FlavorRadar
        axes={insights.aggregate.flavor_axes}
        subject={`${coffee.roaster} ${coffee.name}`}
        responseUnit="response"
      />
    </div>
  </div>
</section>

<section class="comparison-section" aria-labelledby="comparison-heading">
  <div class="section-heading">
    <p class="eyebrow">Brew comparison</p>
    <h2 id="comparison-heading">How each brew landed.</h2>
    <p class="muted">Recipe settings stay attached to each brew so outcomes can be compared.</p>
  </div>
  {#if insights.rated_brews.length === 0}
    <div class="empty">No rated brews yet.</div>
  {:else}
    <div class="comparison-grid" data-testid="brew-comparison-grid">
      {#each insights.rated_brews as result}
        <article class="brew-comparison-card" data-testid="brew-comparison-card">
          <div class="brew-heading">
            <div>
              <p class="eyebrow">Brew #{result.brew.id}</p>
              <h3>{formatCatalogDate(result.brew.completed_at)}</h3>
              <span
                >by {result.brew.operator_name} · {result.aggregate.count}
                {result.aggregate.count === 1 ? 'rating' : 'ratings'}</span
              >
            </div>
            <a href={`/brews/${result.brew.id}`}>View brew <span aria-hidden="true">→</span></a>
          </div>
          <dl class="recipe-context">
            <div>
              <dt>Ratio</dt>
              <dd>1:{formatCatalogNumber(result.brew.ratio)}</dd>
            </div>
            <div>
              <dt>Temperature</dt>
              <dd>{formatCatalogNumber(result.brew.temperature_c, ' °C')}</dd>
            </div>
            <div>
              <dt>Grinder</dt>
              <dd>
                {result.brew.grinder_name} · {formatCatalogNumber(result.brew.grinder_setting)}
                {result.brew.grinder_unit}
              </dd>
            </div>
            <div>
              <dt>Brew time</dt>
              <dd>{formatTime(result.brew.total_brew_time_s)}</dd>
            </div>
            <div>
              <dt>Throughput</dt>
              <dd>{formatCatalogNumber(result.brew.overall_throughput_g_s, ' g/s')}</dd>
            </div>
          </dl>
          <RatingMetrics aggregate={result.aggregate} compact />
          <FlavorRadar
            axes={result.aggregate.flavor_axes}
            subject={`brew ${result.brew.id}`}
            compact
          />
        </article>
      {/each}
    </div>
  {/if}
  {#if loadMoreError}<p class="error partial" role="status">{loadMoreError}</p>{/if}
  {#if insights.next_offset !== null}
    <button class="secondary load-more" disabled={loadingMore} onclick={onloadmore}>
      {loadingMore ? 'Loading…' : 'Load more brews'}
    </button>
  {/if}
</section>

<style>
  .tasting-section,
  .comparison-section,
  .section-heading,
  .brew-comparison-card,
  .brew-heading > div {
    display: grid;
  }
  .tasting-section,
  .comparison-section,
  .brew-comparison-card {
    gap: var(--catalog-gap-md, 16px);
  }
  .section-heading {
    gap: var(--catalog-gap-xs, 4px);
  }
  .section-heading :global(p),
  .section-heading h2,
  .brew-heading :global(p),
  .brew-heading h3 {
    margin: 0;
  }
  .section-heading h2 {
    font-size: clamp(1.8rem, 4vw, 2.7rem);
  }
  .aggregate-layout {
    display: grid;
    grid-template-columns: minmax(0, 0.9fr) minmax(320px, 1.1fr);
    gap: clamp(18px, 4vw, 40px);
    align-items: center;
    min-width: 0;
  }
  .radar-card,
  .brew-comparison-card {
    min-width: 0;
    border: 1px solid var(--line);
    border-radius: 18px;
    background: var(--surface);
  }
  .radar-card {
    padding: clamp(12px, 3vw, 24px);
  }
  .comparison-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 16px;
    min-width: 0;
  }
  .brew-comparison-card {
    align-content: start;
    padding: clamp(14px, 2.5vw, 20px);
  }
  .brew-heading {
    display: flex;
    justify-content: space-between;
    gap: 14px;
  }
  .brew-heading > div {
    gap: 4px;
  }
  .brew-heading h3 {
    font-size: 1.2rem;
  }
  .brew-heading span {
    color: var(--muted);
    font-size: 0.78rem;
  }
  .brew-heading > a {
    flex: 0 0 auto;
    font-size: 0.82rem;
    font-weight: 800;
    text-decoration: none;
  }
  .recipe-context {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 10px 14px;
    margin: 0;
    padding: 12px;
    border-radius: 12px;
    background: var(--cream);
  }
  .recipe-context div {
    display: grid;
    align-content: start;
    gap: 2px;
    min-width: 0;
  }
  .recipe-context dt {
    color: var(--muted);
    font-size: 0.62rem;
    font-weight: 800;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }
  .recipe-context dd {
    margin: 0;
    overflow-wrap: anywhere;
    font-size: 0.78rem;
    line-height: 1.35;
  }
  .load-more {
    justify-self: center;
  }
  @media (max-width: 900px) {
    .aggregate-layout,
    .comparison-grid {
      grid-template-columns: 1fr;
    }
  }
  @media (max-width: 520px) {
    .brew-heading {
      display: grid;
    }
    .brew-heading > a {
      width: fit-content;
    }
    .recipe-context {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
</style>
