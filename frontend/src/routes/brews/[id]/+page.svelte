<script lang="ts">
  import BrewDetail from './BrewDetail.svelte';

  let { params } = $props();
</script>

<!-- A new brew needs its own page state, polling, and wake lock. -->
{#key params.id}
  <BrewDetail id={Number(params.id)} />
{/key}
