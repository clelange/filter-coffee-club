<script lang="ts">
  import { onDestroy, tick } from 'svelte';

  export let open = false;
  export let title: string;
  export let description: string;
  export let confirmLabel = 'Confirm';
  export let cancelLabel = 'Cancel';
  export let busy = false;
  export let onconfirm: () => void | Promise<void>;
  export let oncancel: () => void;

  let dialog: HTMLElement;
  let cancelButton: HTMLButtonElement;
  let previouslyFocused: HTMLElement | null = null;
  let active = false;

  $: if (open && !active) {
    active = true;
    void activate();
  } else if (!open && active) {
    active = false;
    void restoreFocus();
  }

  onDestroy(() => previouslyFocused?.focus());

  async function activate() {
    if (typeof document === 'undefined') return;
    previouslyFocused =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    await tick();
    cancelButton?.focus();
  }

  async function restoreFocus() {
    await tick();
    previouslyFocused?.focus();
    previouslyFocused = null;
  }

  function cancel() {
    if (!busy) oncancel();
  }

  function handleKeydown(event: KeyboardEvent) {
    if (!open) return;
    if (event.key === 'Escape' && !busy) {
      event.preventDefault();
      cancel();
      return;
    }
    if (event.key !== 'Tab' || !dialog) return;
    const controls = [...dialog.querySelectorAll<HTMLElement>('button:not(:disabled)')];
    const first = controls[0];
    const last = controls.at(-1);
    if (!first || !last) return;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }
</script>

<svelte:window onkeydown={handleKeydown} />

{#if open}
  <div
    class="dialog-backdrop"
    role="presentation"
    onclick={(event) => event.currentTarget === event.target && cancel()}
  >
    <div
      class="dialog"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="confirm-title"
      aria-describedby="confirm-description"
      tabindex="-1"
      bind:this={dialog}
    >
      <div>
        <h2 id="confirm-title">{title}</h2>
        <p id="confirm-description">{description}</p>
      </div>
      <div class="actions">
        <button class="danger" type="button" disabled={busy} onclick={onconfirm}
          >{busy ? 'Working…' : confirmLabel}</button
        >
        <button
          class="secondary"
          type="button"
          disabled={busy}
          bind:this={cancelButton}
          onclick={cancel}>{cancelLabel}</button
        >
      </div>
    </div>
  </div>
{/if}

<style>
  .dialog-backdrop {
    position: fixed;
    z-index: 100;
    inset: 0;
    display: grid;
    place-items: center;
    padding: 20px;
    background: rgb(20 14 12 / 58%);
  }
  .dialog {
    display: grid;
    gap: 22px;
    width: min(100%, 480px);
    padding: 26px;
    border: 1px solid var(--line);
    border-radius: 22px;
    background: var(--surface);
    box-shadow: 0 24px 70px rgb(20 14 12 / 30%);
  }
  h2,
  p {
    margin: 0;
  }
  h2 {
    margin-bottom: 8px;
    font-size: 1.7rem;
  }
  p {
    color: var(--muted);
    line-height: 1.5;
  }
</style>
