import { writable } from 'svelte/store';
import type { AppSettings, Session } from './types';

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public retryAfterSeconds: number | null = null
  ) {
    super(message);
  }
}

export const sessionStore = writable<Session | null>(null);
export const appSettingsStore = writable<AppSettings | null>(null);
let sessionSnapshot: Session | null = null;
let sessionChecked = false;
sessionStore.subscribe((value) => (sessionSnapshot = value));

function detailMessage(body: unknown, fallback: string): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) return detail.map((item) => item.msg ?? String(item)).join(', ');
  }
  return fallback;
}

function retryAfterSeconds(response: Response): number | null {
  const value = response.headers.get('Retry-After');
  if (value === null) return null;
  const seconds = Number(value);
  return Number.isFinite(seconds) && seconds >= 0 ? Math.ceil(seconds) : null;
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData))
    headers.set('Content-Type', 'application/json');
  const method = (options.method ?? 'GET').toUpperCase();
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && sessionSnapshot?.csrf_token) {
    headers.set('X-CSRF-Token', sessionSnapshot.csrf_token);
  }
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    headers,
    credentials: 'same-origin'
  });
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => null);
  if (!response.ok)
    throw new ApiError(
      response.status,
      detailMessage(body, response.statusText),
      retryAfterSeconds(response)
    );
  return body as T;
}

export async function ensureSession(force = false): Promise<Session | null> {
  if (sessionChecked && !force) return sessionSnapshot;
  try {
    const session = await api<Session>('/auth/me');
    sessionStore.set(session);
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401) throw error;
    sessionStore.set(null);
  }
  sessionChecked = true;
  return sessionSnapshot;
}

export function setSession(session: Session | null): void {
  sessionChecked = true;
  sessionStore.set(session);
}

export async function logout(): Promise<void> {
  if (sessionSnapshot) await api<void>('/auth/logout', { method: 'POST' });
  setSession(null);
}

export function jsonBody(value: unknown): string {
  return JSON.stringify(value);
}

export async function uploadCatalogPhoto<T>(path: string, photo: File): Promise<T> {
  const body = new FormData();
  body.append('photo', photo);
  return api<T>(path, { method: 'PUT', body });
}

export function formatTime(seconds: number | null): string {
  if (!seconds) return '—';
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}
