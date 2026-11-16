<script lang="ts">
  import { page } from '$app/state';

  let { children } = $props();
</script>

{#key `${page.params.kind}/${page.params.id}`}
  {@render children()}
{/key}
