<script lang="ts">
  import { formatTime } from '$lib/api';
  import { formatCatalogDate, formatCatalogNumber } from '$lib/catalog';
  import ProfileLink from '$lib/ProfileLink.svelte';
  import type { CatalogInsights } from '$lib/types';

  export let insights: CatalogInsights;
</script>

<section class="recent-section" aria-labelledby="recent-heading">
  <div class="section-heading">
    <p class="eyebrow">Latest activity</p>
    <h2 id="recent-heading">Recent completed brews.</h2>
  </div>
  {#if insights.recent_brews.length === 0}
    <div class="empty">No completed brews have used this item yet.</div>
  {:else}
    <div class="brew-list">
      {#each insights.recent_brews as brew}
        <article class="brew-result">
          <div class="brew-heading">
            <div>
              <strong
                ><a class="brew-target" href={`/brews/${brew.id}`}
                  >{brew.coffee_roaster} · {brew.coffee_name}</a
                ></strong
              >
              <span
                >{formatCatalogDate(brew.completed_at)} · by
                <span class="operator-link"
                  ><ProfileLink
                    profileId={brew.operator_id}
                    displayName={brew.operator_name}
                  /></span
                ></span
              >
            </div>
            <a class="view-label" href={`/brews/${brew.id}`}
              >View brew <span aria-hidden="true">→</span></a
            >
          </div>
          <dl>
            <div>
              <dt>Recipe</dt>
              <dd>
                {formatCatalogNumber(brew.dose_g, ' g')} → {formatCatalogNumber(brew.water_g, ' g')} ·
                1:{formatCatalogNumber(brew.ratio)} · {brew.servings}
                {brew.servings === 1 ? 'serving' : 'servings'}
              </dd>
            </div>
            <div>
              <dt>Temperature</dt>
              <dd>{formatCatalogNumber(brew.temperature_c, ' °C')}</dd>
            </div>
            <div>
              <dt>Grinder</dt>
              <dd>
                {brew.grinder_name} · {formatCatalogNumber(brew.grinder_setting)}
                {brew.grinder_unit}
              </dd>
            </div>
            <div>
              <dt>Brewer</dt>
              <dd>
                {[brew.dripper_name, brew.filter_name].filter(Boolean).join(' · ') ||
                  'Not recorded'}
              </dd>
            </div>
            <div>
              <dt>Measured result</dt>
              <dd>
                {formatTime(brew.total_brew_time_s)} · {formatCatalogNumber(
                  brew.overall_throughput_g_s,
                  ' g/s'
                )}
              </dd>
            </div>
            <div>
              <dt>Pour plan</dt>
              <dd>
                {brew.bloom_water_g === null
                  ? 'Bloom not recorded'
                  : `${formatCatalogNumber(brew.bloom_water_g, ' g')} for ${formatTime(brew.bloom_time_s)}`}
                · {brew.pour_count === null ? 'Pours not recorded' : `${brew.pour_count} pours`}
              </dd>
            </div>
            <div>
              <dt>Target flow</dt>
              <dd>{formatCatalogNumber(brew.target_flow_g_s, ' g/s')}</dd>
            </div>
            {#if brew.technique_note}
              <div class="wide">
                <dt>Technique</dt>
                <dd>{brew.technique_note}</dd>
              </div>
            {/if}
            {#if insights.ratings_visible}<div>
                <dt>Liking</dt>
                <dd>
                  {formatCatalogNumber(brew.average_liking, ' / 10')} · {brew.rating_count ?? 0}
                  {brew.rating_count === 1 ? 'rating' : 'ratings'}
                </dd>
              </div>{/if}
          </dl>
        </article>
      {/each}
    </div>
  {/if}
</section>

<style>
  .recent-section,
  .section-heading,
  .brew-list {
    display: grid;
  }
  .recent-section,
  .brew-list {
    gap: var(--catalog-gap-md, 16px);
  }
  .section-heading {
    gap: var(--catalog-gap-xs, 4px);
  }
  .section-heading :global(p),
  .section-heading h2 {
    margin: 0;
  }
  .section-heading h2 {
    font-size: clamp(1.8rem, 4vw, 2.7rem);
  }
  .brew-result {
    position: relative;
    display: grid;
    gap: 14px;
    min-width: 0;
    padding: clamp(16px, 3vw, 22px);
    border: 1px solid var(--line);
    border-radius: 18px;
    background: var(--surface);
    color: var(--ink);
    text-decoration: none;
  }
  .brew-result:hover {
    border-color: color-mix(in srgb, var(--cyan) 45%, var(--line));
  }
  .brew-target {
    color: inherit;
    text-decoration: none;
  }
  .brew-target::after {
    position: absolute;
    inset: 0;
    content: '';
  }
  .operator-link,
  .view-label {
    position: relative;
    z-index: 1;
  }
  .brew-heading {
    display: flex;
    justify-content: space-between;
    gap: 16px;
  }
  .brew-heading > div {
    display: grid;
    gap: 4px;
  }
  .brew-heading strong {
    font-size: 1.02rem;
  }
  .brew-heading span,
  dt {
    color: var(--muted);
    font-size: 0.78rem;
  }
  .view-label {
    flex: 0 0 auto;
    color: var(--cyan) !important;
    font-weight: 800;
    text-decoration: none;
  }
  dl {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 155px), 1fr));
    gap: 12px 18px;
    margin: 0;
  }
  dl div {
    display: grid;
    gap: 3px;
    min-width: 0;
  }
  dl .wide {
    grid-column: 1 / -1;
  }
  dt {
    font-weight: 800;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }
  dd {
    margin: 0;
    overflow-wrap: anywhere;
    font-size: 0.88rem;
    line-height: 1.4;
  }
  @media (max-width: 520px) {
    .brew-heading {
      display: grid;
    }
  }
</style>
