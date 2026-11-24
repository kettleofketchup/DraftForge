// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState, type ReactNode } from 'react';
import { I18nextProvider } from 'react-i18next';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import type { OrgFeatureAccess } from '~/features/org-features';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import { createI18nInstance } from '~/i18n/config';
import { getCandidates, resolveDiscordMember, undoPromoSend } from '../api';
import { CandidateList } from '../CandidateList';
import {
  DEFAULT_CANDIDATE_FILTERS,
  type CandidateFilters,
  type CandidateRow,
  type LinkedCandidate,
} from '../schemas';
import {
  NO_SYNC,
  SFG_CONTACT,
  SYNC_CONFIGURED,
  candidateRow,
  candidatesResponse,
} from './fixtures';

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
  vi.mocked(undoPromoSend).mockReset();
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
  contact_recorded: false,
  external_contact: null,
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

function Harness({
  onSelect,
  initialFilters = DEFAULT_CANDIDATE_FILTERS,
}: {
  onSelect: (row: LinkedCandidate) => void;
  initialFilters?: CandidateFilters;
}) {
  const [filters, setFilters] = useState<CandidateFilters>(initialFilters);
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
      contact_sync: NO_SYNC,
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

const SHOW_MESSAGED: CandidateFilters = {
  ...DEFAULT_CANDIDATE_FILTERS,
  hideMessaged: false,
};

const localSend = {
  send_id: 77,
  by: 'Promoter Pat',
  sent_at: '2026-11-24T10:00:00Z',
  can_undo: true,
};

describe('CandidateList recorded contacts', () => {
  it('asks the server to hide messaged players by default', async () => {
    vi.mocked(getCandidates).mockResolvedValue(candidatesResponse([]));
    render(<Harness onSelect={vi.fn()} />, { wrapper: Wrapper });
    await screen.findByTestId('promo-candidates-empty');
    expect(vi.mocked(getCandidates).mock.lastCall?.[2]).toMatchObject({
      hideMessaged: true,
    });
  });

  it('shows an imported contact as a read-only tick with messaging disabled and no undo', async () => {
    vi.mocked(getCandidates).mockResolvedValue(
      candidatesResponse([
        candidateRow({ contact_recorded: true, external_contact: SFG_CONTACT }),
      ]),
    );
    const onSelect = vi.fn();
    render(<Harness onSelect={onSelect} initialFilters={SHOW_MESSAGED} />, {
      wrapper: Wrapper,
    });
    const tick = await screen.findByRole('checkbox', {
      name: 'Contact recorded in SFG',
    });
    expect(tick).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByTestId('promo-candidate-42')).toHaveTextContent(
      'Delivery not verified',
    );
    const message = screen.getByTestId('promo-select-42');
    expect(message).toBeDisabled();
    expect(message).toHaveAttribute('aria-pressed', 'false');
    expect(message).toHaveAccessibleDescription(/Contact recorded in SFG/);
    fireEvent.click(message);
    expect(onSelect).not.toHaveBeenCalled();
    expect(screen.queryByTestId(/^promo-undo-/)).toBeNull();
    expect(screen.queryByTestId('promo-last-messaged-42')).toBeNull();
  });

  it('offers undo for the local send only, and keeps the imported tick after undo', async () => {
    vi.mocked(getCandidates)
      .mockResolvedValueOnce(
        candidatesResponse([
          candidateRow({
            last_messaged: localSend,
            contact_recorded: true,
            external_contact: SFG_CONTACT,
          }),
        ]),
      )
      .mockResolvedValue(
        candidatesResponse([
          candidateRow({
            contact_recorded: true,
            external_contact: SFG_CONTACT,
          }),
        ]),
      );
    vi.mocked(undoPromoSend).mockResolvedValue({
      sfg_writeback: { state: 'pending', reason: null, delivery_id: 'd-1' },
    });
    render(<Harness onSelect={vi.fn()} initialFilters={SHOW_MESSAGED} />, {
      wrapper: Wrapper,
    });
    expect(
      await screen.findByTestId('promo-last-messaged-42'),
    ).toHaveTextContent('Messaged by Promoter Pat');
    expect(screen.getAllByTestId(/^promo-undo-/)).toHaveLength(1);
    expect(screen.getByTestId('promo-select-42')).toBeDisabled();
    fireEvent.click(screen.getByTestId('promo-undo-77'));
    await waitFor(() => expect(undoPromoSend).toHaveBeenCalledWith(1, 77));
    await waitFor(() =>
      expect(screen.queryByTestId('promo-last-messaged-42')).toBeNull(),
    );
    expect(
      screen.getByRole('checkbox', { name: 'Contact recorded in SFG' }),
    ).toHaveAttribute('aria-checked', 'true');
    expect(screen.queryByTestId(/^promo-undo-/)).toBeNull();
  });

  it('ticks a Discord-only guild member without resolving or enrolling them', async () => {
    vi.mocked(getCandidates).mockResolvedValue(
      candidatesResponse(
        [
          candidateRow({
            user_pk: null,
            discordId: '990777',
            contact_recorded: true,
            external_contact: SFG_CONTACT,
          }),
        ],
        { source: 'discord' },
      ),
    );
    render(
      <Harness
        onSelect={vi.fn()}
        initialFilters={{ ...SHOW_MESSAGED, source: 'discord' }}
      />,
      { wrapper: Wrapper },
    );
    const row = await screen.findByTestId('promo-candidate-discord-990777');
    expect(row).toHaveTextContent('Contact recorded in SFG');
    expect(row).toHaveTextContent('No account yet');
    const message = screen.getByTestId('promo-select-discord-990777');
    expect(message).toBeDisabled();
    fireEvent.click(message);
    expect(resolveDiscordMember).not.toHaveBeenCalled();
  });

  it('does not select a resolved member whose contact is already recorded', async () => {
    vi.mocked(getCandidates).mockResolvedValue(
      candidatesResponse([{ ...newcomer }], { source: 'discord' }),
    );
    vi.mocked(resolveDiscordMember).mockResolvedValue({
      ...newcomer,
      user_pk: 77,
      contact_recorded: true,
      external_contact: SFG_CONTACT,
    });
    const onSelect = vi.fn();
    render(
      <Harness
        onSelect={onSelect}
        initialFilters={{ ...DEFAULT_CANDIDATE_FILTERS, source: 'discord' }}
      />,
      { wrapper: Wrapper },
    );
    fireEvent.click(await screen.findByTestId('promo-select-discord-990777'));
    await waitFor(() => expect(resolveDiscordMember).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('keeps a local-only repeat send messageable with its undo', async () => {
    vi.mocked(getCandidates).mockResolvedValue(
      candidatesResponse([
        candidateRow({ last_messaged: localSend, contact_recorded: true }),
      ]),
    );
    const onSelect = vi.fn();
    render(<Harness onSelect={onSelect} initialFilters={SHOW_MESSAGED} />, {
      wrapper: Wrapper,
    });
    const message = await screen.findByTestId('promo-select-42');
    expect(message).toBeEnabled();
    expect(screen.getByTestId('promo-undo-77')).toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).toBeNull();
    fireEvent.click(message);
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ user_pk: 42 }),
    );
  });

  it('warns that history may be incomplete and shows the last import time when configured', async () => {
    vi.mocked(getCandidates).mockResolvedValue(
      candidatesResponse([candidateRow()], { contact_sync: SYNC_CONFIGURED }),
    );
    render(<Harness onSelect={vi.fn()} />, { wrapper: Wrapper });
    const warning = await screen.findByTestId('promo-contact-sync-warning');
    expect(warning).toHaveTextContent('History may be incomplete');
    expect(warning).toHaveTextContent('Last SFG receipt imported');
    expect(warning).not.toHaveTextContent(/synced/i);
    expect(screen.getByTestId('promo-select-42')).toBeEnabled();
  });

  it('omits the import time when no receipt has been imported yet', async () => {
    vi.mocked(getCandidates).mockResolvedValue(
      candidatesResponse([candidateRow()], {
        contact_sync: { ...SYNC_CONFIGURED, last_receipt_imported_at: null },
      }),
    );
    render(<Harness onSelect={vi.fn()} />, { wrapper: Wrapper });
    const warning = await screen.findByTestId('promo-contact-sync-warning');
    expect(warning).toHaveTextContent('History may be incomplete');
    expect(warning).not.toHaveTextContent('Last SFG receipt imported');
  });

  it('shows no sync status for an org without the integration', async () => {
    vi.mocked(getCandidates).mockResolvedValue(
      candidatesResponse([candidateRow()]),
    );
    render(<Harness onSelect={vi.fn()} />, { wrapper: Wrapper });
    await screen.findByTestId('promo-candidate-42');
    expect(screen.queryByTestId('promo-contact-sync-warning')).toBeNull();
    expect(screen.queryByText(/SFG/)).toBeNull();
  });

  it('keeps the existing error message when candidates fail to load', async () => {
    vi.mocked(getCandidates).mockRejectedValue({
      response: { status: 503, data: { detail: 'Players are unavailable.' } },
    });
    render(<Harness onSelect={vi.fn()} />, { wrapper: Wrapper });
    expect(
      await screen.findByTestId('promo-candidates-error'),
    ).toHaveTextContent('Players are unavailable.');
  });
});
