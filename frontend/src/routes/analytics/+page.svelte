<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import AnalyticsScatterPlot from '$lib/AnalyticsScatterPlot.svelte';
  import { loginPath } from '$lib/device';
  import { api, ensureSession } from '$lib/api';
  import ProfileLink from '$lib/ProfileLink.svelte';
  import type { components } from '$lib/generated-api';
  import type { AnalyticsAxisKey, AnalyticsRatingKey } from '$lib/types';

  type AnalyticsResponse = components['schemas']['AnalyticsResponse'];
  type AnalyticsScatterPoint = components['schemas']['AnalyticsPoint'];

  const axisOptions: { key: AnalyticsAxisKey; label: string }[] = [
    { key: 'ratio', label: 'Ratio' },
    { key: 'temperature_c', label: 'Temperature' },
    { key: 'grinder_setting', label: 'Grinder setting' },
    { key: 'total_brew_time_s', label: 'Brew time' },
    { key: 'target_flow_g_s', label: 'Target flow' },
    { key: 'overall_throughput_g_s', label: 'Overall throughput' }
  ];
  const ratingOptions: { key: AnalyticsRatingKey; label: string }[] = [
    { key: 'liking', label: 'Liking' },
    { key: 'acidity', label: 'Acidity' },
    { key: 'bitterness', label: 'Bitterness' },
    { key: 'sweetness', label: 'Sweetness' },
    { key: 'body', label: 'Body' }
  ];

  let data = $state<AnalyticsResponse | null>(null);
  let variable = $state<AnalyticsAxisKey>('ratio');
  let coffeeFilter = $state('all');
  let grinderFilter = $state('all');
  let mapCoffeeFilter = $state('');
  let mapGrinderFilter = $state('');
  let mapX = $state<AnalyticsAxisKey>('ratio');
  let mapY = $state<AnalyticsAxisKey>('temperature_c');
  let mapColor = $state<AnalyticsRatingKey>('liking');
  let error = $state('');

  function hasMeasurement(point: AnalyticsScatterPoint, key: AnalyticsAxisKey): boolean {
    return point[key] !== null && Number.isFinite(Number(point[key]));
  }

  function points(): AnalyticsScatterPoint[] {
    return data
      ? data.scatter.filter(
          (point) =>
            hasMeasurement(point, variable) &&
            (coffeeFilter === 'all' || String(point.coffee_id) === coffeeFilter) &&
            (variable !== 'grinder_setting' ||
              (grinderFilter !== 'all' && String(point.grinder_id) === grinderFilter))
        )
      : [];
  }
  function coffees(): { id: number; name: string }[] {
    if (!data) return [];
    return [
      ...new Map(
        data.scatter.map((point) => [point.coffee_id, { id: point.coffee_id, name: point.coffee }])
      ).values()
    ].sort((left, right) => left.name.localeCompare(right.name));
  }

  function grinderOptions(coffeeId: string | null = null): { id: number; name: string }[] {
    if (!data) return [];
    const candidates = coffeeId
      ? data.scatter.filter((point) => String(point.coffee_id) === coffeeId)
      : data.scatter;
    return [
      ...new Map(
        candidates.map((point) => [
          point.grinder_id,
          { id: point.grinder_id, name: point.grinder_name }
        ])
      ).values()
    ].sort((left, right) => left.name.localeCompare(right.name));
  }

  function mapNeedsGrinder(): boolean {
    return mapX === 'grinder_setting' || mapY === 'grinder_setting';
  }

  function mapPoints(): AnalyticsScatterPoint[] {
    if (!data || !mapCoffeeFilter || (mapNeedsGrinder() && !mapGrinderFilter)) return [];
    return data.scatter.filter(
      (point) =>
        String(point.coffee_id) === mapCoffeeFilter &&
        hasMeasurement(point, mapX) &&
        hasMeasurement(point, mapY) &&
        (!mapNeedsGrinder() || String(point.grinder_id) === mapGrinderFilter)
    );
  }

  function maxFlavor(): number {
    return Math.max(1, ...Object.values(data?.flavor_counts ?? {}));
  }

  function axisLabel(key: AnalyticsAxisKey, selectedGrinder = ''): string {
    const grinderUnit = data?.scatter.find(
      (point) => !selectedGrinder || String(point.grinder_id) === selectedGrinder
    )?.grinder_unit;
    return {
      ratio: 'Brew ratio (1:x)',
      temperature_c: 'Temperature (°C)',
      grinder_setting: `Grinder setting${grinderUnit ? ` (${grinderUnit})` : ''}`,
      total_brew_time_s: 'Brew time (s)',
      target_flow_g_s: 'Target flow (g/s)',
      overall_throughput_g_s: 'Overall throughput (g/s)'
    }[key];
  }

  function ratingLabel(key: AnalyticsRatingKey): string {
    return ratingOptions.find((option) => option.key === key)?.label ?? key;
  }

  function changeMapCoffee(event: Event): void {
    mapCoffeeFilter = (event.currentTarget as HTMLSelectElement).value;
    mapGrinderFilter = '';
  }

  onMount(async () => {
    if (!(await ensureSession())) {
      await goto(loginPath('/analytics'));
      return;
    }
    try {
      data = await api<AnalyticsResponse>('/analytics');
      if (coffees().length === 1) mapCoffeeFilter = String(coffees()[0].id);
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not load analytics.';
    }
  });
</script>

<svelte:head><title>Analytics · Filter Coffee Club</title></svelte:head>
<p class="eyebrow">Club observations</p>
<h1>Find the useful signal.</h1>
<p class="lede">
  Small samples stay visible. These patterns help form the next hypothesis; they do not prove
  causation.
</p>

{#if error}<p class="error section">{error}</p>{:else if !data}<div class="empty section">
    Calculating the current orbit…
  </div>{:else}
  <section class="metric-grid section">
    <article class="card metric">
      <strong>{data.counts.brews}</strong><span>completed brews</span>
    </article>
    <article class="card metric">
      <strong>{data.counts.ratings}</strong><span>tasting responses</span>
    </article>
    <article class="card metric">
      <strong>{data.counts.coffees}</strong><span>coffees observed</span>
    </article>
  </section>
  <div class="dashboard section">
    <div class="chart-stack">
      <section class="panel chart-panel">
        <div class="chart-heading">
          <div>
            <p class="eyebrow">Recipe comparison</p>
            <h2>Settings versus liking</h2>
          </div>
          <div class="chart-filters">
            <label
              >Coffee<select bind:value={coffeeFilter}
                ><option value="all">All coffees</option>{#each coffees() as coffee}<option
                    value={String(coffee.id)}>{coffee.name}</option
                  >{/each}</select
              ></label
            ><label
              >Horizontal axis<select bind:value={variable}
                >{#each axisOptions as option}<option value={option.key}>{option.label}</option
                  >{/each}</select
              ></label
            >{#if variable === 'grinder_setting'}<label
                >Grinder<select bind:value={grinderFilter}
                  ><option value="all">Choose one grinder</option
                  >{#each grinderOptions() as grinder}<option value={String(grinder.id)}
                      >{grinder.name}</option
                    >{/each}</select
                ></label
              >{/if}
          </div>
        </div>
        {#if points().length === 0}<div class="empty">
            {variable === 'grinder_setting' && grinderFilter === 'all'
              ? 'Choose one grinder before comparing its settings.'
              : 'No rated brews have this measurement yet.'}
          </div>{:else}<AnalyticsScatterPlot
            points={points()}
            xKey={variable}
            yKey="liking"
            xLabel={axisLabel(variable, grinderFilter === 'all' ? '' : grinderFilter)}
            yLabel="Liking (1–9)"
          />{/if}
        <p class="hint">
          Each circle is one brew; larger circles have more ratings. Filter grinder-setting views to
          one grinder before interpreting them. Observational, not causal.
        </p>
      </section>

      <section class="panel chart-panel recipe-map">
        <div class="chart-heading">
          <div>
            <p class="eyebrow">Within one coffee</p>
            <h2>Recipe map</h2>
          </div>
          <div class="chart-filters map-filters">
            <label
              >Map coffee<select value={mapCoffeeFilter} onchange={changeMapCoffee}
                ><option value="">Choose a coffee</option>{#each coffees() as coffee}<option
                    value={String(coffee.id)}>{coffee.name}</option
                  >{/each}</select
              ></label
            ><label
              >X axis<select bind:value={mapX}
                >{#each axisOptions as option}<option
                    value={option.key}
                    disabled={option.key === mapY}>{option.label}</option
                  >{/each}</select
              ></label
            ><label
              >Y axis<select bind:value={mapY}
                >{#each axisOptions as option}<option
                    value={option.key}
                    disabled={option.key === mapX}>{option.label}</option
                  >{/each}</select
              ></label
            ><label
              >Colour<select bind:value={mapColor}
                >{#each ratingOptions as option}<option value={option.key}>{option.label}</option
                  >{/each}</select
              ></label
            >{#if mapNeedsGrinder()}<label
                >Map grinder<select bind:value={mapGrinderFilter}
                  ><option value="">Choose a grinder</option
                  >{#each grinderOptions(mapCoffeeFilter) as grinder}<option
                      value={String(grinder.id)}>{grinder.name}</option
                    >{/each}</select
                ></label
              >{/if}
          </div>
        </div>
        {#if !mapCoffeeFilter}<div class="empty">
            Choose one coffee to compare recipes without mixing different beans.
          </div>{:else if mapNeedsGrinder() && !mapGrinderFilter}<div class="empty">
            Choose one grinder before comparing grinder settings.
          </div>{:else if mapPoints().length === 0}<div class="empty">
            No rated brews have both selected measurements yet.
          </div>{:else}<AnalyticsScatterPlot
            points={mapPoints()}
            xKey={mapX}
            yKey={mapY}
            xLabel={axisLabel(mapX, mapGrinderFilter)}
            yLabel={axisLabel(mapY, mapGrinderFilter)}
            colorKey={mapColor}
            colorLabel={ratingLabel(mapColor)}
          />{/if}
        <p class="hint">
          Colour shows the brew’s average rating; the detail panel also shows the individual min–max
          range. Points with identical values are offset slightly, while their detail values stay
          exact. Sensory measures describe intensity, not quality. Observational, not causal.
        </p>
      </section>
    </div>
    <aside class="stack">
      <section class="card">
        <p class="eyebrow">Qualified favorites</p>
        <h2>Top coffees</h2>
        {#if data.top_coffees.length === 0}<p class="muted">
            A coffee needs at least three ratings to enter the ranking.
          </p>{:else}<ol class="ranking">
            {#each data.top_coffees as coffee}<li>
                <span>{coffee.name}<small>{coffee.ratings} ratings</small></span><strong
                  >{coffee.average}</strong
                >
              </li>{/each}
          </ol>{/if}
      </section>
      <section class="card">
        <p class="eyebrow">Repeatable signals</p>
        <h2>Top recipes</h2>
        {#if data.top_recipes.length === 0}<p class="muted">
            A recipe needs at least three ratings to enter the ranking.
          </p>{:else}<ol class="ranking">
            {#each data.top_recipes as recipe}<li>
                <a href={`/brews/${recipe.brew_id}`}
                  ><span
                    >{recipe.name}<small>{recipe.recipe} · {recipe.ratings} ratings</small></span
                  ><strong>{recipe.average}</strong></a
                >
              </li>{/each}
          </ol>{/if}
      </section>
      <section class="card">
        <p class="eyebrow">Tasting vocabulary</p>
        <h2>Frequent notes</h2>
        <div class="bars">
          {#each Object.entries(data.flavor_counts) as [name, count]}<div>
              <span>{name}<b>{count}</b></span><i style={`width:${(count / maxFlavor()) * 100}%`}
              ></i>
            </div>{/each}
        </div>
      </section>
      <section class="card">
        <p class="eyebrow">Operators</p>
        <div class="operator-list">
          {#each data.operator_counts as operator}<span
              ><ProfileLink profileId={operator.profile_id} displayName={operator.display_name} /><b
                >{operator.brew_count} brew{operator.brew_count === 1 ? '' : 's'}</b
              ></span
            >{/each}
        </div>
      </section>
    </aside>
  </div>
{/if}

<style>
  .metric-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 14px;
  }
  .dashboard {
    display: grid;
    grid-template-columns: minmax(0, 1.6fr) minmax(280px, 0.7fr);
    gap: 18px;
    align-items: start;
  }
  .chart-stack {
    display: grid;
    gap: 18px;
    min-width: 0;
  }
  .chart-panel {
    min-width: 0;
  }
  .chart-heading {
    display: flex;
    justify-content: space-between;
    align-items: start;
    gap: 20px;
  }
  .chart-filters {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    justify-content: flex-end;
  }
  .chart-heading label {
    min-width: 180px;
  }
  .chart-filters select {
    min-width: 0;
  }
  .recipe-map {
    border-color: color-mix(in srgb, var(--cyan) 32%, var(--line));
  }
  .ranking {
    margin: 0;
    padding-left: 24px;
  }
  .ranking li {
    padding: 10px 0;
    border-bottom: 1px solid var(--line);
  }
  .ranking li,
  .ranking li > a,
  .ranking span,
  .operator-list span {
    display: flex;
    justify-content: space-between;
    gap: 10px;
  }
  .ranking li > a {
    width: 100%;
    color: inherit;
    text-decoration: none;
  }
  .ranking span {
    display: grid;
  }
  .ranking small {
    color: var(--muted);
  }
  .ranking strong {
    font-size: 1.4rem;
  }
  .bars {
    display: grid;
    gap: 11px;
  }
  .bars div > span {
    display: flex;
    justify-content: space-between;
    font-size: 0.82rem;
  }
  .bars i {
    display: block;
    height: 7px;
    margin-top: 4px;
    border-radius: 999px;
    background: var(--amber);
  }
  .operator-list {
    display: grid;
    gap: 10px;
  }
  .operator-list b {
    color: var(--muted);
    font-size: 0.8rem;
  }
  @media (max-width: 840px) {
    .dashboard {
      grid-template-columns: 1fr;
    }
    .metric-grid {
      grid-template-columns: 1fr 1fr;
    }
    .chart-heading {
      display: grid;
    }
    .chart-filters {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      justify-content: stretch;
      width: 100%;
    }
    .chart-heading label {
      min-width: 0;
    }
  }
  @media (max-width: 500px) {
    .metric-grid,
    .chart-filters {
      grid-template-columns: 1fr;
    }
  }
</style>
