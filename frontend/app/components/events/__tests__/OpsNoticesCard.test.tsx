// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { OpsNotice } from '~/components/api/opsNoticesAPI';

const { fetchEventOpsNotices, resolveEventOpsNotice, logger, toast } =
  vi.hoisted(() => ({
    fetchEventOpsNotices: vi.fn(),
    resolveEventOpsNotice: vi.fn(),
    logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
    toast: { error: vi.fn(), warning: vi.fn(), success: vi.fn() },
  }));

vi.mock('sonner', () => ({ toast }));

vi.mock('~/components/api/opsNoticesAPI', () => ({
  fetchEventOpsNotices,
  resolveEventOpsNotice,
}));

vi.mock('~/lib/logger', () => ({ getLogger: () => logger }));

import { OpsNoticesCard } from '../OpsNoticesCard';

function makeNotice(overrides: Partial<OpsNotice>): OpsNotice {
  return {
    id: 1,
    key: 'test.alert',
    label: 'Test alert',
    category: 'urgent',
    severity: 'critical',
    state: 'open',
    summary: 'Lobby bot is offline',
    event_id: 11,
    event_name: 'Night 4',
    subject_user: null,
    actor: null,
    dedupe_key: '',
    occurrences: 1,
    first_seen_at: new Date().toISOString(),
    last_seen_at: new Date().toISOString(),
    closed_at: null,
    close_note: '',
    delivery_state: 'pending',
    payload: {},
    ...overrides,
  };
}

const urgent = makeNotice({ id: 1, occurrences: 3 });
const task = makeNotice({
  id: 2,
  category: 'task',
  severity: 'info',
  summary: 'Check in the late players',
});

const QUERY_KEY = ['event-ops-notices', 11, 'open'];

function httpError(status: number, data: unknown): Error {
  return Object.assign(new Error(`Request failed with status ${status}`), {
    response: { status, data },
  });
}

function renderCard(noticeHref?: (n: OpsNotice) => string): {
  container: HTMLElement;
  client: QueryClient;
} {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <MemoryRouter>
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </MemoryRouter>
  );
  const result = render(
    <OpsNoticesCard eventId={11} noticeHref={noticeHref} />,
    { wrapper },
  );
  return { container: result.container, client };
}

beforeEach(() => {
  fetchEventOpsNotices.mockReset();
  resolveEventOpsNotice.mockReset();
  logger.error.mockReset();
  toast.error.mockReset();
  toast.warning.mockReset();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('OpsNoticesCard', () => {
  it('renders nothing when there are no open notices', async () => {
    fetchEventOpsNotices.mockResolvedValue([]);
    const { container, client } = renderCard();
    await waitFor(() =>
      expect(client.getQueryState(QUERY_KEY)?.status).toBe('success'),
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing while loading', () => {
    fetchEventOpsNotices.mockReturnValue(new Promise(() => {}));
    const { container } = renderCard();
    expect(container).toBeEmptyDOMElement();
  });

  it('requests urgent and task only', async () => {
    fetchEventOpsNotices.mockResolvedValue([]);
    renderCard();
    await waitFor(() =>
      expect(fetchEventOpsNotices).toHaveBeenCalledWith(11, {
        state: 'open',
        category: ['urgent', 'task'],
      }),
    );
  });

  it('lists rows with severity badge, event name and occurrence count', async () => {
    fetchEventOpsNotices.mockResolvedValue([urgent, task]);
    renderCard();
    expect(await screen.findByTestId('ops-notices-card')).toBeInTheDocument();
    expect(screen.getByText('Operations notices (2 open)')).toBeInTheDocument();
    const row = screen.getByTestId('ops-notice-row-1');
    expect(row).toHaveTextContent('Lobby bot is offline');
    expect(row).toHaveTextContent('critical');
    expect(row).toHaveTextContent('Night 4');
    expect(row).toHaveTextContent('x3');
    expect(screen.getByTestId('ops-notice-row-2')).not.toHaveTextContent('x1');
  });

  it('links the summary when noticeHref is given', async () => {
    fetchEventOpsNotices.mockResolvedValue([urgent]);
    renderCard((n) => `/ops/notices/${n.id}`);
    const link = await screen.findByRole('link', {
      name: 'Lobby bot is offline',
    });
    expect(link).toHaveAttribute('href', '/ops/notices/1');
  });

  it('renders the summary as plain text without noticeHref', async () => {
    fetchEventOpsNotices.mockResolvedValue([urgent]);
    renderCard();
    await screen.findByTestId('ops-notice-row-1');
    expect(screen.queryByRole('link')).toBeNull();
  });

  it('shows Resolve for urgent only', async () => {
    fetchEventOpsNotices.mockResolvedValue([urgent, task]);
    renderCard();
    expect(
      await screen.findByTestId('ops-notice-resolve-1'),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('ops-notice-resolve-2')).toBeNull();
  });

  it('resolving calls the API and refetches', async () => {
    fetchEventOpsNotices.mockResolvedValueOnce([urgent]).mockResolvedValue([]);
    resolveEventOpsNotice.mockResolvedValue({ ...urgent, state: 'resolved' });
    renderCard();
    fireEvent.click(await screen.findByTestId('ops-notice-resolve-1'));
    await waitFor(() =>
      expect(resolveEventOpsNotice).toHaveBeenCalledWith(11, 1),
    );
    await waitFor(() => expect(fetchEventOpsNotices).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(screen.queryByTestId('ops-notices-card')).toBeNull(),
    );
  });

  it('logs a resolve failure and shows an error toast', async () => {
    fetchEventOpsNotices.mockResolvedValue([urgent]);
    resolveEventOpsNotice.mockRejectedValue(new Error('boom'));
    renderCard();
    fireEvent.click(await screen.findByTestId('ops-notice-resolve-1'));
    await waitFor(() => expect(logger.error).toHaveBeenCalled());
    expect(toast.error).toHaveBeenCalledWith("Couldn't resolve notice: boom");
  });

  it('warns and refetches when the notice is already gone', async () => {
    fetchEventOpsNotices.mockResolvedValueOnce([urgent]).mockResolvedValue([]);
    resolveEventOpsNotice.mockRejectedValue(
      httpError(404, { detail: 'Not found.' }),
    );
    renderCard();
    fireEvent.click(await screen.findByTestId('ops-notice-resolve-1'));
    await waitFor(() =>
      expect(toast.warning).toHaveBeenCalledWith('Notice was already resolved'),
    );
    await waitFor(() => expect(fetchEventOpsNotices).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(screen.queryByTestId('ops-notices-card')).toBeNull(),
    );
  });

  it('explains a task resolve rejection and refetches', async () => {
    fetchEventOpsNotices.mockResolvedValue([urgent]);
    resolveEventOpsNotice.mockRejectedValue(
      httpError(400, { code: 'task_resolve_unsupported' }),
    );
    renderCard();
    fireEvent.click(await screen.findByTestId('ops-notice-resolve-1'));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "Couldn't resolve notice: task notices close on their own",
      ),
    );
    await waitFor(() => expect(fetchEventOpsNotices).toHaveBeenCalledTimes(2));
  });

  it('keeps loaded rows when a background refetch fails', async () => {
    fetchEventOpsNotices
      .mockResolvedValueOnce([urgent])
      .mockRejectedValue(new Error('boom'));
    const { client } = renderCard();
    await screen.findByTestId('ops-notice-row-1');
    await client.refetchQueries({ queryKey: QUERY_KEY });
    await waitFor(() =>
      expect(client.getQueryState(QUERY_KEY)?.status).toBe('error'),
    );
    expect(screen.getByTestId('ops-notice-row-1')).toBeInTheDocument();
    expect(
      await screen.findByText("Couldn't refresh operations notices"),
    ).toBeInTheDocument();
  });

  it('shows an error line on fetch failure', async () => {
    fetchEventOpsNotices.mockRejectedValue(new Error('boom'));
    renderCard();
    expect(
      await screen.findByText("Couldn't load operations notices"),
    ).toBeInTheDocument();
    expect(logger.error).toHaveBeenCalled();
  });

  it('logs a fetch failure once per failure streak', async () => {
    fetchEventOpsNotices.mockImplementation(() =>
      Promise.reject(new Error('boom')),
    );
    const { client } = renderCard();
    await screen.findByText("Couldn't load operations notices");
    await client.refetchQueries({ queryKey: QUERY_KEY });
    await waitFor(() => expect(fetchEventOpsNotices).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(client.getQueryState(QUERY_KEY)?.fetchStatus).toBe('idle'),
    );
    expect(logger.error).toHaveBeenCalledTimes(1);
  });

  it('refetches every 15 seconds', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    fetchEventOpsNotices.mockResolvedValue([urgent]);
    renderCard();
    await waitFor(() => expect(fetchEventOpsNotices).toHaveBeenCalledTimes(1));
    await vi.advanceTimersByTimeAsync(15_000);
    await waitFor(() => expect(fetchEventOpsNotices).toHaveBeenCalledTimes(2));
  });
});
