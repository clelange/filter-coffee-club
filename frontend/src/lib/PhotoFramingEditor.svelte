<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { photoFramingStyle } from '$lib/photo-framing';
  import type { PhotoFraming } from '$lib/types';

  export let src: string;
  export let alt = 'Selected catalog item';
  export let initial: PhotoFraming | null = null;
  export let onapply: (framing: PhotoFraming | null) => void = () => undefined;
  export let oncancel: () => void = () => undefined;

  let panel: HTMLElement;
  let enabled = true;
  let focusX = initial?.focus_x ?? 0.5;
  let focusY = initial?.focus_y ?? 0.5;
  let zoom = initial?.zoom ?? 1;
  const pointers = new Map<number, { x: number; y: number }>();
  let pinchDistance = 0;
  let pinchZoom = 1;
  let previousBodyOverflow = '';

  const clamp = (value: number, minimum: number, maximum: number) =>
    Math.min(maximum, Math.max(minimum, value));

  onMount(() => {
    previousBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    panel?.focus();
  });

  onDestroy(() => {
    document.body.style.overflow = previousBodyOverflow;
  });

  function framingStyle(): string | undefined {
    if (!enabled) return undefined;
    return photoFramingStyle({ focus_x: focusX, focus_y: focusY, zoom });
  }

  function enableFraming() {
    enabled = true;
  }

  function center() {
    enabled = true;
    focusX = 0.5;
    focusY = 0.5;
    zoom = 1;
  }

  function useFullImage() {
    enabled = false;
    focusX = 0.5;
    focusY = 0.5;
    zoom = 1;
  }

  function updateZoom(value: number) {
    enabled = true;
    zoom = clamp(value, 1, 3);
  }

  function pointerDown(event: PointerEvent) {
    enableFraming();
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (pointers.size === 2) {
      const [first, second] = [...pointers.values()];
      pinchDistance = Math.hypot(second.x - first.x, second.y - first.y);
      pinchZoom = zoom;
    }
  }

  function pointerMove(event: PointerEvent) {
    const previous = pointers.get(event.pointerId);
    if (!previous) return;
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });

    if (pointers.size === 1) {
      const frame = (event.currentTarget as HTMLElement).getBoundingClientRect();
      focusX = clamp(focusX - (event.clientX - previous.x) / (frame.width * zoom), 0, 1);
      focusY = clamp(focusY - (event.clientY - previous.y) / (frame.height * zoom), 0, 1);
      return;
    }

    const [first, second] = [...pointers.values()];
    const distance = Math.hypot(second.x - first.x, second.y - first.y);
    if (pinchDistance > 0) updateZoom(pinchZoom * (distance / pinchDistance));
  }

  function pointerEnd(event: PointerEvent) {
    pointers.delete(event.pointerId);
    if (pointers.size < 2) pinchDistance = 0;
  }

  function wheel(event: WheelEvent) {
    event.preventDefault();
    updateZoom(zoom - event.deltaY * 0.002);
  }

  function moveWithKeyboard(event: KeyboardEvent) {
    const step = event.shiftKey ? 0.05 : 0.015;
    if (event.key === 'ArrowLeft') focusX = clamp(focusX - step, 0, 1);
    else if (event.key === 'ArrowRight') focusX = clamp(focusX + step, 0, 1);
    else if (event.key === 'ArrowUp') focusY = clamp(focusY - step, 0, 1);
    else if (event.key === 'ArrowDown') focusY = clamp(focusY + step, 0, 1);
    else if (event.key === '+' || event.key === '=') updateZoom(zoom + 0.1);
    else if (event.key === '-') updateZoom(zoom - 0.1);
    else return;
    enableFraming();
    event.preventDefault();
  }

  function globalKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      oncancel();
      return;
    }
    if (event.key !== 'Tab' || !panel) return;
    const focusable = [
      ...panel.querySelectorAll<HTMLElement>(
        'button:not(:disabled), input:not(:disabled), [href], [tabindex]:not([tabindex="-1"])'
      )
    ];
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && (document.activeElement === first || document.activeElement === panel)) {
      last.focus();
      event.preventDefault();
    } else if (!event.shiftKey && document.activeElement === last) {
      first.focus();
      event.preventDefault();
    }
  }

  function apply() {
    onapply(enabled ? { focus_x: focusX, focus_y: focusY, zoom } : null);
  }
</script>

<svelte:window onkeydown={globalKeydown} />

<div class="editor-shell" role="presentation">
  <div
    class="editor"
    role="dialog"
    aria-modal="true"
    aria-labelledby="framing-title"
    bind:this={panel}
    tabindex="-1"
  >
    <header>
      <div>
        <p class="eyebrow">Photo editor</p>
        <h2 id="framing-title">Adjust framing</h2>
        <p>Drag to position the subject. Pinch, scroll, or use the slider to zoom.</p>
      </div>
      <button
        class="secondary close"
        type="button"
        aria-label="Close photo editor"
        onclick={oncancel}>×</button
      >
    </header>

    <div class="editor-body">
      <div class="preview-layout">
        <div class="primary-preview">
          <span>Gallery preview</span>
          <button
            type="button"
            class="crop-frame gallery"
            aria-label="Gallery photo framing area. Drag or use arrow keys to reposition."
            onpointerdown={pointerDown}
            onpointermove={pointerMove}
            onpointerup={pointerEnd}
            onpointercancel={pointerEnd}
            onwheel={wheel}
            onkeydown={moveWithKeyboard}
          >
            <img class:framed={enabled} {src} {alt} draggable="false" style={framingStyle()} />
            {#if enabled}<div class="guide" aria-hidden="true"></div>{/if}
          </button>
        </div>
        <div class="detail-preview">
          <span>Detail preview</span>
          <div class="crop-frame detail">
            <img class:framed={enabled} {src} alt="" draggable="false" style={framingStyle()} />
          </div>
        </div>
      </div>

      <div class="controls">
        <label>
          <span>Zoom</span>
          <input
            type="range"
            min="1"
            max="3"
            step="0.01"
            value={zoom}
            disabled={!enabled}
            aria-valuetext={`${zoom.toFixed(2)} times`}
            oninput={(event) => updateZoom(Number(event.currentTarget.value))}
          />
          <output>{zoom.toFixed(2)}×</output>
        </label>
        <label>
          <span>Horizontal position</span>
          <input
            type="range"
            min="0"
            max="1"
            step="0.01"
            value={focusX}
            disabled={!enabled}
            oninput={(event) => {
              enableFraming();
              focusX = Number(event.currentTarget.value);
            }}
          />
        </label>
        <label>
          <span>Vertical position</span>
          <input
            type="range"
            min="0"
            max="1"
            step="0.01"
            value={focusY}
            disabled={!enabled}
            oninput={(event) => {
              enableFraming();
              focusY = Number(event.currentTarget.value);
            }}
          />
        </label>
      </div>
    </div>

    <div class="editor-actions">
      <div>
        <button class="secondary" type="button" onclick={center}>Center and fill</button>
        <button class="secondary" type="button" onclick={useFullImage}>Use full image</button>
      </div>
      <div>
        <button class="secondary" type="button" onclick={oncancel}>Cancel</button>
        <button class="primary" type="button" onclick={apply}>Apply framing</button>
      </div>
    </div>
  </div>
</div>

<style>
  .editor-shell {
    position: fixed;
    z-index: 100;
    inset: 0;
    display: grid;
    place-items: center;
    padding: 20px;
    background: rgb(36 28 25 / 72%);
    backdrop-filter: blur(8px);
  }
  .editor {
    display: grid;
    width: min(940px, 100%);
    max-height: calc(100dvh - 40px);
    grid-template-rows: auto minmax(0, 1fr) auto;
    gap: 22px;
    overflow: hidden;
    padding: clamp(18px, 4vw, 32px);
    border: 1px solid var(--line);
    border-radius: 24px;
    background: var(--surface);
    box-shadow: 0 28px 90px rgb(0 0 0 / 35%);
  }
  .editor-body {
    display: grid;
    min-height: 0;
    gap: 22px;
    overflow: auto;
    padding: 2px;
  }
  header,
  .editor-actions,
  .editor-actions > div {
    display: flex;
    align-items: center;
  }
  .editor-actions {
    padding-top: 14px;
    border-top: 1px solid var(--line);
    background: var(--surface);
  }
  header,
  .editor-actions {
    justify-content: space-between;
    gap: 18px;
  }
  header h2,
  header p {
    margin: 0;
  }
  header > div {
    display: grid;
    gap: 6px;
  }
  header .eyebrow {
    margin: 0;
  }
  header p:last-child {
    color: var(--muted);
  }
  .close {
    flex: 0 0 auto;
    width: 46px;
    min-height: 46px;
    padding: 0;
    border-radius: 50%;
    font-size: 1.7rem;
    line-height: 1;
  }
  .preview-layout {
    display: grid;
    grid-template-columns: minmax(0, 520px) minmax(180px, 240px);
    justify-content: space-between;
    gap: 18px;
    align-items: end;
  }
  .primary-preview,
  .detail-preview {
    display: grid;
    gap: 7px;
    min-width: 0;
  }
  .primary-preview > span,
  .detail-preview > span,
  .controls label > span {
    color: var(--muted);
    font-size: 0.78rem;
    font-weight: 800;
  }
  .crop-frame {
    position: relative;
    width: 100%;
    overflow: hidden;
    border: 1px solid var(--line);
    border-radius: 16px;
    background: var(--cream);
    padding: 0;
  }
  .crop-frame.gallery {
    aspect-ratio: 16 / 10;
    cursor: grab;
    touch-action: none;
  }
  .crop-frame.gallery:active {
    cursor: grabbing;
  }
  .crop-frame.detail {
    aspect-ratio: 4 / 3;
  }
  .crop-frame img {
    width: 100%;
    height: 100%;
    display: block;
    object-fit: contain;
    pointer-events: none;
    user-select: none;
  }
  .crop-frame img.framed {
    object-fit: cover;
  }
  .guide {
    position: absolute;
    inset: 0;
    border: 1px solid rgb(255 255 255 / 58%);
    background:
      linear-gradient(
        to right,
        transparent calc(33.333% - 0.5px),
        rgb(255 255 255 / 45%) 33.333%,
        transparent calc(33.333% + 0.5px),
        transparent calc(66.666% - 0.5px),
        rgb(255 255 255 / 45%) 66.666%,
        transparent calc(66.666% + 0.5px)
      ),
      linear-gradient(
        to bottom,
        transparent calc(33.333% - 0.5px),
        rgb(255 255 255 / 45%) 33.333%,
        transparent calc(33.333% + 0.5px),
        transparent calc(66.666% - 0.5px),
        rgb(255 255 255 / 45%) 66.666%,
        transparent calc(66.666% + 0.5px)
      );
    pointer-events: none;
  }
  .controls {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 16px;
  }
  .controls label {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 8px;
    align-items: center;
  }
  .controls input {
    grid-column: 1 / -1;
    width: 100%;
    min-height: 32px;
    accent-color: var(--cyan);
  }
  .controls input:disabled {
    opacity: 0.4;
  }
  .editor-actions > div {
    flex-wrap: wrap;
    gap: 8px;
  }
  @media (min-width: 701px) and (max-height: 700px) {
    .editor {
      gap: 14px;
      padding: 18px;
    }
    .editor-body {
      gap: 14px;
    }
    .preview-layout {
      grid-template-columns: minmax(0, 400px) minmax(160px, 200px);
    }
    .controls {
      gap: 12px;
    }
    .controls input {
      min-height: 24px;
    }
    .editor-actions {
      padding-top: 10px;
    }
  }
  @media (max-width: 700px) {
    .editor-shell {
      padding: 0;
    }
    .editor {
      width: 100%;
      height: 100dvh;
      max-height: none;
      align-content: start;
      border: 0;
      border-radius: 0;
    }
    .preview-layout {
      grid-template-columns: 1fr;
    }
    .detail-preview {
      width: min(52%, 210px);
    }
    .controls {
      grid-template-columns: 1fr;
      gap: 10px;
    }
    .editor-actions {
      align-items: stretch;
      flex-direction: column;
    }
    .editor-actions > div {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .editor-actions button {
      min-height: 48px;
    }
  }
</style>
