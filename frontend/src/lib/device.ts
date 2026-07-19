import { get, writable } from 'svelte/store';
import type { DeviceMode } from './types';

const STORAGE_KEY = 'fcc-device-mode';

export const deviceModeStore = writable<DeviceMode>('personal');

let configured = false;

function storedMode(): DeviceMode | null {
  const value = localStorage.getItem(STORAGE_KEY);
  return value === 'kiosk' || value === 'personal' ? value : null;
}

function applyMode(mode: DeviceMode, persist: boolean) {
  deviceModeStore.set(mode);
  document.documentElement.dataset.deviceMode = mode;
  if (persist) localStorage.setItem(STORAGE_KEY, mode);
}

function removeActivationParameters(url: URL) {
  const cleaned = new URL(url);
  cleaned.searchParams.delete('kiosk');
  if (url.pathname === '/login' && url.searchParams.get('mode') === 'kiosk') {
    cleaned.searchParams.delete('mode');
  }
  if (cleaned.href !== url.href) {
    history.replaceState(history.state, '', `${cleaned.pathname}${cleaned.search}${cleaned.hash}`);
  }
}

export function initializeDeviceMode(url: URL): { configured: boolean; mode: DeviceMode } {
  const kioskFlag = url.searchParams.get('kiosk');
  const legacyKioskLogin = url.pathname === '/login' && url.searchParams.get('mode') === 'kiosk';

  if (kioskFlag === '1' || legacyKioskLogin) {
    configured = true;
    applyMode('kiosk', true);
    removeActivationParameters(url);
  } else if (kioskFlag === '0') {
    configured = true;
    applyMode('personal', true);
    removeActivationParameters(url);
  } else {
    const stored = storedMode();
    configured = stored !== null;
    applyMode(stored ?? 'personal', false);
  }

  return { configured, mode: get(deviceModeStore) };
}

export function adoptSessionDeviceMode(mode: DeviceMode) {
  if (configured) return;
  configured = true;
  applyMode(mode, true);
}

export function currentDeviceMode(): DeviceMode {
  return get(deviceModeStore);
}

export function loginPath(next?: string): string {
  if (!next) return '/login';
  const params = new URLSearchParams({ next });
  return `/login?${params.toString()}`;
}
