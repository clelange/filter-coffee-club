<script lang="ts">
  export let logoPath: string | null = null;
  export let brewingLogoPath: string | null = null;
  export let brewing = false;
  export let compact = false;
  export let large = false;

  const defaultLogo = '/brand/filter-coffee-club-logo-128.webp';
  const defaultLogoSrcset = [
    '/brand/filter-coffee-club-logo-128.webp 128w',
    '/brand/filter-coffee-club-logo-256.webp 256w',
    '/brand/filter-coffee-club-logo-384.webp 384w',
    '/brand/filter-coffee-club-logo-768.webp 768w'
  ].join(', ');

  let selectedLogoPath: string | null;
  let usesBundledLogo: boolean;
  $: selectedLogoPath = brewing && brewingLogoPath ? brewingLogoPath : logoPath;
  $: usesBundledLogo = !selectedLogoPath;
</script>

<img
  class:compact
  class:large
  src={selectedLogoPath ?? defaultLogo}
  srcset={usesBundledLogo ? defaultLogoSrcset : undefined}
  sizes={usesBundledLogo ? (large ? 'min(32vw, 340px)' : compact ? '56px' : '72px') : undefined}
  width={large ? 340 : compact ? 56 : 72}
  height={large ? 340 : compact ? 56 : 72}
  alt=""
/>

<style>
  img {
    width: 72px;
    height: 72px;
    flex: 0 0 auto;
    object-fit: contain;
  }
  .compact {
    width: 56px;
    height: 56px;
  }
  .large {
    width: min(32vw, 340px);
    height: auto;
    aspect-ratio: 1;
  }
</style>
