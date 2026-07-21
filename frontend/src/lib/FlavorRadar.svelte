<script lang="ts">
  interface FlavorAxis {
    id: number;
    label: string;
    mentions: number;
    total: number;
  }

  export let axes: FlavorAxis[] = [];

  const center = 200;
  const radius = 145;
  const labelRadius = 160;
  const rings = [0.25, 0.5, 0.75, 1];
  const maximumLabelLength = 11;

  $: hasMentions = axes.some((axis) => axis.mentions > 0);
  $: accessibleLabel = axes.length
    ? `Broad flavour profile. ${axes
        .map(
          (axis) =>
            `${axis.label}: ${axis.mentions} of ${axis.total} ${axis.total === 1 ? 'taster' : 'tasters'} (${percentage(axis)}%)`
        )
        .join('. ')}.`
    : 'Broad flavour profile. No broad flavour categories are configured.';

  function share(axis: FlavorAxis): number {
    return axis.total > 0 ? axis.mentions / axis.total : 0;
  }

  function percentage(axis: FlavorAxis): number {
    return Math.round(share(axis) * 100);
  }

  function angle(index: number): number {
    return -Math.PI / 2 + (Math.PI * 2 * index) / axes.length;
  }

  function x(index: number, scale = 1, distance = radius): number {
    return center + Math.cos(angle(index)) * distance * scale;
  }

  function y(index: number, scale = 1, distance = radius): number {
    return center + Math.sin(angle(index)) * distance * scale;
  }

  function polygonPoints(scale: number): string {
    return axes.map((_, index) => `${x(index, scale)},${y(index, scale)}`).join(' ');
  }

  function dataPoints(): string {
    return axes.map((axis, index) => `${x(index, share(axis))},${y(index, share(axis))}`).join(' ');
  }

  function textAnchor(index: number): 'start' | 'middle' | 'end' {
    const horizontal = Math.cos(angle(index));
    if (horizontal > 0.25) return 'start';
    if (horizontal < -0.25) return 'end';
    return 'middle';
  }

  function truncateLabel(label: string): string {
    return label.length <= maximumLabelLength
      ? label
      : `${label.slice(0, maximumLabelLength - 1).trimEnd()}…`;
  }

  function labelLines(label: string): string[] {
    if (label.length <= maximumLabelLength) return [label];
    const breakAt = label.lastIndexOf(' ', maximumLabelLength);
    if (breakAt <= 0)
      return [
        truncateLabel(label.slice(0, maximumLabelLength)),
        truncateLabel(label.slice(maximumLabelLength))
      ];
    return [label.slice(0, breakAt), truncateLabel(label.slice(breakAt + 1))];
  }
</script>

<figure class="flavor-radar" data-testid="flavor-radar">
  {#if axes.length === 0}
    <div class="configuration-empty" role="status">No broad flavour categories configured.</div>
  {:else if axes.length < 3}
    <div class="category-bars" role="img" aria-label={accessibleLabel}>
      {#each axes as axis}
        <div class="category-bar">
          <span><strong>{axis.label}</strong><b>{percentage(axis)}%</b></span>
          <i><span style={`width:${percentage(axis)}%`}></span></i>
        </div>
      {/each}
    </div>
  {:else}
    <svg viewBox="-40 -20 480 440" role="img" aria-label={accessibleLabel}>
      {#each rings as ring}
        <polygon class="radar-ring" points={polygonPoints(ring)} />
        <text class="ring-label" x={center + 4} y={center - radius * ring - 4}>{ring * 100}%</text>
      {/each}

      {#each axes as axis, index}
        {@const lines = labelLines(axis.label)}
        <line class="radar-axis" x1={center} y1={center} x2={x(index)} y2={y(index)} />
        <text
          class="axis-label"
          x={x(index, 1, labelRadius)}
          y={y(index, 1, labelRadius) - (lines.length === 2 ? 12 : 7)}
          text-anchor={textAnchor(index)}
        >
          {#each lines as line, lineIndex}
            <tspan x={x(index, 1, labelRadius)} dy={lineIndex === 0 ? 0 : 15}>{line}</tspan>
          {/each}
        </text>
        <text
          class="axis-value"
          x={x(index, 1, labelRadius)}
          y={y(index, 1, labelRadius) + (lines.length === 2 ? 20 : 10)}
          text-anchor={textAnchor(index)}>{percentage(axis)}%</text
        >
      {/each}

      {#if hasMentions}
        <polygon class="radar-result" points={dataPoints()} />
        {#each axes as axis, index}
          {#if axis.mentions > 0}
            <circle
              class="radar-point"
              cx={x(index, share(axis))}
              cy={y(index, share(axis))}
              r="4.5"
            >
              <title
                >{axis.label}: {axis.mentions} of {axis.total}
                {axis.total === 1 ? 'taster' : 'tasters'} ({percentage(axis)}%)</title
              >
            </circle>
          {/if}
        {/each}
      {:else}
        <circle class="radar-zero" cx={center} cy={center} r="5" />
      {/if}
    </svg>
  {/if}
  {#if axes.length > 0}
    <figcaption>
      {#if !hasMentions}
        <strong>No broad flavour notes yet.</strong> The chart will grow as tasters add notes.
      {:else if axes.length < 3}
        Bar length shows the share of tasters who mentioned each broad category.
      {:else}
        Distance from the centre shows the share of tasters who mentioned each broad category.
      {/if}
    </figcaption>
  {/if}
</figure>

<style>
  .flavor-radar {
    display: grid;
    gap: 4px;
    margin: 4px 0 22px;
  }
  svg {
    display: block;
    width: 100%;
    height: auto;
    overflow: hidden;
  }
  .configuration-empty {
    padding: 18px;
    border: 1px dashed var(--line);
    border-radius: 12px;
    color: var(--muted);
    text-align: center;
  }
  .category-bars {
    display: grid;
    gap: 12px;
    padding: 10px 0;
  }
  .category-bar {
    display: grid;
    gap: 6px;
  }
  .category-bar > span {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    font-size: 0.86rem;
  }
  .category-bar b {
    flex: 0 0 auto;
    color: var(--muted);
  }
  .category-bar strong {
    min-width: 0;
    overflow-wrap: anywhere;
  }
  .category-bar i {
    height: 8px;
    overflow: hidden;
    border-radius: 999px;
    background: var(--cream);
  }
  .category-bar i span {
    display: block;
    height: 100%;
    border-radius: inherit;
    background: var(--cyan);
  }
  .radar-ring,
  .radar-axis {
    fill: none;
    stroke: var(--line);
    stroke-width: 1.5;
  }
  .radar-axis {
    stroke-dasharray: 3 4;
  }
  .ring-label {
    fill: var(--muted);
    font-size: 9px;
    font-weight: 650;
  }
  .axis-label {
    fill: var(--ink);
    font-size: 15px;
    font-weight: 800;
  }
  .axis-value {
    fill: var(--muted);
    font-size: 13px;
    font-weight: 700;
  }
  .radar-result {
    fill: color-mix(in srgb, var(--cyan) 22%, transparent);
    stroke: var(--cyan);
    stroke-linejoin: round;
    stroke-width: 3;
  }
  .radar-point {
    fill: var(--surface);
    stroke: var(--cyan);
    stroke-width: 3;
  }
  .radar-zero {
    fill: var(--surface);
    stroke: var(--muted);
    stroke-width: 2;
  }
  figcaption {
    color: var(--muted);
    font-size: 0.78rem;
    line-height: 1.45;
    text-align: center;
  }
  figcaption strong {
    color: var(--ink);
  }
  @media (max-width: 420px) {
    .axis-label {
      font-size: 14px;
    }
    .axis-value {
      font-size: 12px;
    }
  }
</style>
