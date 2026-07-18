<script lang="ts">
  export let logoPath: string | null = null;
  export let compact = false;
</script>

{#if logoPath}
  <img class:compact src={logoPath} alt="" />
{:else}
  <svg class:compact viewBox="0 0 76 76" aria-hidden="true">
    <circle class="orbit outer" cx="38" cy="38" r="31" />
    <ellipse class="orbit inner" cx="38" cy="38" rx="31" ry="17" transform="rotate(-24 38 38)" />
    <circle class="particle one" cx="63" cy="20" r="5" />
    <circle class="particle two" cx="10" cy="45" r="3" />
    <path class="dripper" d="M24 26h28l-6 24H30z" />
    <path class="rim" d="M22 26h32M31 55h14" />
    <path class="drop" d="M38 31c5 7 7 10 7 14a7 7 0 0 1-14 0c0-4 2-7 7-14z" />
  </svg>
{/if}

<style>
  svg,
  img {
    width: 64px;
    height: 64px;
    flex: 0 0 auto;
    object-fit: contain;
  }
  .compact {
    width: 48px;
    height: 48px;
  }
  .orbit {
    fill: none;
    stroke: var(--cyan);
    stroke-width: 2.5;
  }
  .outer {
    stroke-dasharray: 16 7;
  }
  .inner {
    opacity: 0.55;
  }
  .particle {
    fill: var(--amber);
  }
  .two {
    fill: var(--cyan);
  }
  .dripper {
    fill: var(--surface);
    stroke: var(--coffee);
    stroke-width: 2.5;
  }
  .rim {
    fill: none;
    stroke: var(--coffee);
    stroke-width: 3;
    stroke-linecap: round;
  }
  .drop {
    fill: var(--coffee);
  }
</style>
