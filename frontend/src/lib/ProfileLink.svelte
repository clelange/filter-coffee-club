<script lang="ts">
  import { sessionStore } from '$lib/api';

  export let profileId: number;
  export let displayName: string;
</script>

{#if $sessionStore && !$sessionStore.profile.pin_change_required}
  <a class="profile-link" href={`/profiles/${profileId}`}>{displayName}</a>
{:else}
  <span>{displayName}</span>
{/if}

<style>
  .profile-link {
    color: inherit;
    font-weight: 750;
    text-decoration-color: color-mix(in srgb, currentColor 42%, transparent);
    text-underline-offset: 0.18em;
  }
  .profile-link:hover {
    color: var(--cyan);
    text-decoration-color: currentColor;
  }
</style>
