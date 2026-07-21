<script lang="ts">
  import { formatCatalogDate, formatCatalogNumber } from '$lib/catalog';
  import { formatTime } from '$lib/api';
  import type { CatalogInsights } from '$lib/types';

  export let insights: CatalogInsights;
</script>

<section class="metrics-section" aria-labelledby="metrics-heading">
  <div class="section-heading">
    <p class="eyebrow">Brew results</p>
    <h2 id="metrics-heading">What the club observed.</h2>
  </div>
  <div class="metrics-grid">
    <div class="detail-metric">
      <strong>{insights.completed_brew_count}</strong><span>Completed brews</span>
    </div>
    <div class="detail-metric date">
      <strong>{formatCatalogDate(insights.last_completed_at)}</strong><span>Last used</span>
    </div>
    <div class="detail-metric">
      <strong
        >{insights.average_ratio === null
          ? '—'
          : `1:${formatCatalogNumber(insights.average_ratio)}`}</strong
      ><span>Average ratio</span>
    </div>
    <div class="detail-metric">
      <strong>{formatCatalogNumber(insights.average_temperature_c, ' °C')}</strong><span
        >Average temperature</span
      >
    </div>
    <div class="detail-metric">
      <strong
        >{formatTime(
          insights.average_total_brew_time_s === null
            ? null
            : Math.round(insights.average_total_brew_time_s)
        )}</strong
      ><span>Average brew time</span>
    </div>
    {#if insights.average_overall_throughput_g_s !== null}
      <div class="detail-metric">
        <strong>{formatCatalogNumber(insights.average_overall_throughput_g_s, ' g/s')}</strong><span
          >Average throughput</span
        >
      </div>
    {/if}
    {#if insights.kind === 'grinder' && insights.observed_grinder_setting_min !== null}
      <div class="detail-metric">
        <strong
          >{formatCatalogNumber(insights.observed_grinder_setting_min)}–{formatCatalogNumber(
            insights.observed_grinder_setting_max
          )}</strong
        >
        <span>Observed setting range</span>
      </div>
    {/if}
    {#if insights.ratings_visible}
      <div class="detail-metric">
        <strong>{formatCatalogNumber(insights.average_liking, ' / 10')}</strong><span
          >Average liking</span
        >
      </div>
      <div class="detail-metric">
        <strong>{insights.rating_count ?? 0}</strong><span>Ratings</span>
      </div>
    {/if}
  </div>
</section>

<style>
  .metrics-section,
  .section-heading {
    display: grid;
    gap: var(--catalog-gap-md, 16px);
  }
  .section-heading :global(p),
  .section-heading h2 {
    margin: 0;
  }
  .section-heading {
    gap: var(--catalog-gap-xs, 4px);
  }
  .section-heading h2 {
    font-size: clamp(1.8rem, 4vw, 2.7rem);
  }
  .metrics-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 145px), 1fr));
    gap: var(--catalog-gap-sm, 8px);
  }
  .detail-metric {
    display: grid;
    align-content: space-between;
    gap: 10px;
    min-height: 118px;
    padding: 16px;
    border: 1px solid var(--line);
    border-radius: 16px;
    background: var(--surface);
  }
  .detail-metric strong {
    overflow-wrap: anywhere;
    font-family: Georgia, 'Times New Roman', serif;
    font-size: clamp(1.45rem, 3vw, 2.25rem);
    line-height: 1;
  }
  .detail-metric.date strong {
    font-size: clamp(1.15rem, 2vw, 1.5rem);
    line-height: 1.12;
  }
  .detail-metric span {
    color: var(--muted);
    font-size: 0.72rem;
    font-weight: 800;
    letter-spacing: 0.07em;
    text-transform: uppercase;
  }
</style>
