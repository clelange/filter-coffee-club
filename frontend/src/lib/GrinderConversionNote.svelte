<script lang="ts">
  export let unconverted: number;
</script>

<p class="hint">
  Converted settings are approximate starting points. Original grinder settings appear in each
  brew’s details.
</p>
{#if unconverted > 0}
  <p class="hint" data-testid="unconverted-brews">
    {unconverted} brew{unconverted === 1 ? '' : 's'} cannot be converted to this scale. Choose another
    scale or an original grinder under “Show settings in” to view those results.
  </p>
{/if}
