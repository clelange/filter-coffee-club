<script lang="ts">
  import { onDestroy, tick } from 'svelte';
  import PhotoFramingEditor from '$lib/PhotoFramingEditor.svelte';
  import { photoFramingStyle } from '$lib/photo-framing';
  import type { PhotoFraming } from '$lib/types';

  export let file: File | null = null;
  export let photoPath: string | null = null;
  export let framing: PhotoFraming | null = null;
  export let label = 'Photo';

  let previewUrl: string | null = null;
  let previewFile: File | null = null;
  let editorOpen = false;
  let editorButton: HTMLButtonElement;

  $: source = previewUrl ?? photoPath;

  $: if (file !== previewFile) {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewFile = file;
    previewUrl = file ? URL.createObjectURL(file) : null;
  }

  function choose(event: Event) {
    file = (event.currentTarget as HTMLInputElement).files?.[0] ?? null;
    if (file) framing = null;
  }

  async function closeEditor() {
    editorOpen = false;
    await tick();
    editorButton?.focus();
  }

  async function applyFraming(value: PhotoFraming | null) {
    framing = value;
    await closeEditor();
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
  {#if source}
    <div class:framed={framing} class="preview">
      <img
        class:framed={framing}
        src={source}
        alt="Selected catalog item"
        style={framing ? photoFramingStyle(framing) : undefined}
      />
    </div>
    <div class="framing-actions">
      <button
        class="secondary small"
        type="button"
        bind:this={editorButton}
        onclick={() => (editorOpen = true)}>Edit framing</button
      >
      {#if framing}<span>Custom framing applied</span>{:else}<span>Showing the full image</span
        >{/if}
    </div>
  {/if}
</div>

{#if editorOpen && source}
  <PhotoFramingEditor
    src={source}
    initial={framing}
    onapply={applyFraming}
    oncancel={closeEditor}
  />
{/if}

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
  .preview.framed {
    padding: 0;
  }
  img {
    width: 100%;
    height: 100%;
    display: block;
    object-fit: contain;
    border-radius: 10px;
  }
  img.framed {
    object-fit: cover;
    border-radius: inherit;
  }
  .framing-actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px;
  }
  .framing-actions span {
    color: var(--muted);
    font-size: 0.82rem;
  }
</style>
