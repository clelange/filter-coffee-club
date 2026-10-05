<script lang="ts">
  import { formatTime } from '$lib/api';
  import ProfileLink from '$lib/ProfileLink.svelte';
  import RatingComparison from '$lib/RatingComparison.svelte';
  import type { Brew, RatingComparison as RatingComparisonData } from '$lib/types';

  let {
    brew,
    comparison,
    profileId,
    repeatError,
    repeatDisabled = false,
    onrepeat
  }: {
    brew: Brew;
    comparison?: RatingComparisonData;
    profileId?: number;
    repeatError?: string;
    repeatDisabled?: boolean;
    onrepeat?: (brew: Brew) => void;
  } = $props();
</script>

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
        {#if profileId !== undefined}
          <a href={`/profiles/${profileId}#brew-${brew.id}`}>Full details →</a>
        {/if}
      </div>
      <RatingComparison result={comparison} compact />
    </div>
  {/if}
  {#if repeatError}<p class="error" role="alert">{repeatError}</p>{/if}
  <div class="actions">
    <a class="button small" href={`/brews/${brew.id}`}
      >{brew.status === 'completed'
        ? 'Open invitation'
        : brew.status === 'draft'
          ? 'Continue brew'
          : 'View record'}</a
    >
    {#if onrepeat && brew.status === 'completed'}
      <button
        class="button secondary"
        class:disabled={repeatDisabled}
        aria-disabled={repeatDisabled}
        onclick={() => {
          if (!repeatDisabled) onrepeat?.(brew);
        }}>Repeat</button
      >
    {/if}
  </div>
</article>

<style>
  .card-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 16px;
  }
  .card-top small {
    color: var(--muted);
  }
  h3 {
    margin: 22px 0 4px;
    font-size: 1.35rem;
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
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    font-size: 0.78rem;
  }
</style>
