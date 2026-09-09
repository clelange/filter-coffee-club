<script lang="ts">
  import { formatTime } from '$lib/api';
  import { formatCatalogDate, formatCatalogNumber as number } from '$lib/catalog';
  import type { components } from '$lib/generated-api';
  type RatedBrewInsight = components['schemas']['RatedBrewInsight'];

  export let result: RatedBrewInsight | null = null;
  export let available = true;
  export let minimumRatings = 3;
  export let coffeeName = '';
</script>

<section class="best-brew card" aria-label="Best-rated brew for this coffee">
  <div class="best-heading">
    <div>
      <p class="eyebrow">
        {coffeeName || result?.brew.coffee_name || 'A starting point for your next brew'}
      </p>
      <h3>Best-rated brew for this coffee</h3>
    </div>
    {#if result}<strong class="best-score"
        >{number(result.aggregate.averages?.liking ?? null)}<small> / 9 liking</small></strong
      >{/if}
  </div>
  {#if result}
    {@const brew = result.brew}
    <p class="hint">
      Brew #{brew.id} · {formatCatalogDate(brew.completed_at)} · {result.aggregate.count} ratings on one
      brew.
    </p>
    <dl>
      <div>
        <dt>Coffee / water</dt>
        <dd>{number(brew.dose_g)} g / {number(brew.water_g)} g · 1:{number(brew.ratio)}</dd>
      </div>
      <div>
        <dt>Grinder</dt>
        <dd>{brew.grinder_name} · {number(brew.grinder_setting)} {brew.grinder_unit}</dd>
      </div>
      <div>
        <dt>Temperature</dt>
        <dd>{number(brew.temperature_c)} °C</dd>
      </div>
      <div>
        <dt>Dripper / filter</dt>
        <dd>{brew.dripper_name ?? 'Not recorded'} / {brew.filter_name ?? 'Not recorded'}</dd>
      </div>
      <div>
        <dt>Bloom</dt>
        <dd>
          {number(brew.bloom_water_g ?? null, ' g')} · {number(brew.bloom_time_s ?? null, ' s')}
        </dd>
      </div>
      <div>
        <dt>Pours / target flow</dt>
        <dd>{number(brew.pour_count ?? null)} / {number(brew.target_flow_g_s ?? null, ' g/s')}</dd>
      </div>
      <div>
        <dt>Recorded brew time</dt>
        <dd>{formatTime(brew.total_brew_time_s)}</dd>
      </div>
    </dl>
    {#if brew.technique_note}<p class="technique">{brew.technique_note}</p>{/if}
    <p class="hint">
      Highest average liking among brews with at least {minimumRatings} ratings. Ties use more ratings,
      then the newest brew record. This is one observed result; repeatability has not been established.
    </p>
    <div class="actions">
      {#if available}<a class="button" href={`/brews/new?repeat=${brew.id}`}>Use these settings</a
        >{:else}<span class="hint">This bag is no longer available for brewing.</span>{/if}
      <a class="button secondary" href={`/brews/${brew.id}`}>View brew</a>
    </div>
  {:else}
    <p class="muted">
      No brew of this coffee has {minimumRatings} ratings yet. All rated brews remain available for comparison
      below.
    </p>
  {/if}
</section>

<style>
  .best-brew {
    display: grid;
    gap: 14px;
    min-width: 0;
    border-color: var(--cyan);
  }
  .best-brew p,
  .best-brew h3 {
    margin: 0;
  }
  .best-brew h3 {
    font-size: 1.3rem;
  }
  .best-heading {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    gap: 12px;
  }
  .best-score {
    font-size: 1.8rem;
    white-space: nowrap;
  }
  .best-score small {
    color: var(--muted);
    font-size: 0.8rem;
  }
  dl {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
    margin: 0;
  }
  dt {
    font-size: 0.75rem;
    color: var(--muted);
  }
  dd {
    margin: 3px 0 0;
    font-weight: 700;
    overflow-wrap: anywhere;
  }
  .technique {
    white-space: pre-wrap;
  }
  @media (max-width: 520px) {
    dl {
      grid-template-columns: 1fr;
    }
  }
</style>
