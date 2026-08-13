<script lang="ts">
  export let logoPath: string | null = null;
  export let compact = false;
  export let large = false;

  const defaultLogo = '/brand/filter-coffee-club-logo-128.webp';
  const defaultLogoSrcset = [
    '/brand/filter-coffee-club-logo-128.webp 128w',
    '/brand/filter-coffee-club-logo-256.webp 256w',
    '/brand/filter-coffee-club-logo-384.webp 384w',
    '/brand/filter-coffee-club-logo-768.webp 768w'
  ].join(', ');
</script>

<img
  class:compact
  class:large
  src={logoPath ?? defaultLogo}
  srcset={logoPath ? undefined : defaultLogoSrcset}
  sizes={logoPath ? undefined : large ? 'min(32vw, 340px)' : compact ? '56px' : '72px'}
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
