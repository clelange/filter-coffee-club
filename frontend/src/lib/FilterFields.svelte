<script lang="ts">
  import type { FilterFormData } from '$lib/types';

  export let form: FilterFormData;
</script>

<label>Name<input bind:value={form.name} required /></label>
<label>Notes<textarea bind:value={form.notes}></textarea></label>
