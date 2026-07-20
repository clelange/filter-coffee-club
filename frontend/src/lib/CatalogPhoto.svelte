<script lang="ts">
  import { api, uploadCatalogPhoto } from '$lib/api';

  export let photoPath: string | null;
  export let alt: string;
  export let endpoint: string;
  export let editable = false;
  export let compact = false;
  export let beanFallback = false;
  export let onchanged: (photoPath: string | null) => void | Promise<void> = () => undefined;

  let input: HTMLInputElement;
  let busy = false;
  let error = '';

  async function replacePhoto(event: Event) {
    const file = (event.currentTarget as HTMLInputElement).files?.[0];
    if (!file) return;
    busy = true;
    error = '';
    try {
      const updated = await uploadCatalogPhoto<{ photo_path: string | null }>(endpoint, file);
      await onchanged(updated.photo_path);
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not upload photo.';
    } finally {
      busy = false;
      if (input) input.value = '';
    }
  }

  async function removePhoto() {
    if (!confirm('Remove this photo?')) return;
    busy = true;
    error = '';
    try {
      const updated = await api<{ photo_path: string | null }>(endpoint, { method: 'DELETE' });
      await onchanged(updated.photo_path);
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not remove photo.';
    } finally {
      busy = false;
    }
  }
</script>

<div class:compact class="catalog-photo">
  <div class="photo-frame">
    {#if photoPath}
      <img src={photoPath} {alt} loading="lazy" decoding="async" />
    {:else}
      <div class:bean={beanFallback} class="photo-fallback" aria-hidden="true">
        {#if beanFallback}<span></span>{:else}<span class="camera">◇</span>{/if}
      </div>
    {/if}
  </div>
  {#if editable}
    <div class="photo-actions">
      <label class="button secondary small" class:disabled={busy}>
        {busy ? 'Working…' : photoPath ? 'Replace photo' : 'Add photo'}
        <input
          bind:this={input}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          disabled={busy}
          onchange={replacePhoto}
        />
      </label>
      {#if photoPath}
        <button class="secondary" type="button" disabled={busy} onclick={removePhoto}
          >Remove photo</button
        >
      {/if}
    </div>
  {/if}
  {#if error}<p class="error" role="alert">{error}</p>{/if}
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
  img {
    width: 100%;
    height: 100%;
    display: block;
    object-fit: contain;
    border-radius: 11px;
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
  .photo-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  label {
    position: relative;
    overflow: hidden;
  }
  label input {
    position: absolute;
    width: 1px;
    height: 1px;
    opacity: 0;
  }
  label.disabled {
    pointer-events: none;
    opacity: 0.45;
  }
  .compact .photo-frame {
    aspect-ratio: 16 / 10;
    border-radius: 14px;
  }
  .compact .photo-fallback.bean {
    width: 54px;
    height: 74px;
  }
  .error {
    margin: 0;
  }
</style>
