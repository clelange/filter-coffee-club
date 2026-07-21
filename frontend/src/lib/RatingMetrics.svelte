<script lang="ts">
  import type { RatingAggregate } from '$lib/types';

  export let aggregate: RatingAggregate;
  export let compact = false;

  const metrics = [
    { key: 'liking', label: 'Liking', maximum: 9 },
    { key: 'acidity', label: 'Acidity', maximum: 5 },
    { key: 'bitterness', label: 'Bitterness', maximum: 5 },
    { key: 'sweetness', label: 'Sweetness', maximum: 5 },
    { key: 'body', label: 'Body', maximum: 5 }
  ];

  function score(key: string): string {
    const value = aggregate.averages[key];
    return value === undefined
      ? '—'
      : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
</script>

<div class:compact class="rating-metrics" data-testid="rating-metrics">
  {#each metrics as metric}
    <div class="rating-metric">
      <strong
        >{score(metric.key)}{#if aggregate.averages[metric.key] !== undefined}<i
            >/{metric.maximum}</i
          >{/if}</strong
      ><span>{metric.label}</span>
    </div>
  {/each}
  <div class="rating-metric">
    <strong>{aggregate.count}</strong><span>{aggregate.count === 1 ? 'Rating' : 'Ratings'}</span>
  </div>
</div>

<style>
  .rating-metrics {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 8px;
    min-width: 0;
  }
  .rating-metric {
    display: grid;
    align-content: space-between;
    gap: 10px;
    min-width: 0;
    min-height: 108px;
    padding: 15px;
    border: 1px solid var(--line);
    border-radius: 14px;
    background: var(--surface);
  }
  .rating-metric strong {
    overflow-wrap: anywhere;
    font-family: Georgia, 'Times New Roman', serif;
    font-size: clamp(1.35rem, 3vw, 2rem);
    line-height: 1;
  }
  .rating-metric i {
    color: var(--muted);
    font-family: inherit;
    font-size: 0.55em;
    font-style: normal;
  }
  .rating-metric span {
    color: var(--muted);
    font-size: 0.7rem;
    font-weight: 800;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  .rating-metrics.compact {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 6px;
  }
  .rating-metrics.compact .rating-metric {
    min-height: 78px;
    padding: 10px;
  }
  .rating-metrics.compact .rating-metric strong {
    font-size: 1.2rem;
  }
  .rating-metrics.compact .rating-metric span {
    font-size: 0.63rem;
  }
  @media (max-width: 460px) {
    .rating-metrics,
    .rating-metrics.compact {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
</style>
