<script lang="ts">
  import { page } from '$app/state';

  let { children } = $props();
</script>

{#key page.url.searchParams.get('coffee')}
  {@render children()}
{/key}
