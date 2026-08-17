import { writable } from 'svelte/store';
import type { AppSettings, PhotoFraming, Session } from './types';

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public code: string | null = null,
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

function errorDetail(body: unknown, fallback: string): { message: string; code: string | null } {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === 'string') return { message: detail, code: null };
    if (Array.isArray(detail)) {
      return {
        message: detail.map((item) => item.msg ?? String(item)).join(', '),
        code: null
      };
    }
    if (detail && typeof detail === 'object' && 'message' in detail) {
      const structured = detail as { message: unknown; code?: unknown };
      if (typeof structured.message === 'string') {
        return {
          message: structured.message,
          code: typeof structured.code === 'string' ? structured.code : null
        };
      }
    }
  }
  return { message: fallback, code: null };
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
  if (!response.ok) {
    const detail = errorDetail(body, response.statusText);
    throw new ApiError(response.status, detail.message, detail.code, retryAfterSeconds(response));
  }
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

export async function uploadCatalogPhoto<T>(
  path: string,
  photo: File,
  framing: PhotoFraming | null = null
): Promise<T> {
  const body = new FormData();
  body.append('photo', photo);
  if (framing) {
    body.append('focus_x', String(framing.focus_x));
    body.append('focus_y', String(framing.focus_y));
    body.append('zoom', String(framing.zoom));
  }
  return api<T>(path, { method: 'PUT', body });
}

export async function updateCatalogPhotoFraming<T>(
  path: string,
  framing: PhotoFraming | null
): Promise<T> {
  return api<T>(path, {
    method: 'PATCH',
    body: jsonBody({ photo_framing: framing })
  });
}

export function formatTime(seconds: number | null): string {
  if (!seconds) return '—';
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}
