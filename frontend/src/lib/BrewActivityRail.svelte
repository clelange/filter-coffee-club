<script lang="ts">
  import { onMount } from 'svelte';
  import { loginPath } from '$lib/device';
  import { sessionStore } from '$lib/api';
  import { brewStatusStore, startBrewStatusPolling } from '$lib/brew-status';

  const hasActivity = $derived(
    Boolean(
      $brewStatusStore &&
      ($brewStatusStore.brews.length > 0 || $brewStatusStore.recent_rating_brews.length > 0)
    )
  );
  const canStart = $derived(
    Boolean(
      $brewStatusStore?.can_start && (!$sessionStore || !$sessionStore.profile.pin_change_required)
    )
  );
  const startHref = $derived($sessionStore ? '/brews/new' : loginPath('/brews/new'));

  onMount(startBrewStatusPolling);
</script>

{#if $brewStatusStore && (hasActivity || canStart)}
  <nav class="brew-activity-rail" aria-label="Brew activity" data-testid="brew-activity-rail">
    <div class="brew-activity-track">
      {#each $brewStatusStore.brews as brew}
        <a
          class="brew-activity-chip brewing"
          data-testid="active-brew-chip"
          href={`/brews/${brew.id}`}
          aria-label={`Brewing now: ${brew.coffee_name}. Open brew ${brew.id}.`}
        >
          <span>Brewing now</span>
          <strong>{brew.coffee_name}</strong>
        </a>
      {/each}
      {#each $brewStatusStore.recent_rating_brews as brew}
        {#if brew.rating_token}
          <a
            class="brew-activity-chip rating"
            data-testid="rating-brew-chip"
            href={`/rate/${brew.rating_token}`}
            aria-label={`Ready to rate: ${brew.coffee_name}.`}
          >
            <span>Ready to rate</span>
            <strong>{brew.coffee_name}</strong>
          </a>
        {/if}
      {/each}
      {#if canStart}
        <a
          class="brew-activity-chip start"
          data-testid="start-brew-chip"
          href={startHref}
          aria-label={hasActivity ? 'Start another brew' : 'Start a brew'}
        >
          <span>{hasActivity ? 'Available slot' : 'Ready when you are'}</span>
          <strong>{hasActivity ? '+ New brew' : 'Start a brew'}</strong>
        </a>
      {/if}
    </div>
  </nav>
{/if}

<style>
  .brew-activity-rail {
    min-width: 0;
    width: 100%;
    padding: 7px clamp(16px, 4vw, 56px) 8px;
    overflow: hidden;
    border-top: 1px solid var(--line);
  }

  .brew-activity-track {
    display: flex;
    gap: 8px;
    min-width: 0;
    overflow-x: auto;
    overscroll-behavior-inline: contain;
    scrollbar-width: thin;
    scroll-snap-type: inline proximity;
  }

  .brew-activity-chip {
    display: grid;
    flex: 0 0 auto;
    min-width: min(220px, calc(100vw - 32px));
    max-width: min(320px, calc(100vw - 32px));
    min-height: 48px;
    align-content: center;
    gap: 1px;
    padding: 7px 14px;
    border: 1px solid var(--line);
    border-radius: 14px;
    color: var(--ink);
    text-decoration: none;
    scroll-snap-align: start;
  }

  .brew-activity-chip span,
  .brew-activity-chip strong {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .brew-activity-chip span {
    color: var(--muted);
    font-size: 0.66rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    line-height: 1.15;
    text-transform: uppercase;
  }

  .brew-activity-chip strong {
    font-size: 0.9rem;
    line-height: 1.25;
  }

  .brew-activity-chip.brewing {
    background: color-mix(in srgb, var(--amber) 11%, var(--surface));
  }

  .brew-activity-chip.rating {
    background: color-mix(in srgb, var(--cyan) 11%, var(--surface));
  }

  .brew-activity-chip.start {
    border-color: var(--coffee);
    background: var(--coffee);
    color: white;
  }

  .brew-activity-chip.start span {
    color: color-mix(in srgb, white 74%, var(--coffee));
  }

  .brew-activity-chip:hover {
    border-color: color-mix(in srgb, var(--coffee) 45%, var(--line));
  }

  .brew-activity-chip.start:hover {
    background: color-mix(in srgb, var(--coffee) 88%, black);
  }

  @media (min-width: 821px) and (max-width: 1100px) {
    .brew-activity-rail {
      padding-inline: 20px;
    }
  }

  @media (max-width: 600px) {
    .brew-activity-rail {
      padding-inline: 12px;
    }

    .brew-activity-chip {
      min-width: min(200px, calc(100vw - 24px));
      max-width: min(280px, calc(100vw - 24px));
    }
  }
</style>
