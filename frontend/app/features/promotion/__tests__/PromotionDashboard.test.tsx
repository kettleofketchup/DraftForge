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
import { setViewportWidth } from '~/components/ui/data-table/__tests__/viewport';
import type { OrgFeatureAccess } from '~/features/org-features';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import { createI18nInstance } from '~/i18n/config';
import {
  getCandidates,
  getPromoEvents,
  getPromoTemplates,
  renderPromo,
  resolveDiscordMember,
  sendPromo,
  undoPromoSend,
} from '../api';
import { PromotionDashboard } from '../PromotionDashboard';
import type {
  CandidateFilters,
  CandidateRow,
  CandidatesResponse,
  PromoEvent,
} from '../schemas';
import {
  EXTERNAL_CONTACT,
  NO_SYNC,
  SYNC_CONFIGURED,
  candidatesResponse,
} from './fixtures';

vi.mock('../api', () => ({
  getCandidates: vi.fn(),
  getPromoEvents: vi.fn(),
  getPromoTemplates: vi.fn(),
  renderPromo: vi.fn(),
  resolveDiscordMember: vi.fn(),
  sendPromo: vi.fn(),
  undoPromoSend: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => {};
  Element.prototype.scrollIntoView ??= () => {};
  globalThis.ResizeObserver ??= class {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  };
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
    game_type: 1,
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
  mmr: 4100,
  recent_count: 2,
  last_messaged: null,
  contact_recorded: false,
  external_contact: null,
  earning_send_exists: false,
  signed_up: false,
};

const newcomer: CandidateRow = {
  ...candidate,
  user_pk: null,
  username: 'newbie',
  discordUsername: 'newbie',
  discordId: '990777',
  mmr: null,
  recent_count: null,
  discord_joined_at: '2026-11-22T10:00:00Z',
};

function candidatesFor(filters: CandidateFilters): CandidatesResponse {
  return {
    source: filters.source,
    n: filters.n,
    days: filters.days,
    game_type: 1,
    min_mmr: null,
    max_mmr: null,
    rows: [candidate, newcomer],
    contact_sync: NO_SYNC,
  };
}

let restoreViewport: () => void;
beforeEach(() => {
  restoreViewport = setViewportWidth(1280);
  vi.mocked(getPromoEvents).mockResolvedValue([eventA, eventB]);
  vi.mocked(getPromoTemplates).mockResolvedValue([
    { id: 3, name: 'First invite', body: 'Hey {player}', updated_at: '' },
  ]);
  vi.mocked(getCandidates).mockImplementation(async (_o, _e, f) =>
    candidatesFor(f),
  );
  vi.mocked(renderPromo).mockResolvedValue({
    text: 'Hey ana',
    warnings: [],
    will_earn: true,
  });
});

afterEach(() => {
  restoreViewport();
  vi.clearAllMocks();
});

function renderDashboard(): QueryClient {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
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

async function ready(): Promise<void> {
  await waitFor(() =>
    expect(screen.getByTestId('promo-event-9')).toHaveAttribute(
      'aria-pressed',
      'true',
    ),
  );
  await screen.findByTestId('promo-candidate-row-42');
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (err: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('PromotionDashboard', () => {
  it('Message opens the branded dialog with identity, template and MMR', async () => {
    renderDashboard();
    await ready();
    expect(screen.queryByTestId('promo-message-dialog')).toBeNull();
    fireEvent.click(screen.getByTestId('promo-candidate-message-42'));

    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveAccessibleName('Message ana');
    expect(screen.getByTestId('promo-dialog-description')).toHaveTextContent(
      'Friday Inhouse · Dota 2 MMR 4,100',
    );
    expect(screen.getByTestId('promo-message-note')).toBeInTheDocument();
    expect(screen.getByTestId('promo-template-select')).toBeInTheDocument();
    expect(screen.getByTestId('promo-discord-profile-link')).toHaveAttribute(
      'href',
      'https://discord.com/users/1234',
    );
    await waitFor(() =>
      expect(screen.getByTestId('promo-message-text')).toHaveValue('Hey ana'),
    );
    expect(dialog.querySelectorAll('form form')).toHaveLength(0);
    expect(screen.getByTestId('promo-mark-sent-btn')).toHaveTextContent(
      'Mark sent',
    );

    fireEvent.click(screen.getByTestId('promo-dialog-close'));
    await waitFor(() =>
      expect(screen.queryByTestId('promo-message-dialog')).toBeNull(),
    );
  });

  it('Mark as sent opens an explicit record flow that only saves on confirm', async () => {
    vi.mocked(sendPromo).mockResolvedValue({
      id: 77,
      earns_points: true,
      points_awarded: 1,
      sent_at: '2026-11-24T10:00:00Z',
      writeback: { state: null, reason: null, delivery_id: null },
    });
    renderDashboard();
    await ready();
    fireEvent.click(screen.getByTestId('promo-candidate-record-42'));
    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveAccessibleName('Record a message to ana');
    expect(screen.getByTestId('promo-record-note')).toHaveTextContent(
      'Nothing is sent from DraftForge',
    );
    await waitFor(() =>
      expect(screen.getByTestId('promo-message-text')).toHaveValue('Hey ana'),
    );
    expect(sendPromo).not.toHaveBeenCalled();
    const confirm = screen.getByTestId('promo-mark-sent-btn');
    expect(confirm).toHaveTextContent('Record as sent');
    fireEvent.click(confirm);
    await waitFor(() =>
      expect(sendPromo).toHaveBeenCalledWith(1, 9, {
        template_id: 3,
        recipient_id: 42,
        text: 'Hey ana',
      }),
    );
    expect(await screen.findByTestId('promo-sent-banner')).toHaveTextContent(
      'You earned 1 point.',
    );
    expect(screen.getByTestId('promo-undo-77')).toBeInTheDocument();
  });

  it('shows the record error and keeps the dialog open', async () => {
    vi.mocked(sendPromo).mockRejectedValue(
      Object.assign(new Error('bad'), {
        isAxiosError: true,
        response: { status: 400, data: { text: ['Message is empty'] } },
      }),
    );
    renderDashboard();
    await ready();
    fireEvent.click(screen.getByTestId('promo-candidate-record-42'));
    await waitFor(() =>
      expect(screen.getByTestId('promo-message-text')).toHaveValue('Hey ana'),
    );
    fireEvent.click(screen.getByTestId('promo-mark-sent-btn'));
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(screen.getByTestId('promo-message-dialog')).toBeInTheDocument();
    expect(screen.queryByTestId('promo-sent-banner')).toBeNull();
  });

  it('resolves a Discord member only on click, disabling the row meanwhile', async () => {
    const pending = deferred<CandidateRow>();
    vi.mocked(resolveDiscordMember).mockReturnValue(pending.promise);
    renderDashboard();
    await ready();
    expect(resolveDiscordMember).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByTestId('promo-candidate-message-discord-990777'),
    );
    await waitFor(() =>
      expect(
        screen.getByTestId('promo-candidate-message-discord-990777'),
      ).toBeDisabled(),
    );
    expect(resolveDiscordMember).toHaveBeenCalledWith(1, 9, '990777');
    expect(screen.queryByTestId('promo-message-dialog')).toBeNull();

    await act(async () => {
      pending.resolve({ ...newcomer, user_pk: 77 });
    });
    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveAccessibleName('Message newbie');
    expect(screen.getByTestId('promo-dialog-description')).toHaveTextContent(
      'MMR Unknown',
    );
  });

  it('drops a late resolution after the audience changes', async () => {
    const pending = deferred<CandidateRow>();
    vi.mocked(resolveDiscordMember).mockReturnValue(pending.promise);
    renderDashboard();
    await ready();
    fireEvent.click(
      screen.getByTestId('promo-candidate-message-discord-990777'),
    );
    fireEvent.click(screen.getByTestId('promo-source-active'));
    await waitFor(() =>
      expect(getCandidates).toHaveBeenLastCalledWith(
        1,
        9,
        expect.objectContaining({ source: 'active' }),
      ),
    );
    await act(async () => {
      pending.resolve({ ...newcomer, user_pk: 77 });
    });
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByTestId('promo-message-dialog')).toBeNull();
    expect(
      screen.getByTestId('promo-candidate-message-discord-990777'),
    ).toBeEnabled();
  });

  it('drops a late resolution after switching events', async () => {
    const pending = deferred<CandidateRow>();
    vi.mocked(resolveDiscordMember).mockReturnValue(pending.promise);
    renderDashboard();
    await ready();
    fireEvent.click(
      screen.getByTestId('promo-candidate-record-discord-990777'),
    );
    fireEvent.click(screen.getByTestId('promo-event-10'));
    await act(async () => {
      pending.resolve({ ...newcomer, user_pk: 77 });
    });
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByTestId('promo-message-dialog')).toBeNull();
  });

  it('reports a failed resolution and re-enables the row', async () => {
    vi.mocked(resolveDiscordMember).mockRejectedValue(
      Object.assign(new Error('gone'), {
        isAxiosError: true,
        response: {
          status: 400,
          data: { discord_id: ['this player cannot be promoted to'] },
        },
      }),
    );
    renderDashboard();
    await ready();
    fireEvent.click(
      screen.getByTestId('promo-candidate-message-discord-990777'),
    );
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(screen.queryByTestId('promo-message-dialog')).toBeNull();
    expect(
      screen.getByTestId('promo-candidate-message-discord-990777'),
    ).toBeEnabled();
  });

  it('Escape closes the dialog and the row can reopen it', async () => {
    renderDashboard();
    await ready();
    fireEvent.click(screen.getByTestId('promo-candidate-message-42'));
    await screen.findByRole('dialog');
    await act(async () => {
      fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    });
    await waitFor(() =>
      expect(screen.queryByTestId('promo-message-dialog')).toBeNull(),
    );
    fireEvent.click(screen.getByTestId('promo-candidate-message-42'));
    await screen.findByRole('dialog');
  });

  it('drops the open recipient when the selected event leaves the events list', async () => {
    const qc = renderDashboard();
    await ready();
    fireEvent.click(screen.getByTestId('promo-event-10'));
    fireEvent.click(await screen.findByTestId('promo-candidate-message-42'));
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
    await waitFor(() =>
      expect(screen.queryByTestId('promo-message-text')).toBeNull(),
    );
    expect(screen.getByTestId('promo-pick-player')).toBeInTheDocument();
  });
});

describe('PromotionDashboard recorded contacts', () => {
  const contacted: CandidateRow = {
    ...candidate,
    contact_recorded: true,
    external_contact: EXTERNAL_CONTACT,
  };

  it('does not open a resolved member whose contact is already recorded', async () => {
    vi.mocked(resolveDiscordMember).mockResolvedValue({
      ...newcomer,
      user_pk: 77,
      contact_recorded: true,
      external_contact: EXTERNAL_CONTACT,
    });
    renderDashboard();
    await ready();
    fireEvent.click(
      screen.getByTestId('promo-candidate-message-discord-990777'),
    );
    await waitFor(() =>
      expect(toast.info).toHaveBeenCalledWith(
        'A contact with this player is already recorded externally',
      ),
    );
    expect(screen.queryByTestId('promo-message-dialog')).toBeNull();
  });

  it('drops an open recipient who disappears from the hidden-messaged list after a refetch', async () => {
    vi.mocked(getCandidates).mockResolvedValue(
      candidatesResponse([candidate], { contact_sync: SYNC_CONFIGURED }),
    );
    const qc = renderDashboard();
    await ready();
    fireEvent.click(screen.getByTestId('promo-candidate-message-42'));
    expect(await screen.findByTestId('promo-message-text')).toBeInTheDocument();

    vi.mocked(getCandidates).mockResolvedValue(
      candidatesResponse([], { contact_sync: SYNC_CONFIGURED }),
    );
    await act(async () => {
      await qc.invalidateQueries();
    });

    await waitFor(() =>
      expect(screen.queryByTestId('promo-message-dialog')).toBeNull(),
    );
    expect(screen.getByTestId('promo-pick-player')).toBeInTheDocument();
  });

  it('drops an open recipient whose refreshed row now has an external contact', async () => {
    vi.mocked(getCandidates).mockResolvedValue(
      candidatesResponse([candidate], { contact_sync: SYNC_CONFIGURED }),
    );
    const qc = renderDashboard();
    await ready();
    fireEvent.click(screen.getByTestId('promo-hide-messaged'));
    await waitFor(() =>
      expect(vi.mocked(getCandidates).mock.lastCall?.[2]).toMatchObject({
        hideMessaged: false,
      }),
    );
    // Let the refetch settle so the click lands on the current row.
    await waitFor(() =>
      expect(screen.getByTestId('promo-candidate-count')).toHaveTextContent(
        /^1 player$/,
      ),
    );
    fireEvent.click(screen.getByTestId('promo-candidate-message-42'));
    expect(await screen.findByTestId('promo-message-text')).toBeInTheDocument();

    vi.mocked(getCandidates).mockResolvedValue(
      candidatesResponse([contacted], { contact_sync: SYNC_CONFIGURED }),
    );
    await act(async () => {
      await qc.invalidateQueries();
    });

    await waitFor(() =>
      expect(screen.queryByTestId('promo-message-dialog')).toBeNull(),
    );
    await waitFor(() =>
      expect(screen.getByTestId('promo-candidate-message-42')).toBeDisabled(),
    );
  });

  it('still drops a stale recipient after a failed send', async () => {
    vi.mocked(getCandidates).mockResolvedValue(
      candidatesResponse([candidate], { contact_sync: SYNC_CONFIGURED }),
    );
    vi.mocked(sendPromo).mockRejectedValue({
      response: { status: 500, data: { detail: 'boom' } },
    });
    const qc = renderDashboard();
    await ready();
    fireEvent.click(screen.getByTestId('promo-candidate-message-42'));
    await waitFor(() =>
      expect(screen.getByTestId('promo-message-text')).toHaveValue('Hey ana'),
    );
    fireEvent.click(screen.getByTestId('promo-mark-sent-btn'));
    await waitFor(() => expect(sendPromo).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.getByTestId('promo-mark-sent-btn')).toBeEnabled(),
    );
    expect(screen.queryByTestId('promo-sent-banner')).toBeNull();

    // The failed send recorded nothing, so a later disappearance from the
    // hidden-messaged list means someone else contacted this player.
    vi.mocked(getCandidates).mockResolvedValue(
      candidatesResponse([], { contact_sync: SYNC_CONFIGURED }),
    );
    await act(async () => {
      await qc.invalidateQueries();
    });
    await waitFor(() =>
      expect(screen.queryByTestId('promo-message-dialog')).toBeNull(),
    );
  });

  it('keeps the dialog open when the backend says the contact is already recorded, then closes it', async () => {
    vi.mocked(sendPromo).mockRejectedValue({
      response: {
        status: 409,
        data: {
          code: 'contact_already_recorded',
          detail: 'a contact with this player is already recorded externally',
        },
      },
    });
    renderDashboard();
    await ready();
    fireEvent.click(screen.getByTestId('promo-candidate-message-42'));
    await waitFor(() =>
      expect(screen.getByTestId('promo-message-text')).toHaveValue('Hey ana'),
    );
    fireEvent.click(screen.getByTestId('promo-mark-sent-btn'));
    await waitFor(() =>
      expect(toast.info).toHaveBeenCalledWith(
        'A contact with ana is already recorded externally',
      ),
    );
    await waitFor(() =>
      expect(screen.queryByTestId('promo-message-dialog')).toBeNull(),
    );
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('keeps an open recipient that only a changed search filter leaves out', async () => {
    vi.mocked(getCandidates).mockResolvedValue(
      candidatesResponse([candidate], { contact_sync: SYNC_CONFIGURED }),
    );
    renderDashboard();
    await ready();
    fireEvent.click(screen.getByTestId('promo-candidate-message-42'));
    expect(await screen.findByTestId('promo-message-text')).toBeInTheDocument();

    vi.mocked(getCandidates).mockResolvedValue(
      candidatesResponse([], { contact_sync: SYNC_CONFIGURED }),
    );
    fireEvent.change(screen.getByTestId('promo-candidate-search'), {
      target: { value: 'zz' },
    });
    await waitFor(() =>
      expect(vi.mocked(getCandidates).mock.lastCall?.[2]).toMatchObject({
        q: 'zz',
      }),
    );
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
    expect(screen.getByTestId('promo-message-text')).toBeInTheDocument();
  });

  it('keeps the dialog and its undo after this promoter marks the send, and shows the writeback state', async () => {
    vi.mocked(getCandidates).mockResolvedValue(
      candidatesResponse([candidate], { contact_sync: SYNC_CONFIGURED }),
    );
    vi.mocked(sendPromo).mockResolvedValue({
      id: 77,
      earns_points: true,
      points_awarded: 1,
      sent_at: '2026-11-14T00:00:00Z',
      writeback: { state: 'pending', reason: null, delivery_id: 'd-77' },
    });
    renderDashboard();
    await ready();
    fireEvent.click(screen.getByTestId('promo-candidate-message-42'));
    await waitFor(() =>
      expect(screen.getByTestId('promo-message-text')).toHaveValue('Hey ana'),
    );
    vi.mocked(getCandidates).mockResolvedValue(
      candidatesResponse([], { contact_sync: SYNC_CONFIGURED }),
    );
    fireEvent.click(screen.getByTestId('promo-mark-sent-btn'));
    expect(await screen.findByTestId('promo-sent-banner')).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByTestId('promo-candidate-row-42')).toBeNull(),
    );
    expect(screen.getByTestId('promo-sent-banner')).toBeInTheDocument();
    expect(screen.getByTestId('promo-external-writeback')).toHaveAttribute(
      'data-state',
      'pending',
    );

    // Undoing that send keeps the dialog open so it can be marked again, even
    // while the list has not caught up yet.
    vi.mocked(undoPromoSend).mockResolvedValue({
      writeback: { state: 'pending', reason: null, delivery_id: 'd-77' },
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
