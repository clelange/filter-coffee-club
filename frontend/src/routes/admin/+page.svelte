<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { api, ensureSession, jsonBody } from '$lib/api';
  import type { AppSettings, Dripper, FlavorTag, Grinder, Preset, Profile } from '$lib/types';

  let people: Profile[] = $state([]);
  let grinders: Grinder[] = $state([]);
  let drippers: Dripper[] = $state([]);
  let filters: {id:number;name:string;notes:string|null}[] = $state([]);
  let presets: Preset[] = $state([]);
  let tags: FlavorTag[] = $state([]);
  let settings: AppSettings | null = $state(null);
  let activeTab: 'people'|'equipment'|'presets'|'branding'|'data' = $state('people');
  let message = $state('');
  let error = $state('');
  let personForm = $state({display_name:'',pin:'',role:'member'});
  let pinResets: Record<number,string> = $state({});
  let grinderForm = $state({manufacturer:'',model:'',setting_unit:'clicks',setting_step:1,soft_min:0,soft_max:50,guidance:''});
  let dripperForm = $state({manufacturer:'',model:'',notes:''});
  let filterForm = $state({name:'',notes:''});
  let tagForm = $state({name:'',parent_id:null as number|null,active:true,sort_order:0});

  function isClickUnit(unit:string){return ['click','clicks'].includes(unit.trim().toLowerCase());}

  onMount(async () => {
    const session = await ensureSession();
    if (!session) { await goto('/login?next=/admin'); return; }
    if (session.profile.role !== 'admin') { await goto('/'); return; }
    await load();
  });

  async function load() {
    [people,grinders,drippers,filters,presets,tags,settings] = await Promise.all([
      api<Profile[]>('/people'),api<Grinder[]>('/grinders'),api<Dripper[]>('/drippers'),api<{id:number;name:string;notes:string|null}[]>('/filters'),api<Preset[]>('/presets?active_only=false'),api<FlavorTag[]>('/flavor-tags?active_only=false'),api<AppSettings>('/settings')
    ]);
  }
  async function run(action:()=>Promise<unknown>, success:string) { error='';message='';try{await action();message=success;await load();}catch(caught){error=caught instanceof Error?caught.message:'The change could not be saved.';} }
  async function addPerson(event:SubmitEvent){event.preventDefault();await run(()=>api('/people',{method:'POST',body:jsonBody(personForm)}),'Member added.');personForm={display_name:'',pin:'',role:'member'};}
  async function togglePerson(person:Profile){await run(()=>api(`/people/${person.id}`,{method:'PUT',body:jsonBody({active:!person.active})}),`${person.display_name} updated.`);}
  async function savePerson(person:Profile){const pin=pinResets[person.id]||undefined;await run(()=>api(`/people/${person.id}`,{method:'PUT',body:jsonBody({display_name:person.display_name,role:person.role,...(pin?{pin}:{})})}),`${person.display_name} updated.`);pinResets[person.id]='';}
  async function addGrinder(event:SubmitEvent){event.preventDefault();await run(()=>api('/grinders',{method:'POST',body:jsonBody({...grinderForm,guidance:grinderForm.guidance||null})}),'Grinder added.');grinderForm={manufacturer:'',model:'',setting_unit:'clicks',setting_step:1,soft_min:0,soft_max:50,guidance:''};}
  async function addDripper(event:SubmitEvent){event.preventDefault();await run(()=>api('/drippers',{method:'POST',body:jsonBody({...dripperForm,manufacturer:dripperForm.manufacturer||null,notes:dripperForm.notes||null})}),'Dripper added.');dripperForm={manufacturer:'',model:'',notes:''};}
  async function addFilter(event:SubmitEvent){event.preventDefault();await run(()=>api('/filters',{method:'POST',body:jsonBody({...filterForm,notes:filterForm.notes||null})}),'Filter added.');filterForm={name:'',notes:''};}
  async function savePreset(preset:Preset){await run(()=>api(`/presets/${preset.id}`,{method:'PUT',body:jsonBody({name:preset.name,ratio:preset.ratio,temperature_min_c:preset.temperature_min_c,temperature_max_c:preset.temperature_max_c,active:preset.active,sort_order:preset.sort_order,grinder_ranges:preset.grinder_ranges})}),'Preset saved.');}
  async function addTag(event:SubmitEvent){event.preventDefault();await run(()=>api('/flavor-tags',{method:'POST',body:jsonBody(tagForm)}),'Flavor tag added.');tagForm={name:'',parent_id:null,active:true,sort_order:0};}
  async function saveTag(tag:FlavorTag){await run(()=>api(`/flavor-tags/${tag.id}`,{method:'PUT',body:jsonBody({name:tag.name,parent_id:tag.parent_id,active:tag.active,sort_order:tag.sort_order})}),'Flavor tag updated.');}
  async function archiveEquipment(kind:'grinders'|'drippers'|'filters',id:number){await run(()=>api(`/${kind}/${id}/archive`,{method:'POST',body:jsonBody({})}),'Equipment archived.');}
  async function saveSettings(event:SubmitEvent){event.preventDefault();if(!settings)return;await run(()=>api('/settings',{method:'PUT',body:jsonBody(settings)}),'Branding saved.');}
  async function uploadLogo(event:Event){const input=event.currentTarget as HTMLInputElement;const file=input.files?.[0];if(!file)return;const body=new FormData();body.set('logo',file);await run(()=>api('/settings/logo',{method:'POST',body}),'Logo uploaded.');}
</script>

<svelte:head><title>Admin · Filter Coffee Club</title></svelte:head>
<p class="eyebrow">Club controls</p><h1>Configure the experiment.</h1><p class="lede">Manage identities, shared equipment, starting points, branding, and portable data.</p>

<div class="tabs section" role="tablist" aria-label="Admin sections">
  {#each [['people','People'],['equipment','Equipment'],['presets','Presets & flavors'],['branding','Branding'],['data','Data']] as item}
    <button class:active={activeTab===item[0]} onclick={() => (activeTab=item[0] as typeof activeTab)}>{item[1]}</button>
  {/each}
</div>
{#if message}<p class="success" role="status">{message}</p>{/if}{#if error}<p class="error" role="alert">{error}</p>{/if}

{#if activeTab==='people'}
  <div class="admin-grid"><form class="panel" onsubmit={addPerson}><h2>Add a member</h2><label>New member display name<input bind:value={personForm.display_name} required /></label><label>Four-digit PIN<input bind:value={personForm.pin} inputmode="numeric" pattern="[0-9][0-9][0-9][0-9]" maxlength="4" required /></label><label>Role<select bind:value={personForm.role}><option value="member">Member</option><option value="admin">Administrator</option></select></label><button class="primary">Add member</button></form>
    <section class="panel"><h2>Profiles</h2><div class="item-list">{#each people as person}<article><input aria-label="Display name" bind:value={person.display_name} /><select aria-label={`Role for ${person.display_name}`} bind:value={person.role}><option value="member">Member</option><option value="admin">Administrator</option></select><input aria-label={`New PIN for ${person.display_name}`} bind:value={pinResets[person.id]} inputmode="numeric" pattern="[0-9][0-9][0-9][0-9]" maxlength="4" placeholder="New PIN" /><button class="secondary" onclick={()=>savePerson(person)}>Save</button><button class="secondary" onclick={() => togglePerson(person)}>{person.active?'Deactivate':'Activate'}</button></article>{/each}</div></section></div>
{:else if activeTab==='equipment'}
  <div class="equipment-grid"><form class="panel" onsubmit={addGrinder}><h2>Grinder</h2><label>Manufacturer<input bind:value={grinderForm.manufacturer} required /></label><label>Model<input bind:value={grinderForm.model} required /></label><div class="field-grid"><label>Unit<input bind:value={grinderForm.setting_unit} required /></label><label>Step<input type="number" bind:value={grinderForm.setting_step} min={isClickUnit(grinderForm.setting_unit)?1:0.01} step={isClickUnit(grinderForm.setting_unit)?1:0.01} inputmode={isClickUnit(grinderForm.setting_unit)?'numeric':'decimal'} /></label><label>Soft min<input type="number" bind:value={grinderForm.soft_min} step={isClickUnit(grinderForm.setting_unit)?1:0.01} inputmode={isClickUnit(grinderForm.setting_unit)?'numeric':'decimal'} /></label><label>Soft max<input type="number" bind:value={grinderForm.soft_max} step={isClickUnit(grinderForm.setting_unit)?1:0.01} inputmode={isClickUnit(grinderForm.setting_unit)?'numeric':'decimal'} /></label></div><label>Guidance<textarea bind:value={grinderForm.guidance}></textarea></label><button class="primary">Add grinder</button></form>
    <form class="panel" onsubmit={addDripper}><h2>Dripper</h2><label>Manufacturer<input bind:value={dripperForm.manufacturer} /></label><label>Model<input bind:value={dripperForm.model} required /></label><label>Notes<textarea bind:value={dripperForm.notes}></textarea></label><button class="primary">Add dripper</button></form>
    <form class="panel" onsubmit={addFilter}><h2>Filter</h2><label>Name<input bind:value={filterForm.name} required /></label><label>Notes<textarea bind:value={filterForm.notes}></textarea></label><button class="primary">Add filter</button></form></div>
  <section class="panel section"><h2>Shared rack</h2><p class="muted">Members edit details from Equipment; archive retired items here.</p><div class="rack"><div><h3>Grinders</h3>{#each grinders as item}<article><span>{item.manufacturer} {item.model} · {item.setting_unit}</span><button class="secondary" onclick={()=>archiveEquipment('grinders',item.id)}>Archive</button></article>{/each}</div><div><h3>Drippers</h3>{#each drippers as item}<article><span>{item.manufacturer??''} {item.model}</span><button class="secondary" onclick={()=>archiveEquipment('drippers',item.id)}>Archive</button></article>{/each}</div><div><h3>Filters</h3>{#each filters as item}<article><span>{item.name}</span><button class="secondary" onclick={()=>archiveEquipment('filters',item.id)}>Archive</button></article>{/each}</div></div></section>
{:else if activeTab==='presets'}
  <div class="stack"><section class="panel"><h2>FCC starting points</h2><div class="preset-list">{#each presets as preset}<article><input bind:value={preset.name} aria-label="Preset name" /><label>Ratio<input type="number" bind:value={preset.ratio} step="0.1" /></label><label>Min °C<input type="number" bind:value={preset.temperature_min_c} /></label><label>Max °C<input type="number" bind:value={preset.temperature_max_c} /></label>{#each preset.grinder_ranges as range}<label>Min clicks<input type="number" bind:value={range.setting_min} step="1" /></label><label>Max clicks<input type="number" bind:value={range.setting_max} step="1" /></label>{/each}<label>Order<input type="number" bind:value={preset.sort_order} /></label><label class="check"><input type="checkbox" bind:checked={preset.active} /> Active</label><button class="secondary" onclick={() => savePreset(preset)}>Save</button></article>{/each}</div></section>
    <div class="admin-grid"><form class="panel" onsubmit={addTag}><h2>Add flavor tag</h2><label>Name<input bind:value={tagForm.name} required /></label><label>Parent category<select bind:value={tagForm.parent_id}><option value={null}>New broad category</option>{#each tags.filter(tag=>tag.parent_id===null) as tag}<option value={tag.id}>{tag.name}</option>{/each}</select></label><button class="primary">Add flavor tag</button></form><section class="panel"><h2>Current vocabulary</h2><div class="tag-editor">{#each tags as tag}<article><input aria-label="Flavor tag name" bind:value={tag.name} /><label>Order<input aria-label="Flavor tag order" type="number" bind:value={tag.sort_order} /></label><label class="check"><input type="checkbox" bind:checked={tag.active} /> Active</label><button class="secondary" onclick={()=>saveTag(tag)}>Save</button></article>{/each}</div></section></div></div>
{:else if activeTab==='branding' && settings}
  <form class="panel brand-form" onsubmit={saveSettings}><div><h2>Filter Coffee Club identity</h2><p class="muted">The official PSI logo is not bundled. Upload an approved PNG or WebP if needed.</p><label>Club name<input bind:value={settings.app_name} required /></label><label>Subtitle<input bind:value={settings.subtitle} /></label><label>Public URL<input type="url" bind:value={settings.public_base_url} placeholder="https://coffee.example.psi.ch" /><span class="hint">This exact origin is encoded in permanent QR links.</span></label><label>Logo PNG/WebP<input type="file" accept="image/png,image/webp" onchange={uploadLogo} /></label></div><div><h3>Palette</h3><div class="colors">{#each [['color_cream','Background'],['color_surface','Surface'],['color_ink','Ink'],['color_coffee','Coffee'],['color_cyan','Collider'],['color_amber','Accent']] as color}<label>{color[1]}<input type="color" bind:value={settings[color[0] as keyof AppSettings] as string} /></label>{/each}</div></div><button class="primary">Save branding</button></form>
{:else if activeTab==='data'}
  <div class="admin-grid"><section class="panel"><p class="eyebrow">Portable data</p><h2>Exports</h2><p class="muted">Exports contain catalog, brew, and rating data, but never PIN hashes, sessions, or QR tokens.</p><div class="actions"><a class="button" href="/api/v1/exports/json">Download JSON</a><a class="button secondary" href="/api/v1/exports/csv">Download CSV ZIP</a></div></section><section class="panel"><p class="eyebrow">Database safety</p><h2>Backups</h2><p>Back up the mounted SQLite file using the documented SQLite backup command or during a stopped container. Restore remains an infrastructure operation.</p><code>sqlite3 /data/fcc.sqlite3 ".backup '/backup/fcc.sqlite3'"</code></section></div>
{/if}

<style>
  .tabs { display:flex; gap:6px; overflow-x:auto; padding:6px; border:1px solid var(--line); border-radius:999px; background:var(--surface); }.tabs button { min-height:48px; padding:9px 16px; border:0; border-radius:999px; background:transparent; color:var(--ink); cursor:pointer; white-space:nowrap; }.tabs button.active { background:var(--coffee); color:white; }
  .admin-grid { display:grid; grid-template-columns:minmax(280px,.7fr) minmax(0,1.3fr); gap:18px; margin-top:18px; align-items:start; }.equipment-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; margin-top:18px; align-items:start; }
  .item-list,.rack>div { display:grid; gap:7px; }.item-list article {display:grid;grid-template-columns:1fr 130px 110px auto auto;gap:7px;align-items:center;padding:10px 0;border-bottom:1px solid var(--line)}.rack article { display:flex; justify-content:space-between; align-items:center; gap:10px; padding:10px 0; border-bottom:1px solid var(--line); }.rack { display:grid; grid-template-columns:repeat(3,1fr); gap:20px; }.rack span { padding:8px 0; }
  .preset-list { display:grid; gap:10px; }.preset-list article { display:grid; grid-template-columns:minmax(180px,2fr) repeat(6,82px) 90px auto; gap:8px; align-items:end; padding:10px; border:1px solid var(--line); border-radius:13px; }.preset-list label { font-size:.72rem; }.check { display:flex; align-items:center; min-height:50px; }.check input { width:20px; min-height:20px; }
  .tag-editor{display:grid;gap:7px}.tag-editor article{display:grid;grid-template-columns:1fr 84px 95px auto;gap:7px;align-items:end}.tag-editor label{font-size:.72rem}.brand-form { display:grid; grid-template-columns:1fr 1fr; gap:30px; margin-top:18px; }.colors { display:grid; grid-template-columns:1fr 1fr; gap:10px; }.colors label { grid-template-columns:1fr 60px; align-items:center; }.colors input { padding:4px; }
  code { display:block; overflow:auto; padding:12px; border-radius:10px; background:var(--ink); color:var(--cream); }
  @media(max-width:900px){.equipment-grid{grid-template-columns:1fr 1fr}.preset-list article{grid-template-columns:1fr 1fr 1fr}.brand-form{grid-template-columns:1fr}.tag-editor article{grid-template-columns:1fr 80px auto}.item-list article{grid-template-columns:1fr 1fr}}@media(max-width:650px){.admin-grid,.equipment-grid{grid-template-columns:1fr}.rack{grid-template-columns:1fr}.preset-list article{grid-template-columns:1fr 1fr}.tag-editor article,.item-list article{grid-template-columns:1fr 1fr}}
</style>
