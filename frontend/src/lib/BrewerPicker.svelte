<script lang="ts">
  import type { ProfileIdentity } from '$lib/types';

  export let profiles: ProfileIdentity[] = [];
  export let selected: number[] = [];
  export let primaryId: number;
  export let disabled = false;

  function add(event: Event) {
    const input = event.currentTarget as HTMLSelectElement;
    const id = Number(input.value);
    if (id && !selected.includes(id)) selected = [...selected, id];
    input.value = '';
  }
</script>

<fieldset class="brewers" {disabled}>
  <legend>Brewers</legend>
  <p class="hint">Everyone who helped brew. The primary brewer manages this list.</p>
  <div class="brewer-chips" aria-label="Selected brewers">
    {#each selected as id (id)}
      {@const name = profiles.find((profile) => profile.id === id)?.display_name ?? `Member #${id}`}
      <span class="brewer-chip">
        <span
          >{name}{#if id === primaryId}<small>Primary</small>{/if}</span
        >
        {#if id !== primaryId}
          <button
            type="button"
            class="secondary"
            aria-label={`Remove brewer ${name}`}
            onclick={() => (selected = selected.filter((item) => item !== id))}>×</button
          >
        {/if}
      </span>
    {/each}
  </div>
  <label
    >Add a brewer
    <select onchange={add} value="">
      <option value="">Choose a person</option>
      {#each profiles.filter((profile) => !selected.includes(profile.id)) as profile}
        <option value={profile.id}>{profile.display_name}</option>
      {/each}
    </select>
  </label>
</fieldset>

<style>
  .brewers {
    display: grid;
    gap: 12px;
    min-width: 0;
  }
  .brewers p {
    margin: 0;
  }
  .brewer-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .brewer-chip {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    padding: 5px 6px 5px 12px;
    border: 1px solid var(--line);
    border-radius: 12px;
    background: var(--surface);
  }
  .brewer-chip > span {
    display: grid;
  }
  .brewer-chip small {
    color: var(--muted);
    font-size: 0.7rem;
  }
  .brewer-chip button {
    min-width: 44px;
    min-height: 44px;
    padding: 4px;
    font-size: 1.3rem;
  }
</style>
