// @vitest-environment jsdom
import { toast } from 'sonner';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../axios';

vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));

function forbidden(data: unknown) {
  return {
    config: { url: '/organizations/7/contributions/' },
    response: { status: 403, data, headers: {} },
  };
}

function reject(err: unknown): void {
  const h = api.interceptors.response.handlers?.[0];
  expect(h?.rejected).toBeDefined();
  h!.rejected!(err).catch(() => {});
}

describe('axios 403 handling', () => {
  beforeEach(() => {
    vi.mocked(toast.error).mockClear();
    delete (window as unknown as Record<string, unknown>)._auth_toast_shown;
  });

  it('does not show the session toast for a coded 403', async () => {
    reject(forbidden({ code: 'feature_locked', detail: 'Locked' }));
    await new Promise((r) => setTimeout(r, 0));
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('does not show the session toast for a not_permitted 403', async () => {
    reject(forbidden({ code: 'not_permitted', detail: 'No' }));
    await new Promise((r) => setTimeout(r, 0));
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('shows the session toast for an uncoded 403', async () => {
    reject(forbidden({ detail: 'Authentication credentials were not provided.' }));
    await vi.waitFor(() => expect(toast.error).toHaveBeenCalled());
  });
});
