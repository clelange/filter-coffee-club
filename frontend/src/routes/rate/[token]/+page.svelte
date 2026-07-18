<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { api, ensureSession, jsonBody, logout } from '$lib/api';
  import type { Brew, FlavorTag, RatingInput, RatingSummary, Session } from '$lib/types';

  let brew: Brew | null = $state(null);
  let session: Session | null = $state(null);
  let tags: FlavorTag[] = $state([]);
  let summary: RatingSummary | null = $state(null);
  let inactive = $state(false);
  let loading = $state(true);
  let saving = $state(false);
  let error = $state('');
  let countdown = $state(10);
  let timer: ReturnType<typeof setInterval> | null = null;
  let rating: RatingInput = $state({ liking: 7, acidity: 2, bitterness: 2, sweetness: 3, body: 3, flavor_tag_ids: [] });

  const token = $derived($page.params.token);
  const parents = $derived(tags.filter((tag) => tag.parent_id === null));

  onMount(async () => {
    try {
      const link = await api<{ active: boolean; brew: Brew | null }>(`/rating-links/${token}`);
      if (!link.active || !link.brew) { inactive = true; return; }
      brew = link.brew;
      session = await ensureSession();
      if (!session) {
        await goto(`/login?next=${encodeURIComponent(`/rate/${token}`)}`);
        return;
      }
      tags = await api<FlavorTag[]>('/flavor-tags');
      summary = await api<RatingSummary>(`/brews/${brew.id}/ratings`);
      if (summary.own_rating) rating = {
        liking: summary.own_rating.liking, acidity: summary.own_rating.acidity,
        bitterness: summary.own_rating.bitterness, sweetness: summary.own_rating.sweetness,
        body: summary.own_rating.body, flavor_tag_ids: summary.own_rating.flavor_tag_ids
      };
    } catch (caught) { error = caught instanceof Error ? caught.message : 'Could not open this rating.'; }
    finally { loading = false; }
  });

  onDestroy(() => { if (timer) clearInterval(timer); });

  function toggleTag(id: number) {
    if (rating.flavor_tag_ids.includes(id)) rating.flavor_tag_ids = rating.flavor_tag_ids.filter((item) => item !== id);
    else if (rating.flavor_tag_ids.length < 5) rating.flavor_tag_ids = [...rating.flavor_tag_ids, id];
  }

  async function submit(event: SubmitEvent) {
    event.preventDefault(); if (!brew) return;
    saving = true; error = '';
    try {
      summary = await api<RatingSummary>(`/brews/${brew.id}/ratings`, { method: 'POST', body: jsonBody(rating) });
      if (session?.device_mode === 'kiosk') {
        countdown = 10;
        timer = setInterval(async () => { countdown -= 1; if (countdown <= 0) await finishKiosk(); }, 1000);
      }
    } catch (caught) { error = caught instanceof Error ? caught.message : 'Could not save your rating.'; }
    finally { saving = false; }
  }

  async function finishKiosk() {
    if (timer) clearInterval(timer); timer = null;
    await logout();
    await goto(`/brews/${brew?.id}`);
  }

  function children(parentId: number): FlavorTag[] { return tags.filter((tag) => tag.parent_id === parentId); }
</script>

<svelte:head><title>Rate this brew · Filter Coffee Club</title></svelte:head>

{#if loading}
  <div class="empty">Opening the tasting form…</div>
{:else if inactive}
  <section class="panel"><p class="eyebrow">Rating closed</p><h1>This brew is no longer available.</h1><p class="lede">The link may belong to a voided or removed brew.</p><a class="button secondary" href="/">Return home</a></section>
{:else if error && !brew}
  <p class="error">{error}</p>
{:else if brew && summary?.can_view && summary.own_rating}
  <section class="results-layout">
    <div><p class="eyebrow">Signal received</p><h1>Thanks, {session?.profile.display_name}.</h1><p class="lede">Your rating is part of {summary.count} response{summary.count === 1 ? '' : 's'} for {brew.coffee_name}.</p>
      {#if session?.device_mode === 'kiosk'}<p class="return-note">Returning to the QR invitation in <strong>{countdown}</strong> seconds.</p>{/if}
      <div class="actions">{#if session?.device_mode === 'kiosk'}<button class="primary" onclick={finishKiosk}>Done</button>{:else}<button class="secondary" onclick={() => (summary = { ...summary!, own_rating: null, can_view: false })}>Edit my rating</button><a class="button" href="/">Club home</a>{/if}</div>
    </div>
    <div class="panel result-panel"><p class="eyebrow">Group response</p><div class="score"><strong>{summary.averages.liking ?? '—'}</strong><span>/ 9 liking</span></div>
      <div class="result-grid">{#each ['acidity','bitterness','sweetness','body'] as key}<div><b>{summary.averages[key] ?? '—'}</b><span>{key}</span></div>{/each}</div>
      {#if Object.keys(summary.flavor_counts).length}<div class="tags">{#each Object.entries(summary.flavor_counts) as [name,count]}<span class="tag">{name} · {count}</span>{/each}</div>{/if}
    </div>
  </section>
{:else if brew}
  <div class="rating-layout">
    <aside><p class="eyebrow">Brew #{brew.id}</p><h1>How did it land?</h1><p class="lede"><strong>{brew.coffee_roaster} · {brew.coffee_name}</strong><br />1:{brew.ratio} · {brew.grinder_setting} {brew.grinder_unit} · {brew.temperature_c} °C</p><p class="muted">Existing ratings stay hidden until you submit yours.</p></aside>
    <form class="panel" onsubmit={submit}>
      <fieldset><legend>Overall liking <output>{rating.liking} / 9</output></legend><input type="range" bind:value={rating.liking} min="1" max="9" step="1" /><div class="anchors"><span>Strongly dislike</span><span>Love it</span></div></fieldset>
      <div class="intensity-grid">
        {#each ['acidity','bitterness','sweetness','body'] as key}
          <label><span>{key} <output>{rating[key as keyof RatingInput]}</output></span><input type="range" bind:value={rating[key as 'acidity']} min="0" max="5" step="1" /><small>not perceived → very intense</small></label>
        {/each}
      </div>
      <fieldset><legend>Tasting notes <small>{rating.flavor_tag_ids.length} / 5</small></legend>
        <div class="flavor-groups">{#each parents as parent}<section><h3>{parent.name}</h3><div class="tag-picker"><button type="button" class:selected={rating.flavor_tag_ids.includes(parent.id)} onclick={() => toggleTag(parent.id)}>{parent.name} · general</button>{#each children(parent.id) as child}<button type="button" class:selected={rating.flavor_tag_ids.includes(child.id)} onclick={() => toggleTag(child.id)}>{child.name}</button>{/each}</div></section>{/each}</div>
      </fieldset>
      {#if error}<p class="error">{error}</p>{/if}
      <button class="primary" disabled={saving}>{saving ? 'Saving…' : 'Submit rating'}</button>
    </form>
  </div>
{/if}

<style>
  .rating-layout,.results-layout { display:grid; grid-template-columns:minmax(0,.8fr) minmax(340px,1.2fr); gap:clamp(30px,7vw,90px); align-items:start; }
  output { float:right; color:var(--coffee); font-size:1.1rem; }
  .anchors { display:flex; justify-content:space-between; color:var(--muted); font-size:.72rem; font-weight:500; }
  .intensity-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; }.intensity-grid label>span { text-transform:capitalize; }.intensity-grid output { float:none; margin-left:auto; }.intensity-grid label>span { display:flex; }.intensity-grid small { color:var(--muted); font-weight:500; }
  fieldset legend small { margin-left:8px; color:var(--muted); }
  .flavor-groups { display:grid; gap:14px; }.flavor-groups section { padding:12px; border:1px solid var(--line); border-radius:14px; }.flavor-groups h3 { margin-bottom:8px; }
  .tag-picker { display:flex; flex-wrap:wrap; gap:7px; }.tag-picker button { min-height:48px; padding:8px 12px; border:1px solid var(--line); border-radius:999px; background:var(--surface); color:var(--ink); cursor:pointer; }.tag-picker button.selected { border-color:var(--cyan); background:var(--cyan); color:white; }
  .score { display:flex; align-items:end; gap:7px; }.score strong { font:700 6rem/.8 Georgia,serif; }.score span { color:var(--muted); }
  .result-grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin:28px 0; }.result-grid div { display:grid; padding:14px; border-radius:12px; background:var(--cream); }.result-grid b { font-size:1.5rem; }.result-grid span { color:var(--muted); text-transform:capitalize; }
  .tags { display:flex; flex-wrap:wrap; gap:6px; }.return-note { padding:12px; border-radius:12px; background:var(--surface); }
  @media(max-width:760px){.rating-layout,.results-layout{grid-template-columns:1fr}.intensity-grid{grid-template-columns:1fr}}
</style>
