<script lang="ts">
  import { onDestroy } from 'svelte';

  export let file: File | null = null;
  export let label = 'Photo';

  let previewUrl: string | null = null;
  let previewFile: File | null = null;

  $: if (file !== previewFile) {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewFile = file;
    previewUrl = file ? URL.createObjectURL(file) : null;
  }

  function choose(event: Event) {
    file = (event.currentTarget as HTMLInputElement).files?.[0] ?? null;
  }

  onDestroy(() => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  });
</script>

<div class="photo-picker">
  <label
    >{label}<input
      type="file"
      accept="image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif"
      onchange={choose}
    /></label
  >
  <small>JPEG, PNG, WebP, HEIC, or HEIF · up to 12 MB</small>
  {#if previewUrl}
    <div class="preview"><img src={previewUrl} alt="Selected catalog item" /></div>
  {/if}
</div>

<style>
  .photo-picker {
    display: grid;
    gap: 8px;
  }
  small {
    color: var(--muted);
  }
  .preview {
    width: min(100%, 360px);
    aspect-ratio: 4 / 3;
    padding: 10px;
    border: 1px solid var(--line);
    border-radius: 16px;
    background: var(--cream);
  }
  img {
    width: 100%;
    height: 100%;
    display: block;
    object-fit: contain;
    border-radius: 10px;
  }
</style>
