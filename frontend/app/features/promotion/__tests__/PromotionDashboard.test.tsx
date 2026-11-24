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
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import type { OrgFeatureAccess } from '~/features/org-features';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import { createI18nInstance } from '~/i18n/config';
import {
  getCandidates,
  getPromoEvents,
  getPromoTemplates,
  renderPromo,
  sendPromo,
  undoPromoSend,
} from '../api';
import { PromotionDashboard } from '../PromotionDashboard';
import type { CandidateRow, PromoEvent } from '../schemas';
import {
  NO_SYNC,
  SFG_CONTACT,
  SYNC_CONFIGURED,
  candidatesResponse,
} from './fixtures';

vi.mock('../api', () => ({
  getCandidates: vi.fn(),
  getPromoEvents: vi.fn(),
  getPromoTemplates: vi.fn(),
  renderPromo: vi.fn(),
  sendPromo: vi.fn(),
  undoPromoSend: vi.fn(),
}));

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => {};
  Element.prototype.scrollIntoView ??= () => {};
});

const access: OrgFeatureAccess = makeOrgFeatureAccess({
  viewerPk: 5,
  canUsePromotion: true,
  canViewContributions: true,
});

function makeEvent(id: number, name: string): PromoEvent {
  return {
    id,
    name,
    scheduled_at: '2026-11-15T01:00:00Z',
    ends_at: null,
    state: 'upcoming',
    signups_open_at: null,
  };
}

const eventA = makeEvent(9, 'Friday Inhouse');
const eventB = makeEvent(10, 'Saturday Cup');

const candidate: CandidateRow = {
  user_pk: 42,
  username: 'ana',
  nickname: null,
  discordUsername: 'ana_dc',
  discordId: '1234',
  avatarUrl: null,
  recent_count: 2,
  last_messaged: null,
  contact_recorded: false,
  external_contact: null,
  earning_send_exists: false,
  signed_up: false,
};

afterEach(() => {
  vi.mocked(getCandidates).mockReset();
  vi.mocked(getPromoEvents).mockReset();
  vi.mocked(getPromoTemplates).mockReset();
  vi.mocked(renderPromo).mockReset();
  vi.mocked(sendPromo).mockReset();
});

describe('PromotionDashboard', () => {
  it('drops the chosen player when the selected event leaves the events list', async () => {
    vi.mocked(getPromoEvents).mockResolvedValue([eventA, eventB]);
    vi.mocked(getPromoTemplates).mockResolvedValue([]);
    vi.mocked(getCandidates).mockResolvedValue({
      source: 'recent',
      n: 3,
      days: 30,
      rows: [candidate],
      contact_sync: NO_SYNC,
    });
    vi.mocked(renderPromo).mockResolvedValue({
      text: 'Hey',
      warnings: [],
      will_earn: true,
    });

    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    function Wrapper({ children }: { children: ReactNode }) {
      return (
        <I18nextProvider i18n={createI18nInstance('en')}>
          <QueryClientProvider client={qc}>
            <MemoryRouter initialEntries={['/?tab=promotion&event=9']}>
              {children}
            </MemoryRouter>
          </QueryClientProvider>
        </I18nextProvider>
      );
    }
    render(<PromotionDashboard orgId={1} access={access} />, {
      wrapper: Wrapper,
    });

    await waitFor(() =>
      expect(screen.getByTestId('promo-event-9')).toHaveAttribute(
        'aria-pressed',
        'true',
      ),
    );
    fireEvent.click(screen.getByTestId('promo-event-10'));
    fireEvent.click(await screen.findByTestId('promo-select-42'));
    expect(await screen.findByTestId('promo-message-text')).toBeInTheDocument();

    vi.mocked(getPromoEvents).mockResolvedValue([eventA]);
    await act(async () => {
      await qc.invalidateQueries();
    });

    await waitFor(() =>
      expect(screen.getByTestId('promo-event-9')).toHaveAttribute(
        'aria-pressed',
        'true',
      ),
    );
    expect(screen.queryByTestId('promo-event-10')).not.toBeInTheDocument();
    expect(screen.queryByTestId('promo-message-text')).not.toBeInTheDocument();
    expect(screen.getByTestId('promo-pick-player')).toBeInTheDocument();
  });
});

describe('PromotionDashboard stale recipients', () => {
  function setup(): QueryClient {
    vi.mocked(getPromoEvents).mockResolvedValue([eventA]);
    vi.mocked(getPromoTemplates).mockResolvedValue([]);
    vi.mocked(renderPromo).mockResolvedValue({
      text: 'Hey',
      warnings: [],
      will_earn: true,
    });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    function Wrapper({ children }: { children: ReactNode }) {
      return (
        <I18nextProvider i18n={createI18nInstance('en')}>
          <QueryClientProvider client={qc}>
            <MemoryRouter initialEntries={['/?tab=promotion&event=9']}>
              {children}
            </MemoryRouter>
          </QueryClientProvider>
        </I18nextProvider>
      );
    }
    render(<PromotionDashboard orgId={1} access={access} />, {
      wrapper: Wrapper,
    });
    return qc;
  }

  it('drops a selected player who disappears from the hidden-messaged list after a refetch', async () => {
    vi.mocked(getCandidates).mockResolvedValue(
      candidatesResponse([candidate], { contact_sync: SYNC_CONFIGURED }),
    );
    const qc = setup();
    fireEvent.click(await screen.findByTestId('promo-select-42'));
    expect(await screen.findByTestId('promo-message-text')).toBeInTheDocument();

    vi.mocked(getCandidates).mockResolvedValue(
      candidatesResponse([], { contact_sync: SYNC_CONFIGURED }),
    );
    await act(async () => {
      await qc.invalidateQueries();
    });

    await waitFor(() =>
      expect(screen.queryByTestId('promo-message-text')).toBeNull(),
    );
    expect(screen.getByTestId('promo-pick-player')).toBeInTheDocument();
  });

  it('drops a selected player whose refreshed row now has an SFG contact', async () => {
    vi.mocked(getCandidates).mockResolvedValue(
      candidatesResponse([candidate], { contact_sync: SYNC_CONFIGURED }),
    );
    const qc = setup();
    fireEvent.click(await screen.findByTestId('promo-hide-messaged'));
    await waitFor(() =>
      expect(vi.mocked(getCandidates).mock.lastCall?.[2]).toMatchObject({
        hideMessaged: false,
      }),
    );
    fireEvent.click(await screen.findByTestId('promo-select-42'));
    expect(await screen.findByTestId('promo-message-text')).toBeInTheDocument();

    vi.mocked(getCandidates).mockResolvedValue(
      candidatesResponse(
        [
          {
            ...candidate,
            contact_recorded: true,
            external_contact: SFG_CONTACT,
          },
        ],
        { contact_sync: SYNC_CONFIGURED },
      ),
    );
    await act(async () => {
      await qc.invalidateQueries();
    });

    await waitFor(() =>
      expect(screen.queryByTestId('promo-message-text')).toBeNull(),
    );
    expect(screen.getByTestId('promo-select-42')).toBeDisabled();
  });

  it('keeps the compose panel and its undo after this promoter marks the send', async () => {
    vi.mocked(getCandidates).mockResolvedValue(
      candidatesResponse([candidate], { contact_sync: SYNC_CONFIGURED }),
    );
    vi.mocked(sendPromo).mockResolvedValue({
      id: 77,
      earns_points: true,
      points_awarded: 1,
      sent_at: '2026-11-14T00:00:00Z',
      sfg_writeback: { state: 'pending', reason: null, delivery_id: 'd-77' },
    });
    setup();
    fireEvent.click(await screen.findByTestId('promo-select-42'));
    fireEvent.change(await screen.findByTestId('promo-message-text'), {
      target: { value: 'Hey' },
    });
    await waitFor(() =>
      expect(screen.getByTestId('promo-mark-sent-btn')).toBeEnabled(),
    );
    vi.mocked(getCandidates).mockResolvedValue(
      candidatesResponse([], { contact_sync: SYNC_CONFIGURED }),
    );
    fireEvent.click(screen.getByTestId('promo-mark-sent-btn'));
    expect(await screen.findByTestId('promo-sent-banner')).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByTestId('promo-candidate-42')).toBeNull(),
    );
    expect(screen.getByTestId('promo-sent-banner')).toBeInTheDocument();
    expect(screen.getByTestId('promo-sfg-writeback')).toHaveAttribute(
      'data-state',
      'pending',
    );

    // Undoing that send keeps the panel open so it can be marked again, even
    // while the list has not caught up yet.
    vi.mocked(undoPromoSend).mockResolvedValue({
      sfg_writeback: { state: 'pending', reason: null, delivery_id: 'd-77' },
    });
    fireEvent.click(screen.getByTestId('promo-undo-77'));
    await waitFor(() =>
      expect(screen.queryByTestId('promo-sent-banner')).toBeNull(),
    );
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
    expect(screen.getByTestId('promo-message-text')).toBeInTheDocument();
    expect(screen.getByTestId('promo-mark-sent-btn')).toBeEnabled();
  });
});
