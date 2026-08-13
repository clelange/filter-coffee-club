import { writable } from 'svelte/store';
import { api } from './api';
import type { ActiveBrews } from './types';

export const brewStatusStore = writable<ActiveBrews | null>(null);

const POLL_INTERVAL_MS = 3000;
const MAX_RETRY_INTERVAL_MS = 30000;

let pendingRefresh: Promise<ActiveBrews> | null = null;
let pendingMutationRefresh: Promise<ActiveBrews> | null = null;
let pollTimer: ReturnType<typeof setTimeout> | null = null;
let pollingConsumers = 0;
let pollInFlight = false;
let retryInterval = POLL_INTERVAL_MS;

export async function refreshBrewStatus(): Promise<ActiveBrews> {
  if (pendingRefresh) return pendingRefresh;

  const request = api<ActiveBrews>('/brews/active').then((status) => {
    brewStatusStore.set(status);
    return status;
  });
  pendingRefresh = request;

  try {
    return await request;
  } finally {
    if (pendingRefresh === request) pendingRefresh = null;
  }
}

export async function refreshBrewStatusAfterMutation(): Promise<ActiveBrews> {
  if (pendingMutationRefresh) return pendingMutationRefresh;

  const previousRequest = pendingRefresh;
  pendingMutationRefresh = (async () => {
    if (previousRequest) {
      await previousRequest.catch(() => undefined);
      if (pendingRefresh === previousRequest) pendingRefresh = null;
    }
    return refreshBrewStatus();
  })();

  try {
    return await pendingMutationRefresh;
  } finally {
    pendingMutationRefresh = null;
  }
}

function clearPollTimer() {
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = null;
}

function schedulePoll(delay: number) {
  clearPollTimer();
  pollTimer = setTimeout(() => void pollBrewStatus(), delay);
}

async function pollBrewStatus() {
  if (pollingConsumers === 0 || document.hidden || pollInFlight) return;
  pollInFlight = true;
  try {
    await refreshBrewStatus();
    retryInterval = POLL_INTERVAL_MS;
  } catch {
    retryInterval = Math.min(retryInterval * 2, MAX_RETRY_INTERVAL_MS);
  } finally {
    pollInFlight = false;
    if (pollingConsumers > 0 && !document.hidden) schedulePoll(retryInterval);
  }
}

function handleVisibilityChange() {
  if (document.hidden || pollingConsumers === 0) {
    clearPollTimer();
    return;
  }
  clearPollTimer();
  void pollBrewStatus();
}

export function startBrewStatusPolling(): () => void {
  pollingConsumers += 1;
  if (pollingConsumers === 1) {
    retryInterval = POLL_INTERVAL_MS;
    document.addEventListener('visibilitychange', handleVisibilityChange);
    void pollBrewStatus();
  }

  let stopped = false;
  return () => {
    if (stopped) return;
    stopped = true;
    pollingConsumers = Math.max(0, pollingConsumers - 1);
    if (pollingConsumers === 0) {
      clearPollTimer();
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    }
  };
}
