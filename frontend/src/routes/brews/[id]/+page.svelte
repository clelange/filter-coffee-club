<script lang="ts">
  import { onDestroy, onMount, tick } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import {
    brewRatioIsUnusual,
    calculateBrewRatio,
    unusualBrewRatioDescription
  } from '$lib/brew-ratio';
  import { refreshBrewStatusAfterMutation } from '$lib/brew-status';
  import ConfirmDialog from '$lib/ConfirmDialog.svelte';
  import { deviceModeStore, loginPath } from '$lib/device';
  import FlavorRadar from '$lib/FlavorRadar.svelte';
  import NumberStepper from '$lib/NumberStepper.svelte';
  import ProfileLink from '$lib/ProfileLink.svelte';
  import RatingMetrics from '$lib/RatingMetrics.svelte';
  import {
    ApiError,
    api,
    ensureSession,
    formatTime,
    jsonBody,
    sessionStore,
    logout
  } from '$lib/api';
  import type { Brew, ProfileIdentity, RatingAggregate } from '$lib/types';

  type FinishIssue =
    | { kind: 'request'; message: string }
    | { kind: 'review'; message: string }
    | { kind: 'reload'; message: string };

  let brew: Brew | null = $state(null);
  let ratingInsights: RatingAggregate | null = $state(null);
  let ratingInsightsError = $state('');
  let error = $state('');
  let finishing = $state(false);
  let finalMinutes = $state(3);
  let finalSeconds = $state(0);
  let actualWater = $state(0);
  let markCoffeeFinished = $state(false);
  let finalizing = $state(false);
  let finishIssue = $state<FinishIssue | null>(null);
  let finishDialog = $state<HTMLElement>();
  let finishRecoveryButton = $state<HTMLButtonElement>();
  let finishPreviouslyFocused: HTMLElement | null = null;
  let finalRatioConfirmationOpen = $state(false);
  let copied = $state(false);
  let statusAction: 'cancel' | 'void' | null = $state(null);
  let changingStatus = $state(false);
  let operatorDialog = $state(false);
  let actionDialog = $state<HTMLElement>();
  let actionPreviouslyFocused: HTMLElement | null = null;
  let operators: ProfileIdentity[] = $state([]);
  let selectedOperatorId = $state(0);
  let changingOperator = $state(false);
  let wakeLock: WakeLockSentinel | null = null;
  let pollTimer: ReturnType<typeof setTimeout> | null = null;
  let joining = $state(false);
  let destroyed = false;

  const id = $derived(Number($page.params.id));
  const finalRatio = $derived(calculateBrewRatio(actualWater, currentBrewDose()));
  const finalRatioUnusual = $derived(
    currentBrewDose() > 0 && brewRatioIsUnusual(actualWater, currentBrewDose())
  );
  const finalBloomWaterInvalid = $derived(bloomWaterExceeds(actualWater));

  $effect(() => {
    const dialog = finishDialog;
    if (!finishing || !dialog) return;
    const frame = requestAnimationFrame(() => {
      if (!finishing || dialog.contains(document.activeElement)) return;
      dialog
        .querySelector<HTMLElement>(
          'input[aria-label="Minutes"], button[aria-label^="Set Minutes;"]'
        )
        ?.focus();
    });
    return () => cancelAnimationFrame(frame);
  });

  $effect(() => {
    const dialog = actionDialog;
    if ((!operatorDialog && !statusAction) || !dialog) return;
    const frame = requestAnimationFrame(() => {
      if ((!operatorDialog && !statusAction) || dialog.contains(document.activeElement)) return;
      dialog
        .querySelector<HTMLElement>(
          'select:not(:disabled), button:not(:disabled), input:not(:disabled), textarea:not(:disabled), a[href]'
        )
        ?.focus();
    });
    return () => cancelAnimationFrame(frame);
  });

  function currentBrewDose(): number {
    return brew?.dose_g ?? 0;
  }

  function bloomWaterExceeds(waterG: number): boolean {
    const bloomWater = brew?.bloom_water_g;
    return bloomWater !== null && bloomWater !== undefined && bloomWater > waterG;
  }

  onMount(async () => {
    await load();
    const session = await ensureSession();
    if (brew?.status === 'draft') {
      if (!session) {
        await goto(loginPath(`/brews/${id}`));
        return;
      }
      await keepAwake();
      scheduleDraftRefresh();
    } else if (brew?.status === 'completed' && session && !session.profile.pin_change_required) {
      await loadRatingInsights();
    }
  });

  onDestroy(() => {
    destroyed = true;
    if (pollTimer) clearTimeout(pollTimer);
    wakeLock?.release();
  });

  function scheduleDraftRefresh() {
    if (destroyed || pollTimer || brew?.status !== 'draft') return;
    pollTimer = setTimeout(async () => {
      pollTimer = null;
      await refreshDraft();
      scheduleDraftRefresh();
    }, 3000);
  }

  async function load() {
    try {
      brew = await api<Brew>(`/brews/${id}`);
      actualWater = brew.water_g;
      if (brew.total_brew_time_s) {
        finalMinutes = Math.floor(brew.total_brew_time_s / 60);
        finalSeconds = brew.total_brew_time_s % 60;
      }
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not load this brew.';
    }
  }

  async function loadRatingInsights() {
    if (!brew) return;
    ratingInsightsError = '';
    try {
      ratingInsights = await api<RatingAggregate>(`/brews/${brew.id}/rating-insights`);
    } catch (caught) {
      ratingInsightsError =
        caught instanceof Error ? caught.message : 'Tasting results are temporarily unavailable.';
    }
  }

  async function refreshDraft() {
    if (
      !brew ||
      brew.status !== 'draft' ||
      finishing ||
      finalizing ||
      finalRatioConfirmationOpen ||
      operatorDialog ||
      changingStatus
    )
      return;
    try {
      const latest = await api<Brew>(`/brews/${brew.id}`);
      if (latest.revision <= brew.revision) return;
      brew = latest;
      actualWater = latest.water_g;
      if (latest.status !== 'draft') await handleDraftEnded(latest);
    } catch {
      // Actions still surface request failures; polling is a best-effort enhancement.
    }
  }

  async function keepAwake() {
    try {
      wakeLock = (await navigator.wakeLock?.request('screen')) ?? null;
    } catch {
      wakeLock = null;
    }
  }

  async function handleDraftEnded(latest: Brew) {
    await refreshBrewStatusAfterMutation().catch(() => undefined);
    await wakeLock?.release();
    wakeLock = null;
    const session = await ensureSession();
    if (session?.device_mode === 'kiosk') {
      await logout();
    } else if (latest.status === 'completed' && session && !session.profile.pin_change_required) {
      await loadRatingInsights();
    }
  }

  function openFinishDialog() {
    finishIssue = null;
    finishPreviouslyFocused =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    finishing = true;
  }

  async function closeFinishDialog() {
    finishing = false;
    finishIssue = null;
    await tick();
    finishPreviouslyFocused?.focus();
    finishPreviouslyFocused = null;
  }

  async function focusFinishRecoveryAction() {
    if (finishIssue?.kind !== 'review' && finishIssue?.kind !== 'reload') return;
    await tick();
    finishRecoveryButton?.focus();
  }

  function handleFinishDialogKeydown(event: KeyboardEvent) {
    if (!finishing || !finishDialog) return;
    const activeElement =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const activeDialog = activeElement?.closest('[role="dialog"], [role="alertdialog"]');
    if (activeDialog && activeDialog !== finishDialog) return;
    if (event.key === 'Escape' && !finalizing) {
      event.preventDefault();
      void closeFinishDialog();
      return;
    }
    if (event.key !== 'Tab') return;
    const controls = [
      ...finishDialog.querySelectorAll<HTMLElement>(
        'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href]'
      )
    ];
    const first = controls[0];
    const last = controls.at(-1);
    if (!first || !last) return;
    if (!finishDialog.contains(activeElement)) {
      event.preventDefault();
      (event.shiftKey ? last : first).focus();
    } else if (event.shiftKey && activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function rememberActionDialogFocus() {
    actionPreviouslyFocused =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
  }

  async function restoreActionDialogFocus() {
    const previous = actionPreviouslyFocused;
    actionPreviouslyFocused = null;
    await tick();
    if (previous?.isConnected) previous.focus();
    else document.getElementById('main-content')?.focus();
  }

  function openStatusDialog(action: 'cancel' | 'void') {
    error = '';
    rememberActionDialogFocus();
    statusAction = action;
  }

  async function closeStatusDialog() {
    statusAction = null;
    await restoreActionDialogFocus();
  }

  async function closeOperatorDialog() {
    operatorDialog = false;
    await restoreActionDialogFocus();
  }

  function handleActionDialogKeydown(event: KeyboardEvent) {
    const dialog = actionDialog;
    if ((!operatorDialog && !statusAction) || !dialog) return;
    const busy = operatorDialog ? changingOperator : changingStatus;
    if (event.key === 'Escape' && !busy) {
      event.preventDefault();
      if (operatorDialog) void closeOperatorDialog();
      else void closeStatusDialog();
      return;
    }
    if (event.key !== 'Tab') return;
    const controls = [
      ...dialog.querySelectorAll<HTMLElement>(
        'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href]'
      )
    ];
    const first = controls[0];
    const last = controls.at(-1);
    const activeElement =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (!first || !last) return;
    if (!dialog.contains(activeElement)) {
      event.preventDefault();
      (event.shiftKey ? last : first).focus();
    } else if (event.shiftKey && activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function handleDialogKeydown(event: KeyboardEvent) {
    handleFinishDialogKeydown(event);
    if (!event.defaultPrevented) handleActionDialogKeydown(event);
  }

  async function refreshAfterFinalizeConflict(brewId: number) {
    const latest = await api<Brew>(`/brews/${brewId}`);
    brew = latest;
    if (latest.status === 'draft') {
      finishIssue = {
        kind: 'review',
        message:
          'Another device changed this brew. The latest recipe is loaded. Review it before trying to finish again; your final measurements are preserved.'
      };
      return;
    }
    await closeFinishDialog();
    await handleDraftEnded(latest).catch(() => undefined);
  }

  async function reloadLatestBrew() {
    if (!brew || finalizing) return;
    finalizing = true;
    try {
      await refreshAfterFinalizeConflict(brew.id);
    } catch {
      finishIssue = {
        kind: 'reload',
        message: 'The latest brew still could not be loaded. Reload it before trying to finish.'
      };
    } finally {
      finalizing = false;
      await focusFinishRecoveryAction();
    }
  }

  async function finalize(confirmUnusualRatio = false) {
    if (!brew) return;
    if (finalBloomWaterInvalid) return;
    if (finalRatioUnusual && !confirmUnusualRatio) {
      finalRatioConfirmationOpen = true;
      return;
    }
    finalRatioConfirmationOpen = false;
    finalizing = true;
    finishIssue = null;
    error = '';
    const brewId = brew.id;
    try {
      const finalized = await api<Brew>(`/brews/${brewId}/finalize`, {
        method: 'POST',
        headers: confirmUnusualRatio ? { 'X-Confirm-Unusual-Ratio': 'true' } : undefined,
        body: jsonBody({
          water_g: actualWater,
          total_brew_time_s: finalMinutes * 60 + finalSeconds,
          revision: brew.revision,
          mark_coffee_finished: markCoffeeFinished
        })
      });
      brew = finalized;
      await closeFinishDialog();
      await handleDraftEnded(finalized).catch(() => undefined);
    } catch (caught) {
      finalRatioConfirmationOpen = false;
      if (caught instanceof ApiError && caught.status === 409) {
        finishIssue = {
          kind: 'reload',
          message: 'The brew changed on another device. Loading the latest version…'
        };
        try {
          await refreshAfterFinalizeConflict(brewId);
        } catch {
          finishIssue = {
            kind: 'reload',
            message:
              'The brew changed, but the latest version could not be loaded. Reload it before trying to finish.'
          };
        }
      } else {
        finishIssue = {
          kind: 'request',
          message: caught instanceof Error ? caught.message : 'Could not finalize the brew.'
        };
      }
    } finally {
      finalizing = false;
      await focusFinishRecoveryAction();
    }
  }

  async function copyLink() {
    if (!brew?.rating_token) return;
    const settings = await api<{ public_base_url: string }>('/settings');
    await navigator.clipboard.writeText(`${settings.public_base_url}/rate/${brew.rating_token}`);
    copied = true;
    setTimeout(() => (copied = false), 1800);
  }

  function rateOnScreenHref(): string {
    if (!brew?.rating_token) return '#';
    const ratingPath = `/rate/${brew.rating_token}`;
    return $sessionStore?.device_mode === 'personal' ? ratingPath : loginPath(ratingPath);
  }

  function canManageDraft(): boolean {
    return Boolean(
      brew &&
      $sessionStore &&
      (brew.operators.some((operator) => operator.id === $sessionStore?.profile.id) ||
        $sessionStore.profile.role === 'admin')
    );
  }

  function canControlDraft(): boolean {
    return Boolean(
      brew &&
      $sessionStore &&
      ($sessionStore.profile.id === brew.operator_id || $sessionStore.profile.role === 'admin')
    );
  }

  function hasJoined(): boolean {
    return Boolean(
      brew &&
      $sessionStore &&
      brew.operators.some((operator) => operator.id === $sessionStore?.profile.id)
    );
  }

  async function joinBrew() {
    if (!brew || joining) return;
    joining = true;
    error = '';
    try {
      brew = await api<Brew>(`/brews/${brew.id}/join`, {
        method: 'POST',
        body: jsonBody({})
      });
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not join this brew.';
    } finally {
      joining = false;
    }
  }

  function canCorrectCompleted(): boolean {
    return Boolean(
      brew &&
      $sessionStore &&
      ($sessionStore.profile.id === brew.operator_id || $sessionStore.profile.role === 'admin')
    );
  }

  async function openOperatorDialog() {
    if (!brew) return;
    error = '';
    rememberActionDialogFocus();
    try {
      if (!operators.length) operators = await api<ProfileIdentity[]>('/auth/profiles');
      selectedOperatorId = brew.operator_id;
      operatorDialog = true;
    } catch (caught) {
      actionPreviouslyFocused = null;
      error = caught instanceof Error ? caught.message : 'Could not load the operator list.';
    }
  }

  async function changeOperator() {
    if (!brew || selectedOperatorId === brew.operator_id) return;
    changingOperator = true;
    error = '';
    try {
      brew = await api<Brew>(`/brews/${brew.id}/operator`, {
        method: 'PUT',
        body: jsonBody({ operator_id: selectedOperatorId, revision: brew.revision })
      });
      await closeOperatorDialog();
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not change the operator.';
    } finally {
      changingOperator = false;
    }
  }

  async function changeStatus() {
    if (!brew || !statusAction) return;
    const action = statusAction;
    changingStatus = true;
    error = '';
    try {
      brew = await api<Brew>(`/brews/${brew.id}/${action}`, {
        method: 'POST',
        body: jsonBody({ revision: brew.revision })
      });
      await closeStatusDialog();
      await refreshBrewStatusAfterMutation().catch(() => undefined);
      await wakeLock?.release();
      if (action === 'cancel') {
        const session = await ensureSession();
        if (session?.device_mode === 'kiosk') await logout();
      }
    } catch (caught) {
      error = caught instanceof Error ? caught.message : `Could not ${action} the brew.`;
    } finally {
      changingStatus = false;
    }
  }
</script>

<svelte:window onkeydown={handleDialogKeydown} />

<svelte:head
  ><title>{brew ? `${brew.coffee_name} · Brew` : 'Brew'} · Filter Coffee Club</title></svelte:head
>

{#if error && !brew}
  <p class="error" role="alert">{error}</p>
{:else if !brew}
  <div class="empty">Finding the brew…</div>
{:else if brew.status === 'draft'}
  <section class="brew-mode">
    <div class="brew-heading">
      <div>
        <p class="eyebrow">Brew mode · settings locked on screen</p>
        <h1>{brew.coffee_name}</h1>
        <p class="lede">
          {brew.coffee_roaster} · brewed by
          {#each brew.operators as operator, index}
            {index ? ', ' : ''}<ProfileLink
              profileId={operator.id}
              displayName={operator.display_name}
            />
          {/each}
        </p>
      </div>
      <span class="status draft">draft #{brew.id}</span>
    </div>
    <div class="recipe-display">
      <article class="hero-metric">
        <strong>{brew.dose_g}<i>g</i></strong><span>total coffee dose</span>
      </article>
      <div class="arrow">→</div>
      <article class="hero-metric">
        <strong>{brew.water_g}<i>g</i></strong><span>total water</span>
      </article>
      <article class="recipe-cell"><strong>1:{brew.ratio}</strong><span>ratio</span></article>
      <article class="recipe-cell">
        <strong>{brew.temperature_c} °C</strong><span>water</span>
      </article>
      <article class="recipe-cell">
        <strong>{brew.grinder_setting}</strong><span>{brew.grinder_name} · {brew.grinder_unit}</span
        >
      </article>
      <article class="recipe-cell">
        <strong>{brew.target_flow_g_s ?? '—'} {brew.target_flow_g_s ? 'g/s' : ''}</strong><span
          >target pour rate</span
        >
      </article>
      <article class="recipe-cell">
        <strong>{brew.servings}</strong><span>serving{brew.servings === 1 ? '' : 's'}</span>
      </article>
      <article class="recipe-cell">
        <strong>{brew.dripper_name ?? '—'}</strong><span
          >{brew.filter_name ?? 'dripper / filter'}</span
        >
      </article>
    </div>
    {#if brew.bloom_water_g || brew.bloom_time_s || brew.pour_count}
      <div class="pour-strip">
        {#if brew.bloom_water_g}<span><b>{brew.bloom_water_g} g</b> bloom water</span>{/if}
        {#if brew.bloom_time_s}<span><b>{brew.bloom_time_s} s</b> bloom</span>{/if}
        {#if brew.pour_count}<span><b>{brew.pour_count}</b> pours</span>{/if}
      </div>
    {/if}
    {#if brew.technique_note}<p class="technique">{brew.technique_note}</p>{/if}
    {#if error}<p class="error" role="alert">{error}</p>{/if}
    <div class="actions brew-actions">
      {#if $sessionStore && !hasJoined()}
        <button class="primary" onclick={joinBrew} disabled={joining}
          >{joining ? 'Joining…' : 'Join brew'}</button
        >
      {/if}
      {#if canManageDraft()}
        {#if canControlDraft()}
          <button class="danger" onclick={() => openStatusDialog('cancel')}>Cancel brew</button>
          <button class="secondary" onclick={openOperatorDialog}>Change primary operator</button>
        {/if}
        <a class="button secondary" href={`/brews/new?edit=${brew.id}`}>Edit recipe</a>
        <button class="primary" onclick={openFinishDialog}>Finish brew</button>
      {/if}
    </div>
  </section>
  {#if finishing}
    <div
      class="modal-backdrop"
      role="presentation"
      onclick={(event) =>
        event.currentTarget === event.target && !finalizing && void closeFinishDialog()}
    >
      <div
        class="modal panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="finish-title"
        aria-describedby="finish-description"
        tabindex="-1"
        bind:this={finishDialog}
      >
        <div class="modal-heading">
          <p class="eyebrow">Scale result</p>
          <h2 id="finish-title">Finish this brew</h2>
          <p class="muted" id="finish-description">
            Enter the final TIMEMORE time and confirm the actual water weight.
          </p>
        </div>
        <div class="field-grid">
          <NumberStepper
            label="Minutes"
            bind:value={finalMinutes}
            min={0}
            max={59}
            inputmode="numeric"
          />
          <NumberStepper
            label="Seconds"
            bind:value={finalSeconds}
            min={0}
            max={59}
            inputmode="numeric"
          />
          <NumberStepper
            label="Actual water"
            bind:value={actualWater}
            min={1}
            max={5000}
            unit="g"
            inputmode="numeric"
          />
        </div>
        <p class:warning={finalRatioUnusual} class="finish-ratio" role="status">
          Final ratio: <strong>1:{finalRatio}</strong>{#if finalRatioUnusual}
            — outside the normal 1:10–1:25 range. Check that both amounts are whole-batch totals.
          {/if}
        </p>
        {#if finalBloomWaterInvalid}<p class="error" role="alert">
            Actual water cannot be lower than the recorded {brew.bloom_water_g} g bloom.
          </p>{/if}
        {#if finishIssue}<p class="error finish-error" role="alert">{finishIssue.message}</p>{/if}
        <label class="finish-coffee-check">
          <input type="checkbox" bind:checked={markCoffeeFinished} />
          <span>
            <strong>This was the last brew from this bag</strong>
            <small>Mark the coffee as finished and remove it from future brewing choices.</small>
          </span>
        </label>
        <div class="actions">
          {#if finishIssue?.kind === 'review'}
            <button class="primary" bind:this={finishRecoveryButton} onclick={closeFinishDialog}
              >Review latest recipe</button
            >
          {:else if finishIssue?.kind === 'reload'}
            <button
              class="primary"
              bind:this={finishRecoveryButton}
              disabled={finalizing}
              onclick={reloadLatestBrew}>{finalizing ? 'Reloading…' : 'Reload latest brew'}</button
            ><button class="secondary" disabled={finalizing} onclick={closeFinishDialog}
              >Back</button
            >
          {:else}
            <button
              class="primary"
              onclick={() => finalize()}
              disabled={finalizing ||
                finalBloomWaterInvalid ||
                finalMinutes * 60 + finalSeconds <= 0}
              >{finalizing ? 'Finalizing…' : 'Finalize and invite tasters'}</button
            ><button class="secondary" disabled={finalizing} onclick={closeFinishDialog}
              >Back</button
            >
          {/if}
        </div>
      </div>
    </div>
  {/if}
{:else if brew.status === 'completed'}
  <section class="invitation">
    <div class="invite-copy">
      <p class="eyebrow">Brew #{brew.id} is ready</p>
      <h1>Taste. Scan. Rate.</h1>
      <p class="lede">
        <strong>{brew.coffee_roaster} · {brew.coffee_name}</strong><br />Brewed by
        {#each brew.operators as operator, index}
          {index ? ', ' : ''}<ProfileLink
            profileId={operator.id}
            displayName={operator.display_name}
          />
        {/each}
        in {formatTime(brew.total_brew_time_s)}.
      </p>
      <div class="brew-summary">
        <span>1:{brew.ratio}</span><span>{brew.grinder_setting} {brew.grinder_unit}</span><span
          >{brew.temperature_c} °C</span
        >
      </div>
      <div class="actions">
        <a class="button" href={rateOnScreenHref()}>Rate on this screen</a>
        <button class="secondary" onclick={copyLink}>{copied ? 'Copied!' : 'Copy link'}</button>
        {#if canCorrectCompleted() && $deviceModeStore !== 'kiosk'}
          <a class="button secondary" href={`/brews/new?correct=${brew.id}`}>Correct brew</a>
        {/if}
        {#if $sessionStore?.profile.role === 'admin' && $deviceModeStore !== 'kiosk'}
          <button class="danger" onclick={() => openStatusDialog('void')}>Void brew</button>
        {/if}
      </div>
      <p class="hint">
        The QR opens this brew only. Each taster still signs in with their own PIN.
      </p>
    </div>
    <div class="qr-card">
      <img
        src={`/api/v1/brews/${brew.id}/qr.svg`}
        alt={`QR code to rate ${brew.coffee_name}`}
      /><strong>Open the camera on your phone</strong><span
        >Personal sessions stay signed in for 3.5 days.</span
      >
    </div>
  </section>
  {#if ratingInsights}
    <section class="group-results" aria-labelledby="group-results-heading">
      <div class="group-results-heading">
        <p class="eyebrow">Group response</p>
        <h2 id="group-results-heading">How this brew landed.</h2>
        <p class="muted">
          Anonymous averages from {ratingInsights.count}
          {ratingInsights.count === 1 ? 'rating' : 'ratings'}.
        </p>
      </div>
      <div class="group-results-layout">
        <RatingMetrics aggregate={ratingInsights} />
        <div class="group-radar panel">
          <FlavorRadar axes={ratingInsights.flavor_axes} subject={`brew ${brew.id}`} />
        </div>
      </div>
    </section>
  {:else if ratingInsightsError}
    <p class="error partial" role="status">
      The brew is available, but tasting results could not be loaded: {ratingInsightsError}
    </p>
  {:else if !$sessionStore}
    <section class="results-signin panel" aria-labelledby="results-signin-heading">
      <p class="eyebrow">Group response</p>
      <h2 id="results-signin-heading">Sign in to see this brew’s tasting results.</h2>
      <a class="button" href={loginPath(`/brews/${brew.id}`)}>Sign in</a>
    </section>
  {:else if $sessionStore.profile.pin_change_required}
    <section class="results-signin panel" aria-labelledby="results-pin-heading">
      <p class="eyebrow">Group response</p>
      <h2 id="results-pin-heading">Finish setting up your PIN to see tasting results.</h2>
      <a class="button" href="/account/pin">Change PIN</a>
    </section>
  {/if}
{:else}
  <div class="panel">
    <p class="eyebrow">Brew #{brew.id}</p>
    <h1>This brew is {brew.status}.</h1>
    <p class="lede">It is kept in the log but cannot be rated.</p>
    <a class="button secondary" href="/">Return home</a>
  </div>
{/if}

{#if operatorDialog && brew}
  <div
    class="modal-backdrop"
    role="presentation"
    onclick={(event) =>
      event.currentTarget === event.target && !changingOperator && void closeOperatorDialog()}
  >
    <div
      class="modal panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby="operator-title"
      aria-describedby="operator-description"
      tabindex="-1"
      bind:this={actionDialog}
    >
      <div class="modal-heading">
        <p class="eyebrow">Primary operator</p>
        <h2 id="operator-title">Change primary operator</h2>
        <p class="muted" id="operator-description">
          The selected profile becomes the primary operator. Existing collaborators remain credited
          and can continue editing or finishing the brew.
        </p>
      </div>
      <label>
        New operator
        <select bind:value={selectedOperatorId} disabled={changingOperator}>
          {#each operators as operator}
            <option value={operator.id}>{operator.display_name}</option>
          {/each}
        </select>
      </label>
      {#if error}<p class="error" role="alert">{error}</p>{/if}
      <div class="actions">
        <button
          class="primary"
          onclick={changeOperator}
          disabled={changingOperator || selectedOperatorId === brew.operator_id}
        >
          {changingOperator ? 'Changing…' : 'Change primary operator'}
        </button>
        <button class="secondary" onclick={closeOperatorDialog} disabled={changingOperator}
          >Keep current operator</button
        >
      </div>
    </div>
  </div>
{/if}

{#if statusAction && brew}
  <div
    class="modal-backdrop"
    role="presentation"
    onclick={(event) =>
      event.currentTarget === event.target && !changingStatus && void closeStatusDialog()}
  >
    <div
      class="modal panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby="status-title"
      aria-describedby="status-description"
      tabindex="-1"
      bind:this={actionDialog}
    >
      <div class="modal-heading">
        <p class="eyebrow">Keep the record</p>
        <h2 id="status-title">
          {statusAction === 'cancel' ? 'Cancel this draft?' : 'Void this completed brew?'}
        </h2>
        <p class="muted" id="status-description">
          {statusAction === 'cancel'
            ? 'The brew will remain in the log as cancelled and cannot be completed or rated.'
            : 'The brew and its ratings will remain stored, but its rating link will close and it will be excluded from analytics.'}
        </p>
      </div>
      {#if error}<p class="error" role="alert">{error}</p>{/if}
      <div class="actions">
        <button class="danger" onclick={changeStatus} disabled={changingStatus}>
          {changingStatus
            ? 'Saving…'
            : statusAction === 'cancel'
              ? 'Cancel draft'
              : 'Void completed brew'}
        </button>
        <button class="secondary" onclick={closeStatusDialog} disabled={changingStatus}
          >Keep brew</button
        >
      </div>
    </div>
  </div>
{/if}

{#if brew}
  <ConfirmDialog
    open={finalRatioConfirmationOpen}
    title={`Save unusual 1:${finalRatio} ratio?`}
    description={unusualBrewRatioDescription(brew.dose_g, actualWater)}
    confirmLabel={`Save 1:${finalRatio} anyway`}
    cancelLabel="Review amounts"
    busy={finalizing}
    onconfirm={() => finalize(true)}
    oncancel={() => (finalRatioConfirmationOpen = false)}
  />
{/if}

<style>
  .brew-mode {
    min-height: 68vh;
    display: grid;
    align-content: center;
    gap: 24px;
  }
  .finish-coffee-check {
    display: flex;
    align-items: flex-start;
    padding: 14px;
    border: 1px solid var(--line);
    border-radius: 14px;
    background: var(--cream);
  }
  .finish-coffee-check input {
    width: 20px;
    min-width: 20px;
    min-height: 20px;
    margin-top: 2px;
  }
  .finish-coffee-check span {
    display: grid;
    gap: 3px;
  }
  .finish-coffee-check small {
    color: var(--muted);
    font-weight: 600;
    line-height: 1.4;
  }
  .brew-heading {
    display: flex;
    justify-content: space-between;
    align-items: start;
    gap: 20px;
  }
  .brew-heading h1 {
    margin-bottom: 6px;
  }
  .recipe-display {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 12px;
  }
  .hero-metric,
  .recipe-cell {
    display: grid;
    align-content: center;
    min-height: 130px;
    padding: 20px;
    border: 1px solid var(--line);
    border-radius: 22px;
    background: var(--surface);
    box-shadow: var(--shadow);
  }
  .hero-metric {
    min-height: 190px;
    grid-column: span 2;
    row-gap: 8px;
    text-align: center;
  }
  .hero-metric strong {
    font:
      700 clamp(3.8rem, 10vw, 8rem)/0.9 Georgia,
      serif;
  }
  .hero-metric i {
    font: 700 1.2rem system-ui;
    font-style: normal;
  }
  .hero-metric span,
  .recipe-cell span {
    color: var(--muted);
    font-size: 0.75rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .arrow {
    display: none;
  }
  .recipe-cell strong {
    font-size: clamp(1.3rem, 3vw, 2rem);
    margin-bottom: 5px;
  }
  .pour-strip {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
  }
  .pour-strip span {
    padding: 10px 16px;
    border-radius: 999px;
    background: color-mix(in srgb, var(--cyan) 10%, var(--surface));
  }
  .pour-strip b {
    margin-right: 5px;
  }
  .technique {
    padding: 15px;
    border-left: 4px solid var(--amber);
    background: var(--surface);
  }
  .brew-actions {
    justify-content: flex-end;
  }
  .brew-actions .button,
  .brew-actions button {
    min-width: 180px;
  }
  .modal-backdrop {
    position: fixed;
    z-index: 50;
    inset: 0;
    display: grid;
    place-items: center;
    overflow-y: auto;
    padding: 16px;
    background: rgb(20 15 13 / 64%);
  }
  .modal {
    display: grid;
    gap: 20px;
    width: min(600px, 100%);
    max-height: calc(100dvh - 32px);
    overflow-y: auto;
    background: var(--surface);
  }
  .modal-heading {
    display: grid;
    gap: 8px;
  }
  .modal-heading > * {
    margin: 0;
  }
  .modal .actions {
    margin-top: 0;
  }
  .finish-ratio {
    margin: 0;
    color: var(--muted);
  }
  .finish-ratio.warning {
    color: #8a4a00;
  }
  .finish-error {
    margin: 0;
  }
  .invitation {
    display: grid;
    grid-template-columns: 1.1fr 0.8fr;
    gap: clamp(30px, 8vw, 100px);
    align-items: center;
    min-height: 68vh;
  }
  .group-results,
  .group-results-heading,
  .results-signin {
    display: grid;
  }
  .group-results {
    gap: 18px;
    margin-top: clamp(30px, 6vw, 70px);
  }
  .group-results-heading,
  .results-signin {
    gap: 8px;
  }
  .group-results-heading > *,
  .results-signin > * {
    margin: 0;
  }
  .group-results-heading h2,
  .results-signin h2 {
    font-size: clamp(1.8rem, 4vw, 2.7rem);
  }
  .group-results-layout {
    display: grid;
    grid-template-columns: minmax(0, 0.9fr) minmax(320px, 1.1fr);
    gap: clamp(18px, 4vw, 40px);
    align-items: center;
    min-width: 0;
  }
  .group-radar {
    min-width: 0;
    padding: clamp(12px, 3vw, 24px);
  }
  .results-signin {
    justify-items: start;
    margin-top: clamp(30px, 6vw, 70px);
  }
  .brew-summary {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin: 24px 0;
  }
  .brew-summary span {
    padding: 10px 14px;
    border-radius: 999px;
    background: var(--surface);
    font-weight: 850;
  }
  .qr-card {
    display: grid;
    justify-items: center;
    gap: 12px;
    padding: 24px;
    border: 1px solid var(--line);
    border-radius: 30px;
    background: var(--surface);
    box-shadow: var(--shadow);
    text-align: center;
  }
  .qr-card img {
    width: min(100%, 360px);
    aspect-ratio: 1;
  }
  .qr-card span {
    color: var(--muted);
    font-size: 0.85rem;
  }
  @media (max-height: 650px) {
    .modal {
      gap: 12px;
      padding: 20px;
    }
    .modal-heading {
      gap: 4px;
    }
    .modal .field-grid {
      row-gap: 10px;
    }
  }
  @media (min-width: 900px) and (max-height: 650px) {
    .brew-mode {
      min-height: 0;
      align-content: start;
      gap: 12px;
    }
    .brew-heading h1 {
      font-size: 2.7rem;
    }
    .brew-heading .lede {
      margin-bottom: 0;
    }
    .recipe-display {
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 10px;
    }
    .hero-metric {
      grid-column: span 3;
      min-height: 122px;
      padding: 14px;
    }
    .hero-metric strong {
      font-size: 4.8rem;
    }
    .recipe-cell {
      min-height: 98px;
      padding: 13px;
    }
    .recipe-cell strong {
      font-size: 1.35rem;
    }
    .brew-actions {
      margin-top: 0;
    }
    .invitation {
      min-height: 0;
    }
    .qr-card {
      padding: 14px;
      gap: 6px;
    }
    .qr-card img {
      width: min(100%, 330px);
    }
  }
  @media (max-width: 760px) {
    .recipe-display {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .hero-metric {
      grid-column: span 1;
      min-height: 150px;
    }
    .recipe-cell {
      min-height: 110px;
    }
    .invitation {
      grid-template-columns: 1fr;
    }
    .group-results-layout {
      grid-template-columns: 1fr;
    }
    .qr-card {
      order: -1;
    }
    .brew-heading {
      display: block;
    }
  }
</style>
