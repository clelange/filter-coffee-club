<script lang="ts">
  import { onMount } from 'svelte';
  import { goto, replaceState } from '$app/navigation';
  import { page } from '$app/state';
  import { deviceModeStore, loginPath } from '$lib/device';
  import { api, appSettingsStore, ensureSession, jsonBody } from '$lib/api';
  import type {
    AppSettings,
    Dripper,
    FlavorTag,
    Grinder,
    MattermostChannelOption,
    MattermostSettings,
    MattermostVerifyResult,
    Preset,
    PresetInput,
    Profile
  } from '$lib/types';

  type AdminTab = 'people' | 'equipment' | 'presets' | 'settings' | 'data';
  const adminSections: { id: AdminTab; label: string }[] = [
    { id: 'people', label: 'People' },
    { id: 'equipment', label: 'Equipment' },
    { id: 'presets', label: 'Presets & flavors' },
    { id: 'settings', label: 'Settings' },
    { id: 'data', label: 'Data' }
  ];

  function isAdminTab(value: string | null): value is AdminTab {
    return adminSections.some((section) => section.id === value);
  }

  function adminTabFromUrl(url: URL): AdminTab {
    const requested = url.searchParams.get('tab');
    return isAdminTab(requested) ? requested : 'people';
  }

  let people: Profile[] = $state([]);
  let grinders: Grinder[] = $state([]);
  let drippers: Dripper[] = $state([]);
  let filters: { id: number; name: string; notes: string | null }[] = $state([]);
  let presets: Preset[] = $state([]);
  let tags: FlavorTag[] = $state([]);
  let settings: AppSettings | null = $state(null);
  let mattermost: MattermostSettings | null = $state(null);
  let mattermostCredential = $state('');
  let mattermostChannels: MattermostChannelOption[] = $state([]);
  let mattermostBusy = $state(false);
  let savedMattermostDestination = $state('');
  let savedMattermostServer = $state('');
  let activeTab: AdminTab = $state(adminTabFromUrl(page.url));
  let tabButtons: Partial<Record<AdminTab, HTMLButtonElement>> = {};
  let message = $state('');
  let error = $state('');
  let personForm = $state({ display_name: '', pin: '', role: 'member' });
  let pinResets: Record<number, string> = $state({});
  let grinderForm = $state({
    manufacturer: '',
    model: '',
    setting_unit: 'clicks',
    setting_step: 1,
    soft_min: 0,
    soft_max: 50,
    guidance: ''
  });
  let dripperForm = $state({ manufacturer: '', model: '', notes: '' });
  let filterForm = $state({ name: '', notes: '' });
  let tagForm = $state({ name: '', parent_id: null as number | null, active: true, sort_order: 0 });
  let presetForm: PresetInput = $state({
    name: '',
    ratio: 16,
    temperature_min_c: 92,
    temperature_max_c: 96,
    active: true,
    sort_order: 0,
    grinder_ranges: []
  });
  const activeTabLabel = $derived(
    adminSections.find((section) => section.id === activeTab)?.label ?? 'Admin section'
  );
  const mattermostTeams = $derived(
    Array.from(
      new Map(
        mattermostChannels.map((channel) => [
          channel.team_id,
          { id: channel.team_id, name: channel.team_display_name }
        ])
      ).values()
    )
  );
  const mattermostDestinationDirty = $derived(
    mattermost !== null && mattermostDestinationKey(mattermost) !== savedMattermostDestination
  );
  const mattermostServerChanged = $derived(
    mattermostServerDiffers(mattermost, savedMattermostServer)
  );
  const mattermostTestDirty = $derived(
    mattermostDestinationDirty || mattermostCredential.length > 0
  );
  const mattermostCredentialUnreadable = $derived(isMattermostCredentialUnreadable(mattermost));
  const mattermostConfigurationLocked = $derived(
    isMattermostConfigurationLocked(settings, mattermost)
  );

  $effect(() => {
    const requestedTab = page.url.searchParams.get('tab');
    activeTab = adminTabFromUrl(page.url);
    if (requestedTab && (!isAdminTab(requestedTab) || requestedTab === 'people')) {
      const url = new URL(window.location.href);
      url.searchParams.delete('tab');
      replaceState(url, page.state);
    }
  });

  $effect(() => {
    const requestedTab = page.url.searchParams.get('tab');
    activeTab = adminTabFromUrl(page.url);
    if (requestedTab && (!isAdminTab(requestedTab) || requestedTab === 'people')) {
      const url = new URL(window.location.href);
      url.searchParams.delete('tab');
      replaceState(url, page.state);
    }
  });

  function mattermostDestinationKey(value: MattermostSettings): string {
    return JSON.stringify([value.auth_mode, value.server_url, value.channel_id]);
  }

  function mattermostServerDiffers(value: MattermostSettings | null, savedServer: string): boolean {
    return value !== null && value.server_url !== savedServer;
  }

  function isMattermostCredentialUnreadable(value: MattermostSettings | null): boolean {
    return value?.credential_status === 'unreadable';
  }

  function isMattermostConfigurationLocked(
    appSettings: AppSettings | null,
    value: MattermostSettings | null
  ): boolean {
    return (
      appSettings?.demo_mode === true ||
      value?.encryption_available === false ||
      isMattermostCredentialUnreadable(value)
    );
  }

  function rememberMattermostDestination(): void {
    if (!mattermost) return;
    savedMattermostDestination = mattermostDestinationKey(mattermost);
    savedMattermostServer = mattermost.server_url;
  }

  function isClickUnit(unit: string) {
    return ['click', 'clicks'].includes(unit.trim().toLowerCase());
  }

  function isSeededDemoProfile(person: Profile) {
    return settings?.demo_mode && settings.demo_profile_names.includes(person.display_name);
  }

  onMount(async () => {
    if ($deviceModeStore === 'kiosk') return;
    const session = await ensureSession();
    if (!session) {
      const nextUrl = new URL(window.location.href);
      nextUrl.searchParams.delete('kiosk');
      if (activeTab === 'people') nextUrl.searchParams.delete('tab');
      else nextUrl.searchParams.set('tab', activeTab);
      await goto(loginPath(`${nextUrl.pathname}${nextUrl.search}${nextUrl.hash}`));
      return;
    }
    if (session.profile.role !== 'admin') {
      await goto('/');
      return;
    }
    await load();
    resetPresetForm();
  });

  async function load() {
    [people, grinders, drippers, filters, presets, tags, settings, mattermost] = await Promise.all([
      api<Profile[]>('/people'),
      api<Grinder[]>('/grinders'),
      api<Dripper[]>('/drippers'),
      api<{ id: number; name: string; notes: string | null }[]>('/filters'),
      api<Preset[]>('/presets?active_only=false'),
      api<FlavorTag[]>('/flavor-tags?active_only=false'),
      api<AppSettings>('/settings'),
      api<MattermostSettings>('/settings/mattermost')
    ]);
    appSettingsStore.set(settings);
    rememberMattermostDestination();
  }
  async function run(action: () => Promise<unknown>, success: string): Promise<boolean> {
    error = '';
    message = '';
    try {
      await action();
      message = success;
      await load();
      return true;
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'The change could not be saved.';
      return false;
    }
  }
  async function runSettingsAction(
    action: () => Promise<AppSettings>,
    success: string
  ): Promise<boolean> {
    error = '';
    message = '';
    try {
      const updatedSettings = await action();
      settings = updatedSettings;
      appSettingsStore.set(updatedSettings);
      message = success;
      return true;
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'The change could not be saved.';
      return false;
    }
  }
  async function addPerson(event: SubmitEvent) {
    event.preventDefault();
    await run(
      () => api('/people', { method: 'POST', body: jsonBody(personForm) }),
      'Member added.'
    );
    personForm = { display_name: '', pin: '', role: 'member' };
  }
  async function togglePerson(person: Profile) {
    await run(
      () =>
        api(`/people/${person.id}`, { method: 'PUT', body: jsonBody({ active: !person.active }) }),
      `${person.display_name} updated.`
    );
  }
  async function savePerson(person: Profile) {
    const pin = pinResets[person.id] || undefined;
    await run(
      () =>
        api(`/people/${person.id}`, {
          method: 'PUT',
          body: jsonBody({
            display_name: person.display_name,
            role: person.role,
            pin_change_required: person.pin_change_required,
            ...(pin ? { pin } : {})
          })
        }),
      `${person.display_name} updated.`
    );
    pinResets[person.id] = '';
  }
  async function addGrinder(event: SubmitEvent) {
    event.preventDefault();
    await run(
      () =>
        api('/grinders', {
          method: 'POST',
          body: jsonBody({ ...grinderForm, guidance: grinderForm.guidance || null })
        }),
      'Grinder added.'
    );
    grinderForm = {
      manufacturer: '',
      model: '',
      setting_unit: 'clicks',
      setting_step: 1,
      soft_min: 0,
      soft_max: 50,
      guidance: ''
    };
  }
  async function addDripper(event: SubmitEvent) {
    event.preventDefault();
    await run(
      () =>
        api('/drippers', {
          method: 'POST',
          body: jsonBody({
            ...dripperForm,
            manufacturer: dripperForm.manufacturer || null,
            notes: dripperForm.notes || null
          })
        }),
      'Dripper added.'
    );
    dripperForm = { manufacturer: '', model: '', notes: '' };
  }
  async function addFilter(event: SubmitEvent) {
    event.preventDefault();
    await run(
      () =>
        api('/filters', {
          method: 'POST',
          body: jsonBody({ ...filterForm, notes: filterForm.notes || null })
        }),
      'Filter added.'
    );
    filterForm = { name: '', notes: '' };
  }
  async function savePreset(preset: Preset) {
    await run(
      () =>
        api(`/presets/${preset.id}`, {
          method: 'PUT',
          body: jsonBody({
            name: preset.name,
            ratio: preset.ratio,
            temperature_min_c: preset.temperature_min_c,
            temperature_max_c: preset.temperature_max_c,
            active: preset.active,
            sort_order: preset.sort_order,
            grinder_ranges: preset.grinder_ranges
          })
        }),
      'Preset saved.'
    );
  }
  async function addPreset(event: SubmitEvent) {
    event.preventDefault();
    if (
      await run(
        () => api('/presets', { method: 'POST', body: jsonBody(presetForm) }),
        'Preset added.'
      )
    )
      resetPresetForm();
  }
  async function addTag(event: SubmitEvent) {
    event.preventDefault();
    await run(
      () => api('/flavor-tags', { method: 'POST', body: jsonBody(tagForm) }),
      'Flavor tag added.'
    );
    tagForm = { name: '', parent_id: null, active: true, sort_order: 0 };
  }
  async function saveTag(tag: FlavorTag) {
    await run(
      () =>
        api(`/flavor-tags/${tag.id}`, {
          method: 'PUT',
          body: jsonBody({
            name: tag.name,
            parent_id: tag.parent_id,
            active: tag.active,
            sort_order: tag.sort_order
          })
        }),
      'Flavor tag updated.'
    );
  }
  async function archiveEquipment(kind: 'grinders' | 'drippers' | 'filters', id: number) {
    await run(
      () => api(`/${kind}/${id}/archive`, { method: 'POST', body: jsonBody({}) }),
      'Equipment archived.'
    );
  }
  async function saveSettings(event: SubmitEvent) {
    event.preventDefault();
    if (!settings) return;
    await runSettingsAction(
      () => api<AppSettings>('/settings', { method: 'PUT', body: jsonBody(settings) }),
      'Settings saved.'
    );
  }
  function selectMattermostChannel() {
    if (!mattermost) return;
    const channel = mattermostChannels.find((item) => item.channel_id === mattermost?.channel_id);
    mattermost.team_id = channel?.team_id ?? null;
    mattermost.team_name = channel?.team_display_name ?? null;
    mattermost.channel_name = channel?.channel_name ?? null;
    mattermost.channel_display_name = channel?.channel_display_name ?? null;
  }
  function changeMattermostMode() {
    if (!mattermost) return;
    mattermostCredential = '';
    mattermostChannels = [];
    mattermost.enabled = false;
    mattermost.credential_configured = false;
    mattermost.credential_status = 'not_configured';
    mattermost.account_user_id = null;
    mattermost.account_username = null;
    mattermost.team_id = null;
    mattermost.team_name = null;
    mattermost.channel_id = null;
    mattermost.channel_name = null;
    mattermost.channel_display_name = null;
  }
  async function verifyMattermost() {
    if (!mattermost || mattermostBusy) return;
    mattermostBusy = true;
    error = '';
    message = '';
    try {
      const result = await api<MattermostVerifyResult>('/settings/mattermost/verify', {
        method: 'POST',
        body: jsonBody({
          server_url: mattermost.server_url,
          ...(mattermostCredential ? { credential: mattermostCredential } : {})
        })
      });
      mattermostChannels = result.channels;
      mattermost.account_user_id = result.user_id;
      mattermost.account_username = result.username;
      if (
        mattermost.channel_id &&
        !result.channels.some((channel) => channel.channel_id === mattermost?.channel_id)
      ) {
        mattermost.channel_id = null;
        selectMattermostChannel();
      }
      message = `Token verified as @${result.username}.`;
    } catch (caught) {
      error =
        caught instanceof Error ? caught.message : 'The Mattermost token could not be verified.';
    } finally {
      mattermostBusy = false;
    }
  }
  async function saveMattermost(event: SubmitEvent) {
    event.preventDefault();
    if (!mattermost || mattermostBusy) return;
    mattermostBusy = true;
    error = '';
    message = '';
    try {
      mattermost = await api<MattermostSettings>('/settings/mattermost', {
        method: 'PUT',
        body: jsonBody({
          enabled: mattermost.enabled,
          server_url: mattermost.server_url,
          auth_mode: mattermost.auth_mode,
          ...(mattermostCredential ? { credential: mattermostCredential } : {}),
          team_id: mattermost.team_id,
          team_name: mattermost.team_name,
          channel_id: mattermost.channel_id,
          channel_name: mattermost.channel_name,
          channel_display_name: mattermost.channel_display_name,
          announce_brew_started: mattermost.announce_brew_started,
          mention_channel_on_started: mattermost.mention_channel_on_started,
          announce_ready_to_rate: mattermost.announce_ready_to_rate,
          mention_channel_on_ready: mattermost.mention_channel_on_ready
        })
      });
      mattermostCredential = '';
      rememberMattermostDestination();
      message = 'Mattermost settings saved.';
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Mattermost settings could not be saved.';
    } finally {
      mattermostBusy = false;
    }
  }
  async function testMattermost() {
    if (!mattermost || mattermostBusy) return;
    mattermostBusy = true;
    error = '';
    message = '';
    try {
      await api('/settings/mattermost/test', { method: 'POST', body: jsonBody({}) });
      mattermost = await api<MattermostSettings>('/settings/mattermost');
      message = 'Mattermost test message delivered.';
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'The test message could not be delivered.';
    } finally {
      mattermostBusy = false;
    }
  }
  async function retryMattermost() {
    if (!mattermost || mattermostBusy) return;
    mattermostBusy = true;
    error = '';
    message = '';
    try {
      const result = await api<{ requeued: number }>('/settings/mattermost/retry', {
        method: 'POST',
        body: jsonBody({})
      });
      mattermost = await api<MattermostSettings>('/settings/mattermost');
      message = `${result.requeued} failed notification${result.requeued === 1 ? '' : 's'} queued again.`;
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Notifications could not be retried.';
    } finally {
      mattermostBusy = false;
    }
  }
  async function clearMattermostCredential() {
    if (!mattermost || mattermostBusy) return;
    mattermostBusy = true;
    error = '';
    message = '';
    try {
      mattermost = await api<MattermostSettings>('/settings/mattermost/credential', {
        method: 'DELETE'
      });
      mattermostCredential = '';
      mattermostChannels = [];
      rememberMattermostDestination();
      message = 'Mattermost credential removed and notifications disabled.';
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'The credential could not be removed.';
    } finally {
      mattermostBusy = false;
    }
  }
  async function uploadLogo(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    const body = new FormData();
    body.set('logo', file);
    if (
      await runSettingsAction(
        () => api<AppSettings>('/settings/logo', { method: 'POST', body }),
        'Logo uploaded.'
      )
    )
      input.value = '';
  }
  async function uploadBrewingLogo(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    const body = new FormData();
    body.set('logo', file);
    if (
      await runSettingsAction(
        () => api<AppSettings>('/settings/brewing-logo', { method: 'POST', body }),
        'Brewing logo uploaded.'
      )
    )
      input.value = '';
  }
  async function clearBrewingLogo() {
    await runSettingsAction(
      () => api<AppSettings>('/settings/brewing-logo', { method: 'DELETE' }),
      'The regular logo will be used while brewing.'
    );
  }
  async function restoreDefaultBrewingLogo() {
    await runSettingsAction(
      () => api<AppSettings>('/settings/brewing-logo/default', { method: 'POST' }),
      'Default brewing animation restored.'
    );
  }

  function grinderForRange(grinderId: number) {
    return grinders.find((item) => item.id === Number(grinderId));
  }
  function rangeStep(grinderId: number) {
    const grinder = grinderForRange(grinderId);
    return isClickUnit(grinder?.setting_unit ?? '') ? 1 : (grinder?.setting_step ?? 0.1);
  }
  function rangeInputMode(grinderId: number) {
    return isClickUnit(grinderForRange(grinderId)?.setting_unit ?? '') ? 'numeric' : 'decimal';
  }
  function addPresetRange() {
    const grinder = grinders.find(
      (item) => !presetForm.grinder_ranges.some((range) => range.grinder_id === item.id)
    );
    if (!grinder) return;
    presetForm.grinder_ranges = [
      ...presetForm.grinder_ranges,
      {
        grinder_id: grinder.id,
        setting_min: grinder.soft_min ?? 0,
        setting_max: grinder.soft_max ?? 50
      }
    ];
  }
  function removePresetRange(index: number) {
    presetForm.grinder_ranges = presetForm.grinder_ranges.filter(
      (_, itemIndex) => itemIndex !== index
    );
  }
  function resetPresetForm() {
    presetForm = {
      name: '',
      ratio: 16,
      temperature_min_c: 92,
      temperature_max_c: 96,
      active: true,
      sort_order: Math.max(-1, ...presets.map((preset) => preset.sort_order)) + 1,
      grinder_ranges: []
    };
    addPresetRange();
  }

  function selectTab(tab: AdminTab) {
    activeTab = tab;
    const url = new URL(window.location.href);
    if (tab === 'people') url.searchParams.delete('tab');
    else url.searchParams.set('tab', tab);
    replaceState(url, page.state);
  }
  function handleTabKeydown(event: KeyboardEvent, index: number) {
    let nextIndex: number | null = null;
    if (event.key === 'ArrowRight') nextIndex = (index + 1) % adminSections.length;
    if (event.key === 'ArrowLeft')
      nextIndex = (index - 1 + adminSections.length) % adminSections.length;
    if (event.key === 'Home') nextIndex = 0;
    if (event.key === 'End') nextIndex = adminSections.length - 1;
    if (nextIndex === null) return;
    event.preventDefault();
    const nextTab = adminSections[nextIndex].id;
    selectTab(nextTab);
    requestAnimationFrame(() => tabButtons[nextTab]?.focus());
  }
</script>

<svelte:head><title>Admin · Filter Coffee Club</title></svelte:head>
{#if $deviceModeStore === 'kiosk'}
  <section class="panel kiosk-unavailable">
    <p class="eyebrow">Personal device required</p>
    <h1>Administration is unavailable on this display.</h1>
    <p class="lede">
      Open the club on a phone or computer to manage people, equipment, presets, flavor tags,
      branding, and exports.
    </p>
    <a class="button secondary" href="/">Return home</a>
  </section>
{:else}
  <p class="eyebrow">Club controls</p>
  <h1>Configure the experiment.</h1>
  <p class="lede">
    Manage identities, shared equipment, starting points, branding, and portable data.
  </p>
  {#if settings?.demo_mode}
    <p class="demo-admin-note" role="note">
      Seeded records and branding are read-only. Create new records to try changes; everything is
      discarded during the next demo reset.
    </p>
  {/if}

  <label class="admin-section-select section" for="admin-section-select">
    Admin section
    <select
      id="admin-section-select"
      value={activeTab}
      onchange={(event) => selectTab(event.currentTarget.value as AdminTab)}
    >
      {#each adminSections as section}<option value={section.id}>{section.label}</option>{/each}
    </select>
  </label>
  <div class="tabs section" role="tablist" aria-label="Admin sections">
    {#each adminSections as section, index}
      <button
        id={`admin-tab-${section.id}`}
        type="button"
        role="tab"
        bind:this={tabButtons[section.id]}
        class:active={activeTab === section.id}
        aria-selected={activeTab === section.id}
        aria-controls="admin-panel"
        tabindex={activeTab === section.id ? 0 : -1}
        onclick={() => selectTab(section.id)}
        onkeydown={(event) => handleTabKeydown(event, index)}>{section.label}</button
      >
    {/each}
  </div>
  {#if message}<p class="success" role="status">{message}</p>{/if}{#if error}<p
      class="error"
      role="alert"
    >
      {error}
    </p>{/if}

  <div
    id="admin-panel"
    class="admin-panel"
    role="tabpanel"
    aria-labelledby={`admin-tab-${activeTab}`}
    tabindex="0"
  >
    {#if activeTab === 'people'}
      <div class="admin-grid">
        <form class="panel" onsubmit={addPerson}>
          <h2>Add a member</h2>
          <label
            >New member display name<input bind:value={personForm.display_name} required /></label
          ><label
            >Four-digit PIN<input
              bind:value={personForm.pin}
              inputmode="numeric"
              autocomplete="new-password"
              pattern="[0-9][0-9][0-9][0-9]"
              maxlength="4"
              required
            /></label
          >
          <p class="hint">
            New accounts must replace this temporary PIN after their first sign-in.
          </p>
          <label
            >Role<select bind:value={personForm.role}
              ><option value="member">Member</option><option value="admin">Administrator</option
              ></select
            ></label
          ><button class="primary">Add member</button>
        </form>
        <section class="panel profiles-panel">
          <h2>Profiles</h2>
          <div class="item-list">
            {#each people as person}<article class="profile-row">
                <input
                  aria-label="Display name"
                  bind:value={person.display_name}
                  disabled={isSeededDemoProfile(person)}
                /><select
                  aria-label={`Role for ${person.display_name}`}
                  bind:value={person.role}
                  disabled={isSeededDemoProfile(person)}
                  ><option value="member">Member</option><option value="admin">Administrator</option
                  ></select
                ><input
                  aria-label={`New PIN for ${person.display_name}`}
                  bind:value={pinResets[person.id]}
                  inputmode="numeric"
                  autocomplete="new-password"
                  pattern="[0-9][0-9][0-9][0-9]"
                  maxlength="4"
                  placeholder="New PIN"
                  disabled={isSeededDemoProfile(person)}
                /><label class="check pin-required"
                  ><input
                    type="checkbox"
                    bind:checked={person.pin_change_required}
                    disabled={isSeededDemoProfile(person)}
                  />
                  Require PIN change for {person.display_name}</label
                >
                <div class="profile-actions">
                  <button
                    class="secondary"
                    onclick={() => savePerson(person)}
                    disabled={isSeededDemoProfile(person)}>Save</button
                  ><button
                    class="secondary"
                    onclick={() => togglePerson(person)}
                    disabled={isSeededDemoProfile(person)}
                    >{person.active ? 'Deactivate' : 'Activate'}</button
                  >
                  <a class="button secondary" href={`/profiles/${person.id}`}>View profile</a>
                </div>
              </article>{/each}
          </div>
        </section>
      </div>
    {:else if activeTab === 'equipment'}
      <div class="equipment-grid">
        <form class="panel" onsubmit={addGrinder}>
          <h2>Grinder</h2>
          <label>Manufacturer<input bind:value={grinderForm.manufacturer} required /></label><label
            >Model<input bind:value={grinderForm.model} required /></label
          >
          <div class="field-grid">
            <label>Unit<input bind:value={grinderForm.setting_unit} required /></label><label
              >Step<input
                type="number"
                bind:value={grinderForm.setting_step}
                min={isClickUnit(grinderForm.setting_unit) ? 1 : 0.01}
                step={isClickUnit(grinderForm.setting_unit) ? 1 : 0.01}
                inputmode={isClickUnit(grinderForm.setting_unit) ? 'numeric' : 'decimal'}
              /></label
            ><label
              >Soft min<input
                type="number"
                bind:value={grinderForm.soft_min}
                step={isClickUnit(grinderForm.setting_unit) ? 1 : 0.01}
                inputmode={isClickUnit(grinderForm.setting_unit) ? 'numeric' : 'decimal'}
              /></label
            ><label
              >Soft max<input
                type="number"
                bind:value={grinderForm.soft_max}
                step={isClickUnit(grinderForm.setting_unit) ? 1 : 0.01}
                inputmode={isClickUnit(grinderForm.setting_unit) ? 'numeric' : 'decimal'}
              /></label
            >
          </div>
          <label>Guidance<textarea bind:value={grinderForm.guidance}></textarea></label><button
            class="primary">Add grinder</button
          >
        </form>
        <form class="panel" onsubmit={addDripper}>
          <h2>Dripper</h2>
          <label>Manufacturer<input bind:value={dripperForm.manufacturer} /></label><label
            >Model<input bind:value={dripperForm.model} required /></label
          ><label>Notes<textarea bind:value={dripperForm.notes}></textarea></label><button
            class="primary">Add dripper</button
          >
        </form>
        <form class="panel" onsubmit={addFilter}>
          <h2>Filter</h2>
          <label>Name<input bind:value={filterForm.name} required /></label><label
            >Notes<textarea bind:value={filterForm.notes}></textarea></label
          ><button class="primary">Add filter</button>
        </form>
      </div>
      <section class="panel section">
        <h2>Shared rack</h2>
        <p class="muted">Members edit details from Equipment; archive retired items here.</p>
        <div class="rack">
          <div>
            <h3>Grinders</h3>
            {#each grinders as item}<article>
                <span>{item.manufacturer} {item.model} · {item.setting_unit}</span><button
                  class="secondary"
                  onclick={() => archiveEquipment('grinders', item.id)}>Archive</button
                >
              </article>{/each}
          </div>
          <div>
            <h3>Drippers</h3>
            {#each drippers as item}<article>
                <span>{item.manufacturer ?? ''} {item.model}</span><button
                  class="secondary"
                  onclick={() => archiveEquipment('drippers', item.id)}>Archive</button
                >
              </article>{/each}
          </div>
          <div>
            <h3>Filters</h3>
            {#each filters as item}<article>
                <span>{item.name}</span><button
                  class="secondary"
                  onclick={() => archiveEquipment('filters', item.id)}>Archive</button
                >
              </article>{/each}
          </div>
        </div>
      </section>
    {:else if activeTab === 'presets'}
      <div class="stack">
        <form class="panel preset-creator" onsubmit={addPreset}>
          <h2>Add recipe preset</h2>
          <div class="preset-create-fields">
            <label>Name<input bind:value={presetForm.name} required /></label><label
              >Ratio<input
                type="number"
                bind:value={presetForm.ratio}
                min="1.1"
                max="30"
                step="0.1"
                required
              /></label
            ><label
              >Min °C<input
                type="number"
                bind:value={presetForm.temperature_min_c}
                min="50"
                max="100"
                required
              /></label
            ><label
              >Max °C<input
                type="number"
                bind:value={presetForm.temperature_max_c}
                min="50"
                max="100"
                required
              /></label
            ><label>Order<input type="number" bind:value={presetForm.sort_order} /></label><label
              class="check"><input type="checkbox" bind:checked={presetForm.active} /> Active</label
            >
          </div>
          <div class="preset-ranges">
            <div class="section-heading">
              <h3>Grinder ranges</h3>
              <button
                class="secondary"
                type="button"
                onclick={addPresetRange}
                disabled={presetForm.grinder_ranges.length >= grinders.length}
                >+ Grinder range</button
              >
            </div>
            {#each presetForm.grinder_ranges as range, index}<div class="preset-range">
                <label
                  >Grinder<select bind:value={range.grinder_id}
                    >{#each grinders as grinder}<option
                        value={grinder.id}
                        disabled={presetForm.grinder_ranges.some(
                          (item, itemIndex) => itemIndex !== index && item.grinder_id === grinder.id
                        )}>{grinder.manufacturer} {grinder.model}</option
                      >{/each}</select
                  ></label
                ><label
                  >Minimum setting<input
                    type="number"
                    bind:value={range.setting_min}
                    step={rangeStep(range.grinder_id)}
                    inputmode={rangeInputMode(range.grinder_id)}
                    required
                  /></label
                ><label
                  >Maximum setting<input
                    type="number"
                    bind:value={range.setting_max}
                    step={rangeStep(range.grinder_id)}
                    inputmode={rangeInputMode(range.grinder_id)}
                    required
                  /></label
                ><button class="secondary" type="button" onclick={() => removePresetRange(index)}
                  >Remove</button
                >
              </div>{/each}
          </div>
          <button class="primary">Add preset</button>
        </form>
        <section class="panel">
          <h2>FCC starting points</h2>
          <div class="preset-list">
            {#each presets as preset}<article>
                <input bind:value={preset.name} aria-label="Preset name" /><label
                  >Ratio<input type="number" bind:value={preset.ratio} step="0.1" /></label
                ><label>Min °C<input type="number" bind:value={preset.temperature_min_c} /></label
                ><label>Max °C<input type="number" bind:value={preset.temperature_max_c} /></label
                >{#each preset.grinder_ranges as range}<label
                    >Min clicks<input
                      type="number"
                      bind:value={range.setting_min}
                      step="1"
                    /></label
                  ><label
                    >Max clicks<input
                      type="number"
                      bind:value={range.setting_max}
                      step="1"
                    /></label
                  >{/each}<label>Order<input type="number" bind:value={preset.sort_order} /></label
                ><label class="check"
                  ><input type="checkbox" bind:checked={preset.active} /> Active</label
                ><button class="secondary" onclick={() => savePreset(preset)}>Save</button>
              </article>{/each}
          </div>
        </section>
        <div class="admin-grid">
          <form class="panel" onsubmit={addTag}>
            <h2>Add flavor tag</h2>
            <label>Name<input bind:value={tagForm.name} required /></label><label
              >Parent category<select bind:value={tagForm.parent_id}
                ><option value={null}>New broad category</option
                >{#each tags.filter((tag) => tag.parent_id === null) as tag}<option value={tag.id}
                    >{tag.name}</option
                  >{/each}</select
              ></label
            ><button class="primary">Add flavor tag</button>
          </form>
          <section class="panel">
            <h2>Current vocabulary</h2>
            <div class="tag-editor">
              {#each tags as tag}<article>
                  <input aria-label="Flavor tag name" bind:value={tag.name} /><label
                    >Order<input
                      aria-label="Flavor tag order"
                      type="number"
                      bind:value={tag.sort_order}
                    /></label
                  ><label class="check"
                    ><input type="checkbox" bind:checked={tag.active} /> Active</label
                  ><button class="secondary" onclick={() => saveTag(tag)}>Save</button>
                </article>{/each}
            </div>
          </section>
        </div>
      </div>
    {:else if activeTab === 'settings' && settings}
      <div class="stack">
        <form class="panel brand-form" onsubmit={saveSettings}>
          <div>
            <h2>Brewing</h2>
            <p class="muted">
              Limit how many draft brews can run at once. Lowering this below current usage lets
              active brews finish but blocks new ones until capacity is available.
            </p>
            <label
              >Maximum parallel brews<input
                type="number"
                min="1"
                max="20"
                bind:value={settings.max_active_brews}
                disabled={settings.demo_mode}
                required
              /></label
            >
          </div>
          <div>
            <h2>Filter Coffee Club identity</h2>
            <p class="muted">
              {settings.demo_mode
                ? 'Branding is read-only in demo mode so one visitor cannot make the site unusable.'
                : 'The Filter Coffee Club logo is used by default. Upload an approved PNG or WebP to replace it.'}
            </p>
            <label
              >Club name<input
                bind:value={settings.app_name}
                required
                disabled={settings.demo_mode}
              />
            </label><label
              >Subtitle<input bind:value={settings.subtitle} disabled={settings.demo_mode} /></label
            ><label
              >Public URL<input
                type="url"
                bind:value={settings.public_base_url}
                placeholder="https://coffee.example.psi.ch"
                disabled={settings.demo_mode}
              /><span class="hint">This exact origin is encoded in permanent QR links.</span></label
            ><label
              >Logo PNG/WebP<input
                type="file"
                accept="image/png,image/webp"
                onchange={uploadLogo}
                disabled={settings.demo_mode}
              /></label
            >
            <div class="brewing-logo-setting">
              <div>
                <h3>Brew-in-progress logo</h3>
                <p class="muted">
                  Show a separate logo while at least one brew is active. Clear it to keep using the
                  regular logo instead.
                </p>
              </div>
              {#if settings.brewing_logo_path}
                <img src={settings.brewing_logo_path} alt="Current brew-in-progress logo" />
                <label
                  >Replacement PNG/WebP<input
                    type="file"
                    accept="image/png,image/webp"
                    onchange={uploadBrewingLogo}
                    disabled={settings.demo_mode}
                  /></label
                >
                <button
                  class="secondary"
                  type="button"
                  onclick={clearBrewingLogo}
                  disabled={settings.demo_mode}>Use regular logo while brewing</button
                >
              {:else}
                <p class="muted">The regular logo is currently reused while brewing.</p>
                <button
                  class="secondary"
                  type="button"
                  onclick={restoreDefaultBrewingLogo}
                  disabled={settings.demo_mode}>Restore default brewing animation</button
                >
              {/if}
            </div>
          </div>
          <div>
            <h3>Palette</h3>
            <div class="colors">
              {#each [['color_cream', 'Background'], ['color_surface', 'Surface'], ['color_ink', 'Ink'], ['color_coffee', 'Coffee'], ['color_cyan', 'Collider'], ['color_amber', 'Accent']] as color}<label
                  >{color[1]}<input
                    type="color"
                    bind:value={settings[color[0] as keyof AppSettings] as string}
                    disabled={settings.demo_mode}
                  /></label
                >{/each}
            </div>
          </div>
          <button class="primary" disabled={settings.demo_mode}>Save settings</button>
        </form>

        {#if mattermost}
          <form
            class="panel mattermost-form"
            aria-describedby={mattermostCredentialUnreadable
              ? 'mattermost-credential-warning'
              : !mattermost.encryption_available
                ? 'mattermost-encryption-warning'
                : undefined}
            onsubmit={saveMattermost}
          >
            <div class="section-heading">
              <div>
                <p class="eyebrow">Channel notifications</p>
                <h2>Mattermost</h2>
              </div>
              <label class="check integration-enabled">
                <input
                  type="checkbox"
                  bind:checked={mattermost.enabled}
                  disabled={mattermostConfigurationLocked}
                />
                Enabled
              </label>
            </div>
            <p class="muted">
              Announce new brews and rating invitations in one channel. Incoming webhooks use the
              default channel selected when the webhook is created; personal access tokens provide
              advanced channel discovery and retry reconciliation.
            </p>
            {#if !mattermost.encryption_available}
              <p
                id="mattermost-encryption-warning"
                class="warning mattermost-lockout"
                role="status"
              >
                <strong>Mattermost setup is locked.</strong>
                Credential encryption is unavailable. Set a stable
                <code>FCC_MATTERMOST_SECRET_KEY</code> in the deployment environment, restart the application,
                and reload this page.
              </p>
            {:else if mattermostCredentialUnreadable}
              <p
                id="mattermost-credential-warning"
                class="warning mattermost-lockout"
                role="status"
              >
                <strong>Saved Mattermost credential is unreadable.</strong>
                The configured <code>FCC_MATTERMOST_SECRET_KEY</code> cannot decrypt this credential.
                Restore the original key and restart the application, or remove the credential below and
                enter it again.
              </p>
            {/if}

            <div class="field-grid mattermost-connection">
              <label>
                Authentication
                <select
                  bind:value={mattermost.auth_mode}
                  onchange={changeMattermostMode}
                  disabled={mattermostConfigurationLocked}
                >
                  <option value="webhook">Incoming webhook</option>
                  <option value="pat">Personal access token</option>
                </select>
              </label>
              <label>
                Mattermost server
                <input
                  type="url"
                  bind:value={mattermost.server_url}
                  placeholder="https://mattermost.web.cern.ch"
                  disabled={mattermostConfigurationLocked}
                  required
                />
              </label>
            </div>

            <label>
              {mattermost.auth_mode === 'pat' ? 'Personal access token' : 'Incoming webhook URL'}
              <input
                type="password"
                bind:value={mattermostCredential}
                autocomplete="new-password"
                placeholder={mattermost.credential_configured
                  ? 'Stored securely — leave blank to keep it'
                  : mattermost.auth_mode === 'pat'
                    ? 'Paste the access token'
                    : 'https://mattermost.example/hooks/…'}
                disabled={mattermostConfigurationLocked}
              />
              <span class="hint">
                {mattermost.auth_mode === 'pat'
                  ? 'Advanced: use a dedicated, non-admin service account. At CERN, ask the Mattermost team to enable PAT access.'
                  : 'The webhook URL is a secret. Its configured default channel receives every announcement.'}
              </span>
              {#if mattermostServerChanged && mattermost.credential_configured && !mattermostCredential}
                <span class="hint warning">
                  Re-enter the credential when changing the Mattermost server.
                </span>
              {/if}
            </label>

            {#if mattermost.auth_mode === 'pat'}
              <div class="connection-actions">
                <button
                  class="secondary"
                  type="button"
                  onclick={verifyMattermost}
                  disabled={mattermostConfigurationLocked ||
                    mattermostBusy ||
                    (mattermostServerChanged && !mattermostCredential) ||
                    (!mattermostCredential && !mattermost.credential_configured)}
                  >{mattermostBusy ? 'Working…' : 'Verify token & load channels'}</button
                >
                {#if mattermost.account_username}
                  <span class="connection-identity"
                    >Connected as @{mattermost.account_username}</span
                  >
                {/if}
              </div>
              <label>
                Destination channel
                <select
                  bind:value={mattermost.channel_id}
                  onchange={selectMattermostChannel}
                  disabled={mattermostConfigurationLocked || mattermostBusy}
                  required={mattermost.enabled}
                >
                  <option value={null}>Select a channel</option>
                  {#if mattermost.channel_id && !mattermostChannels.some((channel) => channel.channel_id === mattermost?.channel_id)}
                    <option value={mattermost.channel_id}>
                      {mattermost.team_name} — {mattermost.channel_display_name}
                    </option>
                  {/if}
                  {#each mattermostTeams as team}
                    <optgroup label={team.name}>
                      {#each mattermostChannels.filter((channel) => channel.team_id === team.id) as channel}
                        <option value={channel.channel_id}>{channel.channel_display_name}</option>
                      {/each}
                    </optgroup>
                  {/each}
                </select>
              </label>
            {:else}
              <p class="hint webhook-note">
                Create the webhook in the destination channel’s Mattermost integration settings. The
                app validates that the URL belongs to the server above; sending a test message is
                the only non-destructive way to verify a webhook.
              </p>
            {/if}

            <fieldset class="mattermost-events">
              <legend>Announcements</legend>
              <div>
                <label class="check">
                  <input
                    type="checkbox"
                    bind:checked={mattermost.announce_brew_started}
                    onchange={() => {
                      if (!mattermost?.announce_brew_started)
                        mattermost!.mention_channel_on_started = false;
                    }}
                    disabled={mattermostConfigurationLocked}
                  />
                  Post when a brew starts
                </label>
                <label class="check mention-option">
                  <input
                    type="checkbox"
                    bind:checked={mattermost.mention_channel_on_started}
                    disabled={mattermostConfigurationLocked || !mattermost.announce_brew_started}
                  />
                  Include @channel
                </label>
              </div>
              <div>
                <label class="check">
                  <input
                    type="checkbox"
                    bind:checked={mattermost.announce_ready_to_rate}
                    onchange={() => {
                      if (!mattermost?.announce_ready_to_rate)
                        mattermost!.mention_channel_on_ready = false;
                    }}
                    disabled={mattermostConfigurationLocked}
                  />
                  Post when rating opens
                </label>
                <label class="check mention-option">
                  <input
                    type="checkbox"
                    bind:checked={mattermost.mention_channel_on_ready}
                    disabled={mattermostConfigurationLocked || !mattermost.announce_ready_to_rate}
                  />
                  Include @channel
                </label>
              </div>
              <p class="hint">
                Channel-wide mentions only notify people when the posting account has permission;
                individual Mattermost notification preferences still apply.
              </p>
            </fieldset>

            <div class="integration-status" aria-live="polite">
              <span><strong>{mattermost.pending_count}</strong> pending</span>
              <span><strong>{mattermost.failed_count}</strong> failed</span>
              {#if mattermost.last_delivery_at}
                <span>Last delivered {new Date(mattermost.last_delivery_at).toLocaleString()}</span>
              {/if}
            </div>
            {#if mattermost.last_error}
              <p class="error" role="status">Last delivery error: {mattermost.last_error}</p>
            {/if}

            <div class="actions mattermost-actions">
              <button class="primary" disabled={mattermostConfigurationLocked || mattermostBusy}
                >{mattermostBusy ? 'Working…' : 'Save Mattermost settings'}</button
              >
              <button
                class="secondary"
                type="button"
                onclick={testMattermost}
                disabled={mattermostConfigurationLocked ||
                  mattermostBusy ||
                  mattermostTestDirty ||
                  !mattermost.credential_configured}>Send test message</button
              >
              {#if mattermostTestDirty && mattermost.credential_configured}
                <span class="hint">Save destination or credential changes before testing.</span>
              {/if}
              {#if mattermost.failed_count > 0}
                <button
                  class="secondary"
                  type="button"
                  onclick={retryMattermost}
                  disabled={mattermostConfigurationLocked || mattermostBusy || !mattermost.enabled}
                  >Retry failed</button
                >
              {/if}
              {#if mattermost.credential_configured}
                <button
                  class="secondary danger-outline"
                  type="button"
                  onclick={clearMattermostCredential}
                  disabled={settings.demo_mode || mattermostBusy}>Remove credential</button
                >
              {/if}
            </div>
          </form>
        {/if}
      </div>
    {:else if activeTab === 'data'}
      <div class="admin-grid">
        <section class="panel">
          <p class="eyebrow">Portable data</p>
          <h2>Exports</h2>
          <p class="muted">
            Exports contain catalog, brew, and rating data, but never PIN hashes, sessions, or QR
            tokens.
          </p>
          <div class="actions">
            <a class="button" href="/api/v1/exports/json">Download JSON</a><a
              class="button secondary"
              href="/api/v1/exports/csv">Download CSV ZIP</a
            >
          </div>
        </section>
        <section class="panel">
          <p class="eyebrow">Database safety</p>
          {#if settings?.demo_mode}
            <h2>Disposable demo data</h2>
            <p>
              This instance intentionally uses ephemeral SQLite storage. Visitor changes disappear
              when the service restarts and during the scheduled daily reset.
            </p>
          {:else}
            <h2>Backups</h2>
            <p>
              Back up the mounted SQLite file using the documented SQLite backup command or during a
              stopped container. Restore remains an infrastructure operation.
            </p>
            <code>sqlite3 /data/fcc.sqlite3 ".backup '/backup/fcc.sqlite3'"</code>
          {/if}
        </section>
      </div>
    {/if}
  </div>
{/if}

<style>
  .kiosk-unavailable {
    max-width: 760px;
    margin: 8vh auto 0;
  }
  .demo-admin-note {
    max-width: 72ch;
    padding: 12px 14px;
    border: 1px solid color-mix(in srgb, var(--cyan) 35%, var(--line));
    border-radius: 13px;
    background: color-mix(in srgb, var(--cyan) 7%, var(--surface));
  }
  .admin-section-select {
    display: none;
  }
  .tabs {
    display: flex;
    gap: 6px;
    overflow-x: auto;
    padding: 6px;
    border: 1px solid var(--line);
    border-radius: 999px;
    background: var(--surface);
  }
  .tabs button {
    min-height: 48px;
    padding: 9px 16px;
    border: 0;
    border-radius: 999px;
    background: transparent;
    color: var(--ink);
    cursor: pointer;
    white-space: nowrap;
  }
  .tabs button.active {
    background: var(--coffee);
    color: white;
  }
  .admin-grid {
    display: grid;
    grid-template-columns: minmax(280px, 0.7fr) minmax(0, 1.3fr);
    gap: 18px;
    margin-top: 18px;
    align-items: start;
  }
  .equipment-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
    margin-top: 18px;
    align-items: start;
  }
  .item-list,
  .rack > div {
    display: grid;
    gap: 7px;
  }
  .profiles-panel {
    min-width: 0;
    container-type: inline-size;
  }
  .profile-row {
    display: grid;
    grid-template-columns: minmax(130px, 1fr) 130px 110px minmax(150px, 1fr);
    gap: 7px;
    align-items: center;
    padding: 10px 0;
    border-bottom: 1px solid var(--line);
  }
  .profile-row > * {
    min-width: 0;
  }
  .profile-actions {
    display: flex;
    grid-column: 1 / -1;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: 7px;
  }
  .pin-required {
    min-height: auto;
    font-size: 0.78rem;
    overflow-wrap: anywhere;
  }
  .rack article {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    padding: 10px 0;
    border-bottom: 1px solid var(--line);
  }
  .rack {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 20px;
  }
  .rack span {
    padding: 8px 0;
  }
  .preset-list {
    display: grid;
    gap: 10px;
  }
  .preset-list article {
    display: grid;
    grid-template-columns: minmax(180px, 2fr) repeat(6, 82px) 90px auto;
    gap: 8px;
    align-items: end;
    padding: 10px;
    border: 1px solid var(--line);
    border-radius: 13px;
  }
  .preset-list label {
    font-size: 0.72rem;
  }
  .check {
    display: flex;
    align-items: center;
    min-height: 50px;
  }
  .check input {
    width: 20px;
    min-height: 20px;
  }
  .preset-creator {
    display: grid;
    gap: 18px;
  }
  .preset-create-fields {
    display: grid;
    grid-template-columns: minmax(180px, 2fr) repeat(4, minmax(80px, 1fr)) auto;
    gap: 10px;
    align-items: end;
  }
  .preset-ranges {
    display: grid;
    gap: 10px;
  }
  .preset-ranges h3 {
    margin: 0;
  }
  .preset-range {
    display: grid;
    grid-template-columns: minmax(180px, 1.5fr) 1fr 1fr auto;
    gap: 10px;
    align-items: end;
    padding: 12px;
    border: 1px solid var(--line);
    border-radius: 13px;
  }
  .tag-editor {
    display: grid;
    gap: 7px;
  }
  .tag-editor article {
    display: grid;
    grid-template-columns: 1fr 84px 95px auto;
    gap: 7px;
    align-items: end;
  }
  .tag-editor label {
    font-size: 0.72rem;
  }
  .brand-form {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 30px;
    margin-top: 18px;
  }
  .mattermost-form {
    display: grid;
    gap: 20px;
  }
  .mattermost-form h2,
  .mattermost-form .eyebrow {
    margin-bottom: 0;
  }
  .integration-enabled {
    min-height: auto;
  }
  .mattermost-lockout {
    display: grid;
    gap: 6px;
    margin: 0;
    padding: 14px 16px;
    border: 1px solid currentColor;
    border-radius: 12px;
  }
  .mattermost-lockout strong {
    font-size: 1rem;
  }
  .mattermost-connection {
    grid-template-columns: minmax(200px, 0.7fr) minmax(280px, 1.3fr);
  }
  .connection-actions,
  .integration-status {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px 18px;
  }
  .connection-identity,
  .integration-status span {
    padding: 8px 10px;
    border-radius: 999px;
    background: color-mix(in srgb, var(--cyan) 8%, var(--surface));
    font-size: 0.86rem;
  }
  .mattermost-events {
    display: grid;
    gap: 10px;
  }
  .mattermost-events > div {
    display: grid;
    grid-template-columns: minmax(220px, 1fr) minmax(150px, 0.7fr);
    gap: 10px;
    align-items: center;
  }
  .mattermost-events .check {
    min-height: 40px;
  }
  .mention-option {
    padding-left: 12px;
    border-left: 2px solid var(--line);
  }
  .webhook-note {
    padding: 12px 14px;
    border: 1px solid var(--line);
    border-radius: 12px;
  }
  .warning code {
    display: inline;
    padding: 2px 4px;
    color: inherit;
    background: color-mix(in srgb, currentColor 10%, transparent);
  }
  .brewing-logo-setting {
    display: grid;
    gap: 12px;
    margin-top: 20px;
    padding-top: 20px;
    border-top: 1px solid var(--line);
  }
  .brewing-logo-setting h3,
  .brewing-logo-setting p {
    margin: 0;
  }
  .brewing-logo-setting img {
    width: 96px;
    height: 96px;
    object-fit: contain;
  }
  .brewing-logo-setting button {
    justify-self: start;
  }
  .colors {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }
  .colors label {
    grid-template-columns: 1fr 60px;
    align-items: center;
  }
  .colors input {
    padding: 4px;
  }
  code {
    display: block;
    overflow: auto;
    padding: 12px;
    border-radius: 10px;
    background: var(--ink);
    color: var(--cream);
  }
  @container (max-width: 560px) {
    .profile-row {
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    }
  }
  @media (max-width: 900px) {
    .equipment-grid {
      grid-template-columns: 1fr 1fr;
    }
    .preset-create-fields,
    .preset-list article {
      grid-template-columns: 1fr 1fr 1fr;
    }
    .brand-form {
      grid-template-columns: 1fr;
    }
    .mattermost-connection {
      grid-template-columns: 1fr;
    }
    .tag-editor article {
      grid-template-columns: 1fr 80px auto;
    }
    .profile-row {
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    }
  }
  @media (max-width: 650px) {
    .tabs {
      display: none;
    }
    .admin-section-select {
      display: grid;
    }
    .admin-grid,
    .equipment-grid {
      grid-template-columns: 1fr;
    }
    .rack {
      grid-template-columns: 1fr;
    }
    .preset-create-fields,
    .preset-range,
    .preset-list article {
      grid-template-columns: 1fr 1fr;
    }
    .mattermost-events > div {
      grid-template-columns: 1fr;
    }
    .tag-editor article {
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    }
  }
</style>
