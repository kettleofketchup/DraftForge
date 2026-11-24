// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState, type ReactNode } from 'react';
import { I18nextProvider } from 'react-i18next';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import type { OrgFeatureAccess } from '~/features/org-features';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import { createI18nInstance } from '~/i18n/config';
import { getCandidates, resolveDiscordMember } from '../api';
import { CandidateList } from '../CandidateList';
import {
  DEFAULT_CANDIDATE_FILTERS,
  type CandidateFilters,
  type CandidateRow,
  type LinkedCandidate,
} from '../schemas';

vi.mock('../api', () => ({
  getCandidates: vi.fn(),
  resolveDiscordMember: vi.fn(),
  undoPromoSend: vi.fn(),
}));

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => {};
  Element.prototype.scrollIntoView ??= () => {};
});

afterEach(() => {
  vi.mocked(getCandidates).mockReset();
  vi.mocked(resolveDiscordMember).mockReset();
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
  recent_count: null,
  discord_joined_at: '2026-11-22T10:00:00Z',
  last_messaged: null,
  earning_send_exists: false,
  signed_up: false,
};

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <I18nextProvider i18n={createI18nInstance('en')}>
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    </I18nextProvider>
  );
}

function Harness({ onSelect }: { onSelect: (row: LinkedCandidate) => void }) {
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
      selectedPk={null}
      onSelect={onSelect}
      hideUndoFor={null}
    />
  );
}

describe('CandidateList sources', () => {
  it('switches source and resolves a Discord member without an account', async () => {
    vi.mocked(getCandidates).mockImplementation(async (_o, _e, filters) => ({
      source: filters.source,
      n: filters.n,
      days: filters.days,
      rows: filters.source === 'discord' ? [newcomer] : [],
    }));
    vi.mocked(resolveDiscordMember).mockResolvedValue({
      ...newcomer,
      user_pk: 77,
    });
    const onSelect = vi.fn();
    render(<Harness onSelect={onSelect} />, { wrapper: Wrapper });

    expect(await screen.findByTestId('promo-pool-n')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('promo-source-discord'));

    const row = await screen.findByTestId('promo-candidate-discord-990777');
    expect(row).toHaveTextContent('No account yet');
    expect(row).toHaveTextContent('Joined Discord');
    expect(screen.getByTestId('promo-days')).toBeInTheDocument();
    expect(screen.queryByTestId('promo-pool-n')).not.toBeInTheDocument();
    expect(vi.mocked(getCandidates).mock.lastCall?.[2]).toMatchObject({
      source: 'discord',
      days: 30,
    });

    fireEvent.click(screen.getByTestId('promo-select-discord-990777'));
    await waitFor(() =>
      expect(onSelect).toHaveBeenCalledWith(
        expect.objectContaining({ user_pk: 77 }),
      ),
    );
    expect(vi.mocked(resolveDiscordMember)).toHaveBeenCalledWith(
      1,
      9,
      '990777',
    );
  });
});
