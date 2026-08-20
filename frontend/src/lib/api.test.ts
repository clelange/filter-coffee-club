import { get } from 'svelte/store';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, ensureSession, logout, sessionStore, setSession } from './api';
import type { Session } from './types';

function session(expiresAt = '2030-01-01T00:00:00Z'): Session {
  return {
    profile: {
      id: 1,
      display_name: 'Ada',
      role: 'admin',
      active: true,
      pin_change_required: false
    },
    csrf_token: 'csrf-token',
    device_mode: 'personal',
    expires_at: expiresAt
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  setSession(null);
});

describe('session lifecycle', () => {
  it('clears a locally expired cached session without making a request', async () => {
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    setSession(session('2000-01-01T00:00:00Z'));

    await expect(ensureSession()).resolves.toBeNull();
    expect(get(sessionStore)).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('clears stale state when an authenticated request returns 401', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: 'Sign in required' }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' }
        })
      )
    );
    setSession(session());

    await expect(api('/people')).rejects.toMatchObject({ status: 401 });
    expect(get(sessionStore)).toBeNull();
  });

  it('preserves the current session when a separate login attempt is rejected', async () => {
    const currentSession = session();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: 'Invalid profile or PIN' }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' }
        })
      )
    );
    setSession(currentSession);

    await expect(api('/auth/login', { method: 'POST' })).rejects.toMatchObject({ status: 401 });
    expect(get(sessionStore)).toEqual(currentSession);
  });

  it('treats an already-expired server session as a completed logout', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: 'Sign in required' }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' }
        })
      )
    );
    setSession(session());

    await expect(logout()).resolves.toBeUndefined();
    expect(get(sessionStore)).toBeNull();
  });

  it('preserves the current session when logout fails before the server accepts it', async () => {
    const currentSession = session();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: 'Temporary failure' }), {
          status: 503,
          headers: { 'Content-Type': 'application/json' }
        })
      )
    );
    setSession(currentSession);

    await expect(logout()).rejects.toMatchObject({ status: 503 });
    expect(get(sessionStore)).toEqual(currentSession);
  });
});
