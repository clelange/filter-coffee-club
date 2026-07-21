<script lang="ts">
  import type { components } from '$lib/generated-api';
  import type { AnalyticsAxisKey, AnalyticsRatingKey } from '$lib/types';

  type AnalyticsScatterPoint = components['schemas']['AnalyticsPoint'];
  type PlotKey = AnalyticsAxisKey | 'liking';
  interface ScaleSpec {
    minimum: number;
    maximum: number;
    ticks: number[];
  }

  export let points: AnalyticsScatterPoint[];
  export let xKey: PlotKey;
  export let yKey: PlotKey;
  export let xLabel: string;
  export let yLabel: string;
  export let colorKey: AnalyticsRatingKey | null = null;
  export let colorLabel = '';

  const width = 680;
  const height = 410;
  const left = 76;
  const right = 24;
  const top = 24;
  const bottom = 72;
  const viridis = ['#440154', '#3b528b', '#21918c', '#5ec962', '#fde725'];
  let activePoint: AnalyticsScatterPoint | null = null;
  let touchPointId: number | null = null;
  let touchPointWasActive = false;
  let xScale: ScaleSpec;
  let yScale: ScaleSpec;
  let plottedPoints: { point: AnalyticsScatterPoint; cx: number; cy: number }[];

  $: if (activePoint && !points.some((point) => point.brew_id === activePoint?.brew_id)) {
    activePoint = null;
    touchPointId = null;
    touchPointWasActive = false;
  }
  $: xScale = scaleSpec(xKey, points);
  $: yScale = scaleSpec(yKey, points);
  $: plottedPoints = displayPoints(points, xKey, yKey, xScale, yScale);

  function value(point: AnalyticsScatterPoint, key: PlotKey): number {
    return key === 'liking' ? point.liking : Number(point[key]);
  }

  function niceStep(range: number, targetTicks = 5): number {
    const rough = range / Math.max(1, targetTicks - 1);
    const power = 10 ** Math.floor(Math.log10(rough));
    const fraction = rough / power;
    const niceFraction = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10;
    return niceFraction * power;
  }

  function scaleSpec(key: PlotKey, sourcePoints: AnalyticsScatterPoint[]): ScaleSpec {
    if (key === 'liking') return { minimum: 1, maximum: 9, ticks: [1, 3, 5, 7, 9] };
    const values = sourcePoints.map((point) => value(point, key));
    if (!values.length) return { minimum: 0, maximum: 1, ticks: [0, 0.25, 0.5, 0.75, 1] };
    let minimum = Math.min(...values);
    let maximum = Math.max(...values);
    if (minimum === maximum) {
      const padding = Math.max(Math.abs(minimum) * 0.05, 0.5);
      minimum -= padding;
      maximum += padding;
    } else {
      const padding = (maximum - minimum) * 0.06;
      minimum -= padding;
      maximum += padding;
    }
    const step = niceStep(maximum - minimum);
    const niceMinimum = Math.floor(minimum / step) * step;
    const niceMaximum = Math.ceil(maximum / step) * step;
    const ticks: number[] = [];
    for (let tick = niceMinimum; tick <= niceMaximum + step / 2; tick += step) {
      ticks.push(Number(tick.toPrecision(12)));
    }
    return { minimum: niceMinimum, maximum: niceMaximum, ticks };
  }

  function position(raw: number, scale: ScaleSpec, start: number, end: number): number {
    return start + ((raw - scale.minimum) / (scale.maximum - scale.minimum)) * (end - start);
  }

  function formatNumber(raw: number): string {
    return raw.toLocaleString(undefined, { maximumFractionDigits: 4 });
  }

  function formatTick(raw: number, scale: ScaleSpec): string {
    const step = Math.abs((scale.ticks[1] ?? scale.maximum) - (scale.ticks[0] ?? scale.minimum));
    const fractionDigits = step > 0 ? Math.max(0, Math.min(6, -Math.floor(Math.log10(step)))) : 0;
    return raw.toLocaleString(undefined, { maximumFractionDigits: fractionDigits });
  }

  function displayPoints(
    sourcePoints: AnalyticsScatterPoint[],
    selectedX: PlotKey,
    selectedY: PlotKey,
    selectedXScale: ScaleSpec,
    selectedYScale: ScaleSpec
  ): { point: AnalyticsScatterPoint; cx: number; cy: number }[] {
    const groups = new Map<string, AnalyticsScatterPoint[]>();
    for (const point of sourcePoints) {
      const key = `${value(point, selectedX)}|${value(point, selectedY)}`;
      groups.set(key, [...(groups.get(key) ?? []), point]);
    }
    return sourcePoints.map((point) => {
      const group = groups.get(`${value(point, selectedX)}|${value(point, selectedY)}`) ?? [point];
      const index = group.findIndex((item) => item.brew_id === point.brew_id);
      const offsetRadius = group.length > 1 ? Math.min(10, 4 + group.length) : 0;
      const angle = (index / group.length) * Math.PI * 2 - Math.PI / 2;
      return {
        point,
        cx:
          position(value(point, selectedX), selectedXScale, left, width - right) +
          Math.cos(angle) * offsetRadius,
        cy:
          position(value(point, selectedY), selectedYScale, height - bottom, top) +
          Math.sin(angle) * offsetRadius
      };
    });
  }

  function interpolateColor(raw: number): string {
    if (!colorKey) return 'var(--cyan)';
    const minimum = colorKey === 'liking' ? 1 : 0;
    const maximum = colorKey === 'liking' ? 9 : 5;
    const normalized = Math.max(0, Math.min(1, (raw - minimum) / (maximum - minimum)));
    const scaled = normalized * (viridis.length - 1);
    const index = Math.min(viridis.length - 2, Math.floor(scaled));
    const fraction = scaled - index;
    const start = viridis[index];
    const end = viridis[index + 1];
    const channels = [1, 3, 5].map((offset) => {
      const startValue = Number.parseInt(start.slice(offset, offset + 2), 16);
      const endValue = Number.parseInt(end.slice(offset, offset + 2), 16);
      return Math.round(startValue + (endValue - startValue) * fraction)
        .toString(16)
        .padStart(2, '0');
    });
    return `#${channels.join('')}`;
  }

  function detailLabel(point: AnalyticsScatterPoint): string {
    const coordinate = `${xLabel} ${formatNumber(value(point, xKey))}; ${yLabel} ${formatNumber(value(point, yKey))}`;
    if (!colorKey) {
      const metric = point.rating_metrics.liking;
      return `${point.coffee}. ${coordinate}. Liking average ${metric.average}, range ${metric.minimum} to ${metric.maximum}, from ${point.ratings} ratings.`;
    }
    const metric = point.rating_metrics[colorKey];
    return `${point.coffee}. ${coordinate}. ${colorLabel} average ${metric.average}, range ${metric.minimum} to ${metric.maximum}, from ${point.ratings} ratings.`;
  }

  function select(point: AnalyticsScatterPoint): void {
    activePoint = point;
  }

  function preparePointer(event: PointerEvent, point: AnalyticsScatterPoint): void {
    if (event.pointerType !== 'touch') return;
    touchPointId = point.brew_id;
    touchPointWasActive = activePoint?.brew_id === point.brew_id;
    select(point);
  }

  function activate(event: MouseEvent, point: AnalyticsScatterPoint): void {
    if (touchPointId === point.brew_id) {
      if (!touchPointWasActive) event.preventDefault();
      touchPointId = null;
      touchPointWasActive = false;
      return;
    }
    if (activePoint?.brew_id !== point.brew_id) {
      event.preventDefault();
      select(point);
    }
  }
</script>

<div class="plot-scroll" data-testid="analytics-plot">
  <svg
    viewBox={`0 0 ${width} ${height}`}
    role="group"
    aria-label={`Interactive scatter plot of ${xLabel} versus ${yLabel}${colorKey ? `, coloured by ${colorLabel}` : ''}`}
  >
    {#each yScale.ticks as tick}
      <line
        class="grid"
        x1={left}
        y1={position(tick, yScale, height - bottom, top)}
        x2={width - right}
        y2={position(tick, yScale, height - bottom, top)}
      />
      <text class="tick y-tick" x={left - 12} y={position(tick, yScale, height - bottom, top) + 4}
        >{formatTick(tick, yScale)}</text
      >
    {/each}
    {#each xScale.ticks as tick}
      <line
        class="grid"
        x1={position(tick, xScale, left, width - right)}
        y1={top}
        x2={position(tick, xScale, left, width - right)}
        y2={height - bottom}
      />
      <text
        class="tick x-tick"
        x={position(tick, xScale, left, width - right)}
        y={height - bottom + 22}>{formatTick(tick, xScale)}</text
      >
    {/each}
    <line
      class="axis-line"
      x1={left}
      y1={height - bottom}
      x2={width - right}
      y2={height - bottom}
    />
    <line class="axis-line" x1={left} y1={top} x2={left} y2={height - bottom} />
    {#each plottedPoints as item (item.point.brew_id)}
      <a
        class="plot-point"
        class:selected={activePoint?.brew_id === item.point.brew_id}
        data-brew-id={item.point.brew_id}
        href={`/brews/${item.point.brew_id}`}
        tabindex="0"
        aria-label={detailLabel(item.point)}
        on:focus={() => select(item.point)}
        on:mouseenter={() => select(item.point)}
        on:pointerdown={(event) => preparePointer(event, item.point)}
        on:click={(event) => activate(event, item.point)}
      >
        <circle
          cx={item.cx}
          cy={item.cy}
          r={6 + Math.min(item.point.ratings, 6)}
          fill={colorKey
            ? interpolateColor(item.point.rating_metrics[colorKey].average)
            : 'var(--cyan)'}
        >
          <title>{detailLabel(item.point)}</title>
        </circle>
      </a>
    {/each}
    <text class="axis-title x-title" x={(left + width - right) / 2} y={height - 14}>{xLabel}</text>
    <text class="axis-title y-title" x={-(top + height - bottom) / 2} y="20" transform="rotate(-90)"
      >{yLabel}</text
    >
  </svg>
</div>

{#if colorKey}
  <div
    class="legend"
    data-testid="color-legend"
    role="group"
    aria-label={`${colorLabel} average colour scale from ${colorKey === 'liking' ? 1 : 0} to ${colorKey === 'liking' ? 9 : 5}`}
  >
    <span>{colorKey === 'liking' ? 1 : 0}</span><i></i><span>{colorKey === 'liking' ? 9 : 5}</span
    ><strong>{colorLabel} average</strong>
  </div>
{/if}

<div class="point-details" data-testid="point-details" aria-live="polite">
  {#if activePoint}
    <div>
      <span>Selected brew</span><strong>{activePoint.coffee}</strong>
      <small
        >{xLabel}: {formatNumber(value(activePoint, xKey))} · {yLabel}: {formatNumber(
          value(activePoint, yKey)
        )}</small
      >
      {#if colorKey}
        {@const metric = activePoint.rating_metrics[colorKey]}
        <small
          >{colorLabel}: {formatNumber(metric.average)} average · {metric.minimum}–{metric.maximum}
          range · {activePoint.ratings} rating{activePoint.ratings === 1 ? '' : 's'}</small
        >
      {:else}
        {@const metric = activePoint.rating_metrics.liking}
        <small
          >Liking: {formatNumber(metric.average)} average · {metric.minimum}–{metric.maximum} range ·
          {activePoint.ratings} rating{activePoint.ratings === 1 ? '' : 's'}</small
        >
      {/if}
    </div>
    <a class="button secondary" href={`/brews/${activePoint.brew_id}`}>Open brew</a>
  {:else}
    <p>Focus, hover, or tap a point to inspect its measurements.</p>
  {/if}
</div>

<style>
  .plot-scroll {
    width: 100%;
    overflow-x: auto;
    overscroll-behavior-inline: contain;
  }
  svg {
    display: block;
    width: 100%;
    min-width: 620px;
    height: auto;
  }
  line {
    vector-effect: non-scaling-stroke;
  }
  .grid {
    stroke: var(--line);
    stroke-width: 1;
    stroke-dasharray: 3 5;
  }
  .axis-line {
    stroke: color-mix(in srgb, var(--ink) 55%, var(--line));
    stroke-width: 1.5;
  }
  text {
    fill: var(--muted);
    font-size: 12px;
  }
  .tick {
    font-variant-numeric: tabular-nums;
  }
  .x-tick,
  .axis-title {
    text-anchor: middle;
  }
  .y-tick {
    text-anchor: end;
  }
  .axis-title {
    fill: var(--ink);
    font-weight: 800;
  }
  .plot-point circle {
    fill-opacity: 0.82;
    stroke: var(--surface);
    stroke-width: 2.5;
    vector-effect: non-scaling-stroke;
    transition:
      stroke 120ms ease,
      stroke-width 120ms ease,
      fill-opacity 120ms ease;
  }
  .plot-point:hover circle,
  .plot-point:focus circle,
  .plot-point.selected circle {
    fill-opacity: 1;
    stroke: var(--ink);
    stroke-width: 3.5;
  }
  .plot-point:focus {
    outline: none;
  }
  .legend {
    display: grid;
    grid-template-columns: auto minmax(120px, 220px) auto;
    align-items: center;
    justify-content: center;
    gap: 8px;
    margin: -6px 0 12px;
    color: var(--muted);
    font-size: 0.75rem;
    font-variant-numeric: tabular-nums;
  }
  .legend i {
    height: 10px;
    border: 1px solid color-mix(in srgb, var(--ink) 18%, transparent);
    border-radius: 999px;
    background: linear-gradient(90deg, #440154, #3b528b, #21918c, #5ec962, #fde725);
  }
  .legend strong {
    grid-column: 1 / -1;
    text-align: center;
    font-size: 0.7rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }
  .point-details {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    min-height: 76px;
    padding: 13px 15px;
    border: 1px solid var(--line);
    border-radius: 14px;
    background: color-mix(in srgb, var(--cream) 72%, var(--surface));
  }
  .point-details div {
    display: grid;
    gap: 3px;
    min-width: 0;
  }
  .point-details span {
    color: var(--muted);
    font-size: 0.66rem;
    font-weight: 800;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  .point-details strong,
  .point-details small {
    overflow-wrap: anywhere;
  }
  .point-details small,
  .point-details p {
    color: var(--muted);
    line-height: 1.4;
  }
  .point-details p {
    margin: 0;
  }
  .point-details .button {
    flex: 0 0 auto;
    padding: 9px 12px;
    font-size: 0.78rem;
  }
  @media (max-width: 560px) {
    .point-details {
      display: grid;
    }
    .point-details .button {
      width: fit-content;
    }
  }
</style>
