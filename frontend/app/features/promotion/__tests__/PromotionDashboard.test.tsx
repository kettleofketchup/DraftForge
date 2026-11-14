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
import { createI18nInstance } from '~/i18n/config';
import {
  getCandidates,
  getPromoEvents,
  getPromoTemplates,
  renderPromo,
} from '../api';
import { PromotionDashboard } from '../PromotionDashboard';
import type { CandidateRow, PromoEvent } from '../schemas';

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

const access: OrgFeatureAccess = {
  settled: true,
  viewerPk: 5,
  canUsePromotion: true,
  canManageTemplates: false,
  canManagePromoters: false,
  canViewContributions: true,
  canViewContributors: false,
  canManageContributions: false,
};

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
  earning_send_exists: false,
  signed_up: false,
};

afterEach(() => {
  vi.mocked(getCandidates).mockReset();
  vi.mocked(getPromoEvents).mockReset();
  vi.mocked(getPromoTemplates).mockReset();
  vi.mocked(renderPromo).mockReset();
});

describe('PromotionDashboard', () => {
  it('drops the chosen player when the selected event leaves the events list', async () => {
    vi.mocked(getPromoEvents).mockResolvedValue([eventA, eventB]);
    vi.mocked(getPromoTemplates).mockResolvedValue([]);
    vi.mocked(getCandidates).mockResolvedValue({ n: 3, rows: [candidate] });
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
