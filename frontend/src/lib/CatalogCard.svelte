<script lang="ts">
  import CatalogPhoto from '$lib/CatalogPhoto.svelte';
  import CatalogUsageSummary from '$lib/CatalogUsageSummary.svelte';
  import type { CatalogUsageItem } from '$lib/types';

  export let href: string;
  export let photoPath: string | null;
  export let photoEndpoint: string;
  export let alt: string;
  export let eyebrow: string;
  export let title: string;
  export let metadata: string;
  export let notes: string | null = null;
  export let usage: CatalogUsageItem | null = null;
  export let beanFallback = false;
  export let primaryHref: string | null = null;
  export let primaryLabel = '';
</script>

<article class="catalog-card" data-testid="catalog-card">
  <a class="catalog-summary" {href} aria-label={`View details for ${title}`}>
    <CatalogPhoto {photoPath} {alt} endpoint={photoEndpoint} compact {beanFallback} />
    <div class="catalog-copy">
      <p class="eyebrow">{eyebrow}</p>
      <h3>{title}</h3>
      <p class="metadata">{metadata || 'Details not recorded yet'}</p>
      {#if notes}<p class="notes">{notes}</p>{/if}
      <CatalogUsageSummary {usage} />
    </div>
  </a>
  {#if primaryHref}
    <div class="catalog-actions">
      <a class="button small" href={primaryHref}>{primaryLabel}</a>
    </div>
  {/if}
</article>

<style>
  .catalog-card {
    display: flex;
    min-width: 0;
    min-height: 100%;
    flex-direction: column;
    overflow: hidden;
    border: 1px solid var(--line);
    border-radius: 22px;
    background: color-mix(in srgb, var(--surface) 96%, transparent);
    box-shadow: var(--shadow);
  }
  .catalog-summary {
    display: grid;
    flex: 1;
    gap: var(--catalog-gap-md, 16px);
    padding: var(--catalog-card-padding, 20px);
    color: var(--ink);
    text-decoration: none;
  }
  .catalog-summary:hover h3 {
    color: var(--cyan);
  }
  .catalog-copy {
    display: grid;
    align-content: start;
    gap: var(--catalog-gap-sm, 8px);
    min-width: 0;
  }
  .catalog-copy :global(p),
  h3 {
    margin: 0;
  }
  h3 {
    font-family: Georgia, 'Times New Roman', serif;
    font-size: clamp(1.32rem, 2.7vw, 1.75rem);
    letter-spacing: -0.025em;
    line-height: 1.08;
  }
  .eyebrow {
    color: var(--cyan);
    font-size: 0.72rem;
    font-weight: 850;
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }
  .metadata {
    color: var(--muted);
    line-height: 1.45;
  }
  .metadata {
    font-size: 0.92rem;
  }
  .notes {
    padding: 10px 12px;
    border-left: 3px solid var(--amber);
    background: var(--cream);
    font-size: 0.9rem;
    font-style: italic;
    line-height: 1.45;
  }
  .catalog-actions {
    display: flex;
    align-items: center;
    min-height: 72px;
    margin-top: auto;
    padding: 10px var(--catalog-card-padding, 20px) var(--catalog-card-padding, 20px);
  }
  @media (max-width: 600px) {
    .catalog-card {
      border-radius: 18px;
    }
  }
</style>
