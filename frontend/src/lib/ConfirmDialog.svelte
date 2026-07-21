<script lang="ts">
  export let open = false;
  export let title: string;
  export let description: string;
  export let confirmLabel = 'Confirm';
  export let busy = false;
  export let onconfirm: () => void | Promise<void>;
  export let oncancel: () => void;
</script>

{#if open}
  <div
    class="dialog-backdrop"
    role="presentation"
    onclick={(event) => event.currentTarget === event.target && !busy && oncancel()}
  >
    <div
      class="dialog"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="confirm-title"
      aria-describedby="confirm-description"
    >
      <div>
        <h2 id="confirm-title">{title}</h2>
        <p id="confirm-description">{description}</p>
      </div>
      <div class="actions">
        <button class="danger" disabled={busy} onclick={onconfirm}
          >{busy ? 'Working…' : confirmLabel}</button
        >
        <button class="secondary" type="button" disabled={busy} onclick={oncancel}>Cancel</button>
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
