<script lang="ts">
  import type { RatingComparison } from '$lib/types';

  type RatingField = 'liking' | 'acidity' | 'bitterness' | 'sweetness' | 'body';

  export let result: RatingComparison;
  export let compact = false;
  export let subjectLabel = 'You';

  const metrics: { key: RatingField; label: string; maximum: number }[] = [
    { key: 'liking', label: 'Liking', maximum: 9 },
    { key: 'acidity', label: 'Acidity', maximum: 5 },
    { key: 'bitterness', label: 'Bitterness', maximum: 5 },
    { key: 'sweetness', label: 'Sweetness', maximum: 5 },
    { key: 'body', label: 'Body', maximum: 5 }
  ];

  function formatScore(value: number): string {
    return Number.isInteger(value) ? String(value) : value.toFixed(1);
  }

  function deltaLabel(value: number): string {
    if (value === 0) return 'same as others';
    return `${value > 0 ? '+' : ''}${formatScore(value)} vs others`;
  }
</script>

<div class:compact class="rating-comparison">
  {#each metrics as metric}
    <div class="comparison-cell">
      <span>{metric.label}</span>
      <strong>{result.rating[metric.key]}<i>/{metric.maximum}</i></strong>
      <small>
        {#if result.peer_count > 0}
          Others {formatScore(result.peer_averages[metric.key])} · {deltaLabel(
            result.peer_deltas[metric.key]
          )}
        {:else}
          No other ratings yet
        {/if}
      </small>
    </div>
  {/each}
</div>

{#if !compact}
  <div class="flavor-comparison">
    <div>
      <span>{subjectLabel} chose</span>
      <p>
        {result.selected_flavors.length ? result.selected_flavors.join(' · ') : 'No flavor tags'}
      </p>
    </div>
    <div>
      <span>Other tasters chose</span>
      <p>
        {result.peer_count === 0
          ? 'No other ratings yet'
          : Object.keys(result.peer_flavor_counts).length
            ? Object.entries(result.peer_flavor_counts)
                .map(([name, count]) => `${name} ${count}`)
                .join(' · ')
            : 'No flavor tags from other tasters'}
      </p>
    </div>
  </div>
{/if}

<style>
  .rating-comparison {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 8px;
  }
  .comparison-cell {
    display: grid;
    gap: 4px;
    min-width: 0;
    padding: 13px;
    border: 1px solid var(--line);
    border-radius: 14px;
    background: color-mix(in srgb, var(--surface) 82%, var(--cream));
  }
  .comparison-cell > span,
  .flavor-comparison span {
    color: var(--muted);
    font-size: 0.69rem;
    font-weight: 800;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  .comparison-cell strong {
    font-size: 1.35rem;
  }
  .comparison-cell i {
    color: var(--muted);
    font-size: 0.72rem;
    font-style: normal;
    font-weight: 500;
  }
  .comparison-cell small {
    color: var(--muted);
    font-size: 0.72rem;
    line-height: 1.35;
  }
  .flavor-comparison {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
    margin-top: 10px;
  }
  .flavor-comparison > div {
    padding: 13px;
    border: 1px solid var(--line);
    border-radius: 14px;
  }
  .flavor-comparison p {
    margin: 6px 0 0;
    font-size: 0.84rem;
    line-height: 1.45;
  }
  .compact .comparison-cell {
    padding: 9px;
  }
  .rating-comparison.compact {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .compact .comparison-cell:first-child {
    grid-column: 1 / -1;
  }
  .compact .comparison-cell strong {
    font-size: 1rem;
  }
  .compact .comparison-cell small {
    font-size: 0.72rem;
  }
  @media (max-width: 720px) {
    .rating-comparison {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .comparison-cell:first-child {
      grid-column: 1 / -1;
    }
  }
  @media (max-width: 520px) {
    .flavor-comparison {
      grid-template-columns: 1fr;
    }
  }
</style>
