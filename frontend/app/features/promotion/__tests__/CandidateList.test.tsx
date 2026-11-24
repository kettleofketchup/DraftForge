// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState, type ReactNode } from 'react';
import { I18nextProvider } from 'react-i18next';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { setViewportWidth } from '~/components/ui/data-table/__tests__/viewport';
import type { OrgFeatureAccess } from '~/features/org-features';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import { createI18nInstance } from '~/i18n/config';
import { getCandidates } from '../api';
import { CandidateList } from '../CandidateList';
import {
  DEFAULT_CANDIDATE_FILTERS,
  type CandidateFilters,
  type CandidateRow,
  type CandidatesResponse,
} from '../schemas';

vi.mock('../api', () => ({
  getCandidates: vi.fn(),
  undoPromoSend: vi.fn(),
}));

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => {};
  Element.prototype.scrollIntoView ??= () => {};
});

let restoreViewport: (() => void) | null = null;
afterEach(() => {
  vi.mocked(getCandidates).mockReset();
  restoreViewport?.();
  restoreViewport = null;
});

const access: OrgFeatureAccess = makeOrgFeatureAccess({
  viewerPk: 5,
  canUsePromotion: true,
});

const newcomer: CandidateRow = {
  user_pk: null,
  username: 'newbie',
  nickname: 'Newb',
  discordUsername: 'newbie',
  discordId: '990777',
  avatarUrl: null,
  mmr: null,
  recent_count: null,
  discord_joined_at: '2026-11-22T10:00:00Z',
  last_messaged: null,
  earning_send_exists: false,
  signed_up: false,
};

const ranked: CandidateRow = {
  ...newcomer,
  user_pk: 31,
  username: 'ranked',
  nickname: null,
  discordId: '31',
  mmr: 4500,
  recent_count: 2,
};

function respond(rows: (f: CandidateFilters) => CandidateRow[]) {
  vi.mocked(getCandidates).mockImplementation(
    async (_o, _e, filters): Promise<CandidatesResponse> => ({
      source: filters.source,
      n: filters.n,
      days: filters.days,
      game_type: 1,
      min_mmr: filters.minMmr,
      max_mmr: filters.maxMmr,
      rows: rows(filters),
    }),
  );
}

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <I18nextProvider i18n={createI18nInstance('en')}>
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    </I18nextProvider>
  );
}

function Harness({
  onCompose = vi.fn(),
  pendingRowId = null,
}: {
  onCompose?: (row: CandidateRow, mode: 'message' | 'record') => void;
  pendingRowId?: string | null;
}) {
  const [filters, setFilters] = useState<CandidateFilters>(
    DEFAULT_CANDIDATE_FILTERS,
  );
  return (
    <CandidateList
      orgId={1}
      access={access}
      eventId={9}
      filters={filters}
      onFiltersChange={setFilters}
      onCompose={onCompose}
      pendingRowId={pendingRowId}
      hideUndoFor={null}
    />
  );
}

const lastFilters = (): CandidateFilters | undefined =>
  vi.mocked(getCandidates).mock.lastCall?.[2];

describe('CandidateList', () => {
  it('switches audience and shows the window for that audience', async () => {
    respond((f) => (f.source === 'discord' ? [newcomer] : []));
    render(<Harness />, { wrapper: Wrapper });

    expect(await screen.findByTestId('promo-pool-n')).toBeInTheDocument();
    expect(screen.getByTestId('promo-source-recent')).toHaveAttribute(
      'data-state',
      'on',
    );
    fireEvent.click(screen.getByTestId('promo-source-discord'));

    const row = await screen.findByTestId('promo-candidate-row-discord-990777');
    expect(row).toHaveTextContent('No account yet');
    expect(row).toHaveTextContent('Joined Discord');
    expect(screen.getByTestId('promo-days')).toBeInTheDocument();
    expect(screen.queryByTestId('promo-pool-n')).not.toBeInTheDocument();
    expect(lastFilters()).toMatchObject({ source: 'discord', days: 30 });
    expect(screen.getByTestId('promo-active-filter-window')).toHaveTextContent(
      'Last 30 days',
    );
    expect(screen.getByTestId('promo-candidate-count')).toHaveTextContent(
      '1 player',
    );
  });

  it('applies a minimum MMR on the server, explains unknowns and resets', async () => {
    respond((f) => (f.minMmr != null ? [ranked] : [ranked, newcomer]));
    render(<Harness />, { wrapper: Wrapper });
    await screen.findByTestId('promo-candidate-row-31');
    expect(screen.getByLabelText('Min Dota 2 MMR')).toBeInTheDocument();

    fireEvent.change(screen.getByTestId('promo-min-mmr'), {
      target: { value: '4000' },
    });
    await waitFor(() => expect(lastFilters()?.minMmr).toBe(4000));
    expect(lastFilters()?.maxMmr).toBeNull();
    expect(
      await screen.findByTestId('promo-mmr-unknown-hint'),
    ).toHaveTextContent('Unknown');
    expect(screen.getByTestId('promo-active-filter-mmr')).toHaveTextContent(
      'Dota 2 MMR ≥ 4000',
    );
    await waitFor(() =>
      expect(
        screen.queryByTestId('promo-candidate-row-discord-990777'),
      ).not.toBeInTheDocument(),
    );

    fireEvent.click(screen.getByTestId('promo-filters-reset'));
    await waitFor(() => expect(lastFilters()?.minMmr).toBeNull());
    expect(screen.getByTestId('promo-min-mmr')).toHaveValue(null);
    expect(screen.queryByTestId('promo-filters-reset')).not.toBeInTheDocument();
  });

  it('does not apply an inverted MMR range', async () => {
    respond(() => [ranked]);
    render(<Harness />, { wrapper: Wrapper });
    await screen.findByTestId('promo-candidate-row-31');
    fireEvent.change(screen.getByTestId('promo-min-mmr'), {
      target: { value: '5000' },
    });
    fireEvent.change(screen.getByTestId('promo-max-mmr'), {
      target: { value: '4000' },
    });
    expect(await screen.findByTestId('promo-mmr-error')).toHaveTextContent(
      'Max MMR must be at least the min MMR',
    );
    expect(screen.getByTestId('promo-max-mmr')).toHaveAttribute(
      'aria-invalid',
      'true',
    );
    await new Promise((r) => setTimeout(r, 400));
    expect(
      vi.mocked(getCandidates).mock.calls.every(([, , f]) => f.maxMmr == null),
    ).toBe(true);
  });

  it('debounces the server search', async () => {
    respond(() => [ranked]);
    render(<Harness />, { wrapper: Wrapper });
    await screen.findByTestId('promo-candidate-row-31');
    fireEvent.change(screen.getByTestId('promo-candidate-search'), {
      target: { value: 'rank' },
    });
    await waitFor(() => expect(lastFilters()?.q).toBe('rank'));
    expect(screen.getByTestId('promo-active-filter-search')).toHaveTextContent(
      'rank',
    );
  });

  it('says why an MMR-filtered list is empty', async () => {
    respond((f) => (f.minMmr != null ? [] : [ranked]));
    render(<Harness />, { wrapper: Wrapper });
    await screen.findByTestId('promo-candidate-row-31');
    fireEvent.change(screen.getByTestId('promo-min-mmr'), {
      target: { value: '9000' },
    });
    expect(
      await screen.findByTestId('promo-candidates-empty'),
    ).toHaveTextContent('Clear the MMR filter to include Unknown');
  });

  it('hands Message and Mark as sent to the page', async () => {
    restoreViewport = setViewportWidth(1280);
    respond(() => [ranked, newcomer]);
    const onCompose = vi.fn();
    render(<Harness onCompose={onCompose} />, { wrapper: Wrapper });
    fireEvent.click(await screen.findByTestId('promo-candidate-message-31'));
    expect(onCompose).toHaveBeenLastCalledWith(ranked, 'message');
    fireEvent.click(
      screen.getByTestId('promo-candidate-record-discord-990777'),
    );
    expect(onCompose).toHaveBeenLastCalledWith(newcomer, 'record');
  });

  it('shows a load error', async () => {
    vi.mocked(getCandidates).mockRejectedValue(
      Object.assign(new Error('nope'), {
        isAxiosError: true,
        response: { status: 403, data: { detail: 'Not permitted' } },
      }),
    );
    render(<Harness />, { wrapper: Wrapper });
    expect(
      await screen.findByTestId('promo-candidates-error'),
    ).toBeInTheDocument();
  });
});
