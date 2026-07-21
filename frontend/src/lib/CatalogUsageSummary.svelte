<script lang="ts">
  import { formatCatalogDate } from '$lib/catalog';
  import type { CatalogUsageItem } from '$lib/types';

  export let usage: CatalogUsageItem | null = null;
</script>

<p class="usage-line" data-testid="usage-summary">
  {usage?.completed_brew_count ?? 0}
  {usage?.completed_brew_count === 1 ? 'completed brew' : 'completed brews'}
  <span aria-hidden="true">·</span>
  Last used {formatCatalogDate(usage?.last_completed_at)}
</p>

<style>
  .usage-line {
    margin: 0;
    padding-top: var(--catalog-gap-sm, 8px);
    color: var(--muted);
    font-size: 0.78rem;
    font-weight: 700;
    line-height: 1.45;
  }
  span {
    padding: 0 3px;
  }
</style>
