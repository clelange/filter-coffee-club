<script lang="ts">
  import type { DripperFormData } from '$lib/types';

  export let form: DripperFormData;
</script>

<div class="field-grid">
  <label>Manufacturer<input bind:value={form.manufacturer} /></label>
  <label>Model<input bind:value={form.model} required /></label>
</div>
<label>Notes<textarea bind:value={form.notes}></textarea></label>
