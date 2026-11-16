// @vitest-environment jsdom
import { toast } from 'sonner';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  getActivityCredential,
  isActivityFrame,
  refreshActivityCredential,
} from '~/lib/activity-session';
import { api, setActivityErrorHandlers } from '../axios';

vi.mock('sonner', () => ({ toast: { error: vi.fn(), info: vi.fn() } }));
vi.mock('~/lib/activity-session', () => ({
  activityAuthorization: vi.fn(),
  getActivityCredential: vi.fn(),
  isActivityFrame: vi.fn(),
  refreshActivityCredential: vi.fn(),
}));

type Cfg = Record<string, unknown>;

const onScopeLost = vi.fn();
const onDisabled = vi.fn();
let token = 'A';

function stubAdapter(config: Cfg) {
  const adapter = vi.fn((c: Cfg) =>
    Promise.resolve({
      status: 200,
      statusText: 'OK',
      data: { ok: true },
      headers: {},
      config: c,
    }),
  );
  config.adapter = adapter;
  return adapter;
}

function failure(
  status: number,
  data: unknown,
  extra: Cfg = {},
): { config: Cfg; response: Cfg; adapter: ReturnType<typeof stubAdapter> } {
  const config: Cfg = {
    url: '/herodraft/9/submit-pick/',
    method: 'post',
    headers: {},
    _activityToken: 'A',
    ...extra,
  };
  const adapter = stubAdapter(config);
  return { config, response: { status, data, headers: {} }, adapter };
}

function rejected(err: unknown): Promise<unknown> {
  const h = api.interceptors.response.handlers?.[0];
  expect(h?.rejected).toBeDefined();
  return h!.rejected!(err);
}

async function flush() {
  await new Promise((r) => setTimeout(r, 0));
}

function anyLogIn(): boolean {
  return vi
    .mocked(toast.error)
    .mock.calls.some(
      ([, opts]) =>
        (opts as { action?: { label?: string } } | undefined)?.action?.label ===
        'Log In',
    );
}

describe('axios inside the Activity frame', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    delete (window as unknown as Record<string, unknown>)._auth_toast_shown;
    token = 'A';
    vi.mocked(isActivityFrame).mockReturnValue(true);
    vi.mocked(getActivityCredential).mockImplementation(
      () =>
        ({
          token,
          scope: 'tournament',
          tournament_id: 1,
          pin: null,
          site_url: null,
        }) as ReturnType<typeof getActivityCredential>,
    );
    const session = await import('~/lib/activity-session');
    vi.mocked(session.activityAuthorization).mockImplementation(
      () => `DraftActivity ${token}`,
    );
    setActivityErrorHandlers({ onScopeLost, onDisabled });
  });

  afterEach(() => {
    setActivityErrorHandlers(null);
  });

  it('records the token it attached', async () => {
    const h = api.interceptors.request.handlers?.[0];
    const config = (await h!.fulfilled!({
      url: '/herodraft/9/',
      headers: {},
    } as never)) as unknown as Cfg;
    expect(config._activityToken).toBe('A');
    expect((config.headers as Cfg).Authorization).toBe('DraftActivity A');
  });

  it('shows the server text for an uncoded hero 403 without refreshing', async () => {
    const { config, response } = failure(403, { error: 'Not your turn' });
    await expect(rejected({ config, response })).rejects.toBeDefined();
    await flush();
    expect(toast.error).toHaveBeenCalledWith('Not your turn');
    expect(refreshActivityCredential).not.toHaveBeenCalled();
    expect(anyLogIn()).toBe(false);
  });

  it('shows a coded 403 without refreshing', async () => {
    const { config, response } = failure(403, {
      code: 'not_permitted',
      detail: 'Captains only',
    });
    await expect(rejected({ config, response })).rejects.toBeDefined();
    await flush();
    expect(toast.error).toHaveBeenCalledWith('Captains only');
    expect(refreshActivityCredential).not.toHaveBeenCalled();
    expect(anyLogIn()).toBe(false);
  });

  it('refreshes once and retries once when the session ended', async () => {
    vi.mocked(refreshActivityCredential).mockImplementation(async () => {
      token = 'B';
      return true;
    });
    const { config, response, adapter } = failure(401, {
      code: 'activity_session_ended',
    });
    const result = (await rejected({ config, response })) as Cfg;
    expect(result.status).toBe(200);
    expect(refreshActivityCredential).toHaveBeenCalledTimes(1);
    expect(adapter).toHaveBeenCalledTimes(1);
    const retried = adapter.mock.calls[0][0] as Cfg;
    expect(retried._activityRetried).toBe(true);
    expect((retried.headers as Record<string, string>).Authorization).toBe(
      'DraftActivity B',
    );
    await flush();
    expect(toast.info).toHaveBeenCalledWith('Reconnecting…', expect.anything());
  });

  it('retries a stale-token request with the current token without refreshing', async () => {
    token = 'B';
    vi.mocked(refreshActivityCredential).mockResolvedValue(false);
    const { config, response, adapter } = failure(401, {
      code: 'activity_session_ended',
    });
    const result = (await rejected({ config, response })) as Cfg;
    expect(result.status).toBe(200);
    expect(refreshActivityCredential).not.toHaveBeenCalled();
    expect(adapter).toHaveBeenCalledTimes(1);
    const retried = adapter.mock.calls[0][0] as Cfg;
    expect((retried.headers as Record<string, string>).Authorization).toBe(
      'DraftActivity B',
    );
    expect(retried._activityRetried).toBe(true);
  });

  it('rejects without retrying when the refresh fails', async () => {
    vi.mocked(refreshActivityCredential).mockResolvedValue(false);
    const { config, response, adapter } = failure(401, {
      code: 'activity_session_ended',
    });
    await expect(rejected({ config, response })).rejects.toBeDefined();
    expect(refreshActivityCredential).toHaveBeenCalledTimes(1);
    expect(adapter).not.toHaveBeenCalled();
  });

  it('does not retry a request that was already retried', async () => {
    vi.mocked(refreshActivityCredential).mockResolvedValue(true);
    const { config, response, adapter } = failure(
      401,
      { code: 'activity_session_ended' },
      { _activityRetried: true },
    );
    await expect(rejected({ config, response })).rejects.toBeDefined();
    expect(refreshActivityCredential).not.toHaveBeenCalled();
    expect(adapter).not.toHaveBeenCalled();
  });

  it('hands out of scope to the route without refreshing', async () => {
    const { config, response } = failure(401, {
      code: 'activity_out_of_scope',
    });
    await expect(rejected({ config, response })).rejects.toBeDefined();
    expect(onScopeLost).toHaveBeenCalledTimes(1);
    expect(refreshActivityCredential).not.toHaveBeenCalled();
  });

  it('hands disabled to the route without refreshing', async () => {
    const { config, response } = failure(401, { code: 'activity_disabled' });
    await expect(rejected({ config, response })).rejects.toBeDefined();
    expect(onDisabled).toHaveBeenCalledTimes(1);
    expect(refreshActivityCredential).not.toHaveBeenCalled();
  });

  it('shows a toast for a path the Activity may not call', async () => {
    const { config, response } = failure(401, {
      code: 'activity_path_not_allowed',
    });
    await expect(rejected({ config, response })).rejects.toBeDefined();
    await flush();
    expect(toast.error).toHaveBeenCalledWith(
      'This action is not available in the Activity.',
    );
    expect(refreshActivityCredential).not.toHaveBeenCalled();
  });

  it.each([401, 403])(
    'rejects a skip-flagged %i with no toast, refresh or handler',
    async (status) => {
      const code = status === 401 ? 'activity_session_ended' : undefined;
      const { config, response, adapter } = failure(
        status,
        { code },
        { skipActivityErrorHandling: true },
      );
      await expect(rejected({ config, response })).rejects.toBeDefined();
      await flush();
      expect(toast.error).not.toHaveBeenCalled();
      expect(toast.info).not.toHaveBeenCalled();
      expect(refreshActivityCredential).not.toHaveBeenCalled();
      expect(onScopeLost).not.toHaveBeenCalled();
      expect(onDisabled).not.toHaveBeenCalled();
      expect(adapter).not.toHaveBeenCalled();
      expect(
        (window as unknown as Record<string, unknown>)._auth_toast_shown,
      ).toBeUndefined();
    },
  );

  it('never offers Log In or navigates for an uncoded 401', async () => {
    const original = window.location;
    const hrefSet = vi.fn();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        pathname: '/activity',
        get href() {
          return 'https://example.test/activity';
        },
        set href(v: string) {
          hrefSet(v);
        },
      },
    });
    try {
      const { config, response } = failure(401, {});
      await expect(rejected({ config, response })).rejects.toBeDefined();
      await flush();
      expect(toast.error).toHaveBeenCalledWith(
        'The Activity could not verify you. Reopen the Activity if this keeps happening.',
      );
      expect(anyLogIn()).toBe(false);
      expect(hrefSet).not.toHaveBeenCalled();
      expect(refreshActivityCredential).not.toHaveBeenCalled();
    } finally {
      Object.defineProperty(window, 'location', {
        configurable: true,
        value: original,
      });
    }
  });
});

describe('axios outside the Activity frame', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    delete (window as unknown as Record<string, unknown>)._auth_toast_shown;
    vi.mocked(isActivityFrame).mockReturnValue(false);
    vi.mocked(getActivityCredential).mockReturnValue(null);
  });

  it('keeps the session expired toast on the website', async () => {
    const { config, response } = failure(401, {}, { url: '/tournaments/3/' });
    await expect(rejected({ config, response })).rejects.toBeDefined();
    await vi.waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        'Session expired — please log in again',
        expect.anything(),
      ),
    );
    expect(refreshActivityCredential).not.toHaveBeenCalled();
  });
});
