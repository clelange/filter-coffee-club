<script lang="ts">
  import { photoFramingStyle } from '#lib/photo-framing.ts';
  import type { PhotoFraming } from '#lib/types.ts';

  export let photoPath: string | null;
  export let photoFraming: PhotoFraming | null = null;
  export let alt: string;
  export let compact = false;
  export let beanFallback = false;
</script>

<div class:compact class="catalog-photo">
  <div class:framed={photoFraming} class="photo-frame">
    {#if photoPath}
      <img
        class:framed={photoFraming}
        src={photoPath}
        {alt}
        loading="lazy"
        decoding="async"
        style={photoFraming ? photoFramingStyle(photoFraming) : undefined}
      />
    {:else}
      <div class:bean={beanFallback} class="photo-fallback" aria-hidden="true">
        {#if beanFallback}<span></span>{:else}<span class="camera">◇</span>{/if}
      </div>
    {/if}
  </div>
</div>

<style>
  .catalog-photo {
    display: grid;
    gap: 10px;
  }
  .photo-frame {
    width: 100%;
    aspect-ratio: 4 / 3;
    display: grid;
    place-items: center;
    padding: 10px;
    overflow: hidden;
    border: 1px solid var(--line);
    border-radius: 18px;
    background: var(--cream);
  }
  .photo-frame.framed {
    padding: 0;
  }
  img {
    width: 100%;
    height: 100%;
    display: block;
    object-fit: contain;
    border-radius: 11px;
  }
  img.framed {
    object-fit: cover;
    border-radius: inherit;
  }
  .photo-fallback {
    color: color-mix(in srgb, var(--coffee) 35%, transparent);
  }
  .camera {
    font-size: 3rem;
  }
  .photo-fallback.bean {
    position: relative;
    width: 72px;
    height: 100px;
    border: 2px solid currentColor;
    border-radius: 52% 48% 48% 52%;
    transform: rotate(28deg);
  }
  .photo-fallback.bean span {
    position: absolute;
    left: 52%;
    top: 10%;
    width: 2px;
    height: 80%;
    background: currentColor;
    transform: rotate(12deg);
  }
  .compact .photo-frame {
    aspect-ratio: 16 / 10;
    border-radius: 14px;
  }
  .compact .photo-fallback.bean {
    width: 54px;
    height: 74px;
  }
</style>
