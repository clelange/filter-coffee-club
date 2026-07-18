<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { api, ensureSession } from '$lib/api';

  interface Point { brew_id:number; coffee_id:number; coffee:string; liking:number; ratings:number; ratio:number; temperature_c:number; grinder_id:number; grinder_name:string; grinder_setting:number; total_brew_time_s:number|null; target_flow_g_s:number|null; }
  interface RankedRecipe { brew_id:number;name:string;recipe:string;average:number;ratings:number; }
  interface Analytics { counts:{brews:number;ratings:number;coffees:number}; top_coffees:{coffee_id:number;name:string;average:number;ratings:number}[]; top_recipes:RankedRecipe[]; flavor_counts:Record<string,number>; operator_counts:Record<string,number>; scatter:Point[]; }

  let data = $state<Analytics | null>(null);
  let variable: 'ratio'|'temperature_c'|'grinder_setting'|'total_brew_time_s'|'target_flow_g_s' = $state('ratio');
  let coffeeFilter = $state('all');
  let grinderFilter = $state('all');
  let error = $state('');
  function points(): Point[] { return data ? data.scatter.filter((point) => point[variable] !== null && (coffeeFilter==='all'||String(point.coffee_id)===coffeeFilter) && (variable!=='grinder_setting'||(grinderFilter!=='all'&&String(point.grinder_id)===grinderFilter))) : []; }
  function coffees(): {id:number;name:string}[] { return data ? [...new Map(data.scatter.map(point=>[point.coffee_id,{id:point.coffee_id,name:point.coffee}])).values()] : []; }
  function grinders(): {id:number;name:string}[] { return data ? [...new Map(data.scatter.map(point=>[point.grinder_id,{id:point.grinder_id,name:point.grinder_name}])).values()] : []; }
  function xValues(): number[] { return points().map((point) => Number(point[variable])); }
  function minX(): number { const values=xValues(); return values.length ? Math.min(...values) : 0; }
  function maxX(): number { const values=xValues(); return values.length ? Math.max(...values) : 1; }
  function maxFlavor(): number { return Math.max(1, ...Object.values(data?.flavor_counts ?? {})); }

  onMount(async () => {
    if (!(await ensureSession())) { await goto('/login?next=/analytics'); return; }
    try { data = await api<Analytics>('/analytics'); } catch (caught) { error = caught instanceof Error ? caught.message : 'Could not load analytics.'; }
  });
  function x(value: number): number { return maxX() === minX() ? 300 : 45 + ((value-minX())/(maxX()-minX()))*510; }
  function y(value: number): number { return 300 - ((value-1)/8)*250; }
  function variableLabel(): string { return ({ratio:'Ratio',temperature_c:'Temperature °C',grinder_setting:'Grinder setting',total_brew_time_s:'Brew time seconds',target_flow_g_s:'Target flow g/s'})[variable]; }
</script>

<svelte:head><title>Analytics · Filter Coffee Club</title></svelte:head>
<p class="eyebrow">Club observations</p><h1>Find the useful signal.</h1><p class="lede">Small samples stay visible. These patterns help form the next hypothesis; they do not prove causation.</p>

{#if error}<p class="error section">{error}</p>{:else if !data}<div class="empty section">Calculating the current orbit…</div>{:else}
  <section class="metric-grid section"><article class="card metric"><strong>{data.counts.brews}</strong><span>completed brews</span></article><article class="card metric"><strong>{data.counts.ratings}</strong><span>tasting responses</span></article><article class="card metric"><strong>{data.counts.coffees}</strong><span>coffees observed</span></article></section>
  <div class="dashboard section">
    <section class="panel chart-panel"><div class="chart-heading"><div><p class="eyebrow">Recipe comparison</p><h2>Settings versus liking</h2></div><div class="chart-filters"><label>Coffee<select bind:value={coffeeFilter}><option value="all">All coffees</option>{#each coffees() as coffee}<option value={String(coffee.id)}>{coffee.name}</option>{/each}</select></label><label>Horizontal axis<select bind:value={variable}><option value="ratio">Ratio</option><option value="temperature_c">Temperature</option><option value="grinder_setting">Grinder setting</option><option value="total_brew_time_s">Brew time</option><option value="target_flow_g_s">Target flow</option></select></label>{#if variable==='grinder_setting'}<label>Grinder<select bind:value={grinderFilter}><option value="all">Choose one grinder</option>{#each grinders() as grinder}<option value={String(grinder.id)}>{grinder.name}</option>{/each}</select></label>{/if}</div></div>
      {#if points().length === 0}<div class="empty">No rated brews have this measurement yet.</div>{:else}
        <svg viewBox="0 0 600 340" role="img" aria-label={`${variableLabel()} versus liking scatter plot`}>
          <line x1="45" y1="300" x2="570" y2="300" /><line x1="45" y1="40" x2="45" y2="300" />
          {#each [1,3,5,7,9] as tick}<text x="30" y={y(tick)+4}>{tick}</text><line class="grid" x1="45" y1={y(tick)} x2="570" y2={y(tick)} />{/each}
          {#each points() as point}<a href={`/brews/${point.brew_id}`}><circle cx={x(Number(point[variable]))} cy={y(point.liking)} r={6+Math.min(point.ratings,6)}><title>{point.coffee}: {point.liking}/9 from {point.ratings} ratings · {variableLabel()} {point[variable]}</title></circle></a>{/each}
          <text class="axis" x="300" y="332">{variableLabel()}</text><text class="axis y" x="15" y="175">Liking</text>
        </svg>
      {/if}
      <p class="hint">Each circle is one brew; larger circles have more ratings. Filter grinder-setting views to one grinder before interpreting them. Observational, not causal.</p>
    </section>
    <aside class="stack"><section class="card"><p class="eyebrow">Qualified favorites</p><h2>Top coffees</h2>{#if data.top_coffees.length === 0}<p class="muted">A coffee needs at least three ratings to enter the ranking.</p>{:else}<ol class="ranking">{#each data.top_coffees as coffee}<li><span>{coffee.name}<small>{coffee.ratings} ratings</small></span><strong>{coffee.average}</strong></li>{/each}</ol>{/if}</section>
      <section class="card"><p class="eyebrow">Repeatable signals</p><h2>Top recipes</h2>{#if data.top_recipes.length === 0}<p class="muted">A recipe needs at least three ratings to enter the ranking.</p>{:else}<ol class="ranking">{#each data.top_recipes as recipe}<li><a href={`/brews/${recipe.brew_id}`}><span>{recipe.name}<small>{recipe.recipe} · {recipe.ratings} ratings</small></span><strong>{recipe.average}</strong></a></li>{/each}</ol>{/if}</section>
      <section class="card"><p class="eyebrow">Tasting vocabulary</p><h2>Frequent notes</h2><div class="bars">{#each Object.entries(data.flavor_counts) as [name,count]}<div><span>{name}<b>{count}</b></span><i style={`width:${(count/maxFlavor())*100}%`}></i></div>{/each}</div></section>
      <section class="card"><p class="eyebrow">Operators</p><div class="operator-list">{#each Object.entries(data.operator_counts) as [name,count]}<span>{name}<b>{count} brew{count===1?'':'s'}</b></span>{/each}</div></section>
    </aside>
  </div>
{/if}

<style>
  .metric-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:14px; }.dashboard { display:grid; grid-template-columns:minmax(0,1.6fr) minmax(280px,.7fr); gap:18px; align-items:start; }
  .chart-heading { display:flex; justify-content:space-between; align-items:start; gap:20px; }.chart-filters{display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-end}.chart-heading label { min-width:180px; }
  svg { width:100%; min-height:340px; }svg line { stroke:var(--line); stroke-width:2; }svg .grid { stroke-width:1; stroke-dasharray:3 5; }svg circle { fill:var(--cyan); fill-opacity:.72; stroke:var(--surface); stroke-width:2; }svg text { fill:var(--muted); font-size:11px; }svg .axis { text-anchor:middle; font-weight:700; }.axis.y { transform:rotate(-90deg); transform-origin:15px 175px; }
  .ranking { margin:0; padding-left:24px; }.ranking li { padding:10px 0;border-bottom:1px solid var(--line); }.ranking li,.ranking li>a,.ranking span,.operator-list span { display:flex; justify-content:space-between; gap:10px; }.ranking li>a{width:100%;color:inherit;text-decoration:none}.ranking span { display:grid; }.ranking small { color:var(--muted); }.ranking strong { font-size:1.4rem; }
  .bars { display:grid; gap:11px; }.bars div>span { display:flex; justify-content:space-between; font-size:.82rem; }.bars i { display:block; height:7px; margin-top:4px; border-radius:999px; background:var(--amber); }.operator-list { display:grid; gap:10px; }.operator-list b { color:var(--muted); font-size:.8rem; }
  @media(max-width:840px){.dashboard{grid-template-columns:1fr}.metric-grid{grid-template-columns:1fr 1fr}.chart-heading{display:grid}.chart-heading label{min-width:0}}@media(max-width:500px){.metric-grid{grid-template-columns:1fr}}
</style>
