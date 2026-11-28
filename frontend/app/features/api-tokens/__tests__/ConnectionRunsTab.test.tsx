// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { OrgFeatureAccess } from '~/features/org-features';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import { ConnectionRunsTab } from '../ConnectionRunsTab';
import { getConnectionRun, listConnectionRuns } from '../connectionApi';
import { RUN_POLL_MS, runPollInterval } from '../connectionQueries';
import { connectionRun } from './connectionFixtures';

vi.mock('../connectionApi', () => ({
  getConnectionRun: vi.fn(),
  listConnectionRuns: vi.fn(),
}));

const ORG = 7;
const access = makeOrgFeatureAccess({
  viewerPk: 9,
  mmrSyncEnabled: true,
  canUseMmrSync: true,
  canUseApiTokens: true,
});
const noAccess = makeOrgFeatureAccess({ viewerPk: 9 });

function setVisibility(state: DocumentVisibilityState): void {
  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    get: () => state,
  });
}

beforeEach(() => {
  setVisibility('visible');
  vi.mocked(getConnectionRun).mockReset();
  vi.mocked(listConnectionRuns).mockReset();
  vi.mocked(listConnectionRuns).mockResolvedValue({
    items: [],
    next_cursor: null,
  });
});

afterEach(() => {
  vi.useRealTimers();
  setVisibility('visible');
});

function renderRuns(initial: {
  access?: OrgFeatureAccess;
  runId?: string | null;
}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const onSelectRun = vi.fn();
  const view = (p: typeof initial): ReactNode => (
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <ConnectionRunsTab
          orgId={ORG}
          access={p.access ?? access}
          connectionId={12}
          selectedRunId={p.runId === undefined ? 'run-1' : p.runId}
          onSelectRun={onSelectRun}
        />
      </TooltipProvider>
    </QueryClientProvider>
  );
  const result = render(view(initial));
  return {
    client,
    onSelectRun,
    rerender: (next: typeof initial) =>
      result.rerender(view({ ...initial, ...next })),
  };
}

describe('ConnectionRunsTab', () => {
  it('test_polling_stops_on_terminal_hidden_or_access_loss', async () => {
    for (const state of ['queued', 'running', 'partial'] as const) {
      expect(runPollInterval(connectionRun({ state }))).toBe(RUN_POLL_MS);
    }
    for (const state of ['succeeded', 'failed', 'canceled'] as const) {
      expect(runPollInterval(connectionRun({ state }))).toBe(false);
    }
    expect(runPollInterval(undefined)).toBe(false);
    expect(runPollInterval(connectionRun({ state: 'running' }), true)).toBe(
      false,
    );
    setVisibility('hidden');
    expect(runPollInterval(connectionRun({ state: 'running' }))).toBe(false);
    setVisibility('visible');

    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(getConnectionRun)
      .mockResolvedValueOnce(connectionRun({ id: 'run-1', state: 'queued' }))
      .mockResolvedValueOnce(connectionRun({ id: 'run-1', state: 'running' }))
      .mockResolvedValue(connectionRun({ id: 'run-1', state: 'succeeded' }));
    renderRuns({});
    await waitFor(() => expect(getConnectionRun).toHaveBeenCalledTimes(1));
    await act(() => vi.advanceTimersByTimeAsync(RUN_POLL_MS));
    await waitFor(() => expect(getConnectionRun).toHaveBeenCalledTimes(2));
    await act(() => vi.advanceTimersByTimeAsync(RUN_POLL_MS));
    await waitFor(() => expect(getConnectionRun).toHaveBeenCalledTimes(3));
    expect(
      await screen.findByTestId('api-connection-run-state'),
    ).toHaveTextContent('Succeeded');
    await act(() => vi.advanceTimersByTimeAsync(RUN_POLL_MS * 3));
    expect(getConnectionRun).toHaveBeenCalledTimes(3);
    // A terminal run refreshes the history once.
    expect(listConnectionRuns).toHaveBeenCalledTimes(2);
  });

  it('stops polling a running run once access is lost', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(getConnectionRun).mockResolvedValue(
      connectionRun({ id: 'run-1', state: 'running' }),
    );
    const { rerender } = renderRuns({});
    await waitFor(() => expect(getConnectionRun).toHaveBeenCalledTimes(1));
    await act(() => vi.advanceTimersByTimeAsync(RUN_POLL_MS));
    await waitFor(() => expect(getConnectionRun).toHaveBeenCalledTimes(2));
    rerender({ access: noAccess });
    await act(() => vi.advanceTimersByTimeAsync(RUN_POLL_MS * 3));
    expect(getConnectionRun).toHaveBeenCalledTimes(2);
  });

  it('stops polling while the page is hidden', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(getConnectionRun).mockResolvedValue(
      connectionRun({ id: 'run-1', state: 'running' }),
    );
    setVisibility('hidden');
    renderRuns({});
    await waitFor(() => expect(getConnectionRun).toHaveBeenCalledTimes(1));
    await act(() => vi.advanceTimersByTimeAsync(RUN_POLL_MS * 3));
    expect(getConnectionRun).toHaveBeenCalledTimes(1);
  });

  it('shows server status, counters, worker state and coded issues only', async () => {
    vi.mocked(getConnectionRun).mockResolvedValue(
      connectionRun({
        id: 'run-1',
        kind: 'test',
        direction: 'mmr_pull',
        state: 'failed',
        error_code: 'pull_incomplete',
        issues: [
          { code: 'unmatched', page: 1, index: 4, player_id: '765611' },
          { code: 'invalid_mmr', page: 2, index: 0 },
        ],
      }),
    );
    renderRuns({});
    expect(
      await screen.findByTestId('api-connection-run-state'),
    ).toHaveTextContent('Failed');
    const counters = screen.getByTestId('api-connection-run-counters');
    expect(counters).toHaveTextContent('18 updated');
    expect(counters).toHaveTextContent('more rows than one run may fetch');
    const issues = screen.getByTestId('api-connection-run-issues');
    expect(issues).toHaveTextContent('No member matched this player ID.');
    expect(issues).toHaveTextContent('Page 1, row 4 (player 765611)');
    expect(issues).toHaveTextContent(
      'The MMR is not a whole number in range. Page 2',
    );
  });

  it('reports an unavailable worker without inventing a terminal state', async () => {
    vi.mocked(getConnectionRun).mockResolvedValue(
      connectionRun({
        id: 'run-1',
        state: 'queued',
        finished_at: null,
        worker_status: 'worker_unavailable',
      }),
    );
    renderRuns({});
    expect(
      await screen.findByTestId('api-connection-run-worker'),
    ).toHaveTextContent('No sync worker');
    expect(screen.getByTestId('api-connection-run-state')).toHaveTextContent(
      'Queued',
    );
  });

  it('lists history in the shared table with a consolidated mobile summary', async () => {
    vi.mocked(listConnectionRuns).mockResolvedValue({
      items: [
        connectionRun({
          id: 'a',
          kind: 'test',
          direction: 'mmr_push',
          health_only: true,
        }),
      ],
      next_cursor: 'more',
    });
    const { onSelectRun } = renderRuns({ runId: null });
    expect(
      await screen.findByTestId('api-connection-run-summary-a'),
    ).toHaveTextContent('Test: MMR push health · Succeeded · 18 updated');
    expect(screen.getByText('Health check only')).toBeInTheDocument();
    expect(screen.getByText('Showing the latest 50 runs.')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('api-connection-run-view-a'));
    expect(onSelectRun).toHaveBeenCalledWith('a');
  });
});
