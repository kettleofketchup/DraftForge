// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { toast } from 'sonner';
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserType } from '~/components/user/types';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import { useUserStore } from '~/store/userStore';
import { ApiAccessPanel } from '../ApiAccessPanel';
import { todayRequests, usageToday } from '../ApiUsageTable';
import {
  createApiToken,
  getApiLimits,
  getApiUsage,
  listApiTokens,
  putApiLimits,
  revokeApiToken,
} from '../api';
import { apiToken, apiUsage, createdApiToken } from './fixtures';

vi.mock('../api', () => ({
  createApiToken: vi.fn(),
  getApiLimits: vi.fn(),
  getApiUsage: vi.fn(),
  listApiTokens: vi.fn(),
  putApiLimits: vi.fn(),
  revokeApiToken: vi.fn(),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
});

const ORG = 7;
const access = makeOrgFeatureAccess({
  viewerPk: 9,
  mmrSyncEnabled: true,
  canUseMmrSync: true,
});

function setViewer(siteAdmin: boolean) {
  useUserStore.setState({
    currentUser: {
      pk: 9,
      username: 'owner',
      is_staff: siteAdmin,
    } as UserType,
  });
}

function renderPanel(a = access) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <ApiAccessPanel orgId={ORG} access={a} />
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  setViewer(false);
  vi.mocked(listApiTokens).mockResolvedValue([
    apiToken(),
    apiToken({
      id: 2,
      name: 'Old bot',
      prefix: 'zzzz0000',
      revoked_at: '2026-11-02T00:00:00Z',
      revoked_by: { pk: 9, username: 'owner' },
    }),
  ]);
  vi.mocked(getApiUsage).mockResolvedValue(apiUsage());
  vi.mocked(getApiLimits).mockResolvedValue({ per_minute: 60, per_day: 5000 });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('ApiAccessPanel', () => {
  it('lists tokens with a masked prefix and status', async () => {
    renderPanel();
    expect(await screen.findByTestId('api-token-row-1')).toBeTruthy();
    expect(screen.getByTestId('api-token-prefix-1').textContent).toBe(
      'dfk_abcd1234_…',
    );
    expect(screen.getByTestId('api-token-status-1').textContent).toBe('Active');
    expect(screen.getByTestId('api-token-status-2').textContent).toBe(
      'Revoked',
    );
    expect(screen.getByTestId('api-token-revoke-1')).toBeTruthy();
    expect(screen.queryByTestId('api-token-revoke-2')).toBeNull();
  });

  it('shows usage totals and today from the server window', async () => {
    renderPanel();
    const row = await screen.findByTestId('api-usage-row-9');
    expect(within(row).getByTestId('api-usage-requests-9').textContent).toBe(
      '42',
    );
    expect(within(row).getByText('12')).toBeTruthy();
    expect(screen.getByTestId('api-usage-table')).toBeTruthy();
  });

  it('shows read-only limits to org staff', async () => {
    renderPanel();
    expect(
      (await screen.findByTestId('api-limits-per-minute')).textContent,
    ).toBe('60');
    expect(screen.getByTestId('api-limits-per-day').textContent).toBe('5,000');
    expect(screen.queryByTestId('api-limits-form')).toBeNull();
  });

  it('lets a site admin edit limits', async () => {
    setViewer(true);
    vi.mocked(putApiLimits).mockResolvedValue({
      per_minute: 10,
      per_day: 5000,
    });
    renderPanel();
    const input = (await screen.findByTestId(
      'api-limits-per_minute',
    )) as HTMLInputElement;
    expect(input.value).toBe('60');
    fireEvent.change(input, { target: { value: '10' } });
    fireEvent.click(screen.getByTestId('api-limits-save'));
    await waitFor(() =>
      expect(putApiLimits).toHaveBeenCalledWith(ORG, {
        per_minute: 10,
        per_day: 5000,
      }),
    );
    expect(toast.success).toHaveBeenCalledWith('Rate limits saved');
  });

  it('rejects out-of-range limits before calling the API', async () => {
    setViewer(true);
    renderPanel();
    const input = await screen.findByTestId('api-limits-per_minute');
    fireEvent.change(input, { target: { value: '0' } });
    fireEvent.click(screen.getByTestId('api-limits-save'));
    expect(await screen.findByText('At least 1')).toBeTruthy();
    expect(putApiLimits).not.toHaveBeenCalled();
  });

  it('creates a token and shows the secret once', async () => {
    vi.mocked(createApiToken).mockResolvedValue(createdApiToken());
    renderPanel();
    fireEvent.click(await screen.findByTestId('api-token-create'));
    fireEvent.change(await screen.findByTestId('api-token-name'), {
      target: { value: '  MMR bot ' },
    });
    fireEvent.click(screen.getByTestId('api-token-create-submit'));
    const secret = await screen.findByTestId('api-token-secret');
    expect(secret.textContent).toBe('dfk_abcd1234_secretsecret');
    expect(createApiToken).toHaveBeenCalledWith(ORG, 'MMR bot');
    expect(screen.getByTestId('api-token-once-note')).toBeTruthy();
  });

  it('shows a create error on the name field', async () => {
    vi.mocked(createApiToken).mockRejectedValue({
      response: { data: { detail: 'Feature locked.' } },
    });
    renderPanel();
    fireEvent.click(await screen.findByTestId('api-token-create'));
    fireEvent.change(await screen.findByTestId('api-token-name'), {
      target: { value: 'bot' },
    });
    fireEvent.click(screen.getByTestId('api-token-create-submit'));
    expect(await screen.findByText('Feature locked.')).toBeTruthy();
    expect(screen.queryByTestId('api-token-secret')).toBeNull();
  });

  it('disables create while the feature is locked', async () => {
    renderPanel(
      makeOrgFeatureAccess({
        viewerPk: 9,
        mmrSyncEnabled: false,
        canUseMmrSync: true,
      }),
    );
    const button = (await screen.findByTestId(
      'api-token-create',
    )) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(screen.getByTestId('api-access-locked')).toBeTruthy();
  });

  it('revokes after confirmation', async () => {
    vi.mocked(revokeApiToken).mockResolvedValue(
      apiToken({ revoked_at: '2026-11-03T00:00:00Z' }),
    );
    renderPanel();
    fireEvent.click(await screen.findByTestId('api-token-revoke-1'));
    expect(revokeApiToken).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByTestId('api-token-revoke-confirm'));
    await waitFor(() => expect(revokeApiToken).toHaveBeenCalledWith(ORG, 1));
    expect(toast.success).toHaveBeenCalledWith('Revoked MMR bot');
  });
});

describe('usage helpers', () => {
  it('derives the server today from since and days', () => {
    expect(usageToday('2026-10-25', 30)).toBe('2026-11-23');
    expect(usageToday('2026-11-23', 1)).toBe('2026-11-23');
  });

  it('reads today requests, defaulting to zero', () => {
    const row = apiUsage().users[0];
    expect(todayRequests(row, '2026-11-23')).toBe(12);
    expect(todayRequests(row, '2026-11-01')).toBe(0);
  });
});
