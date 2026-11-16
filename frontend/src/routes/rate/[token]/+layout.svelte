<script lang="ts">
  import { page } from '$app/state';

  let { children } = $props();
</script>

{#key page.params.token}
  {@render children()}
{/key}
