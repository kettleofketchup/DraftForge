// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import type { ReactNode } from 'react';
import { I18nextProvider } from 'react-i18next';
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest';
import type { UserType } from '~/components/user/types';
import type { OrgFeatureAccess } from '~/features/org-features';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import { createI18nInstance } from '~/i18n/config';
import { useUserStore } from '~/store/userStore';
import { renderPromo, sendPromo } from '../api';
import { ComposePanel } from '../ComposePanel';
import type {
  ExternalWriteback,
  LinkedCandidate,
  PromoEvent,
  PromoSendResult,
  PromoTemplate,
} from '../schemas';
import { EXTERNAL_CONTACT } from './fixtures';

vi.mock('../api', () => ({
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

const event: PromoEvent = {
  id: 9,
  name: 'Friday Inhouse',
  scheduled_at: '2026-11-15T01:00:00Z',
  ends_at: null,
  state: 'upcoming',
  signups_open_at: null,
  game_type: 1,
};

const candidate: LinkedCandidate = {
  user_pk: 42,
  username: 'ana',
  nickname: null,
  discordUsername: 'ana_dc',
  discordId: '1234',
  avatarUrl: null,
  mmr: 3200,
  recent_count: 2,
  last_messaged: null,
  contact_recorded: false,
  external_contact: null,
  earning_send_exists: false,
  signed_up: false,
};

const templates: PromoTemplate[] = [
  {
    id: 3,
    name: 'First invite',
    body: 'Hey {player}',
    updated_at: '2026-11-01T00:00:00Z',
  },
];

const RENDERED =
  'Hey Ana, Friday Inhouse is <t:1794704400:F> (<t:1794704400:R>)';

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <I18nextProvider i18n={createI18nInstance('en')}>
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    </I18nextProvider>
  );
}

interface PanelOptions {
  syncConfigured?: boolean;
  onStale?: () => void;
  target?: LinkedCandidate;
}

function renderPanel(
  panelAccess: OrgFeatureAccess = access,
  { syncConfigured, onStale, target = candidate }: PanelOptions = {},
): void {
  render(
    <ComposePanel
      orgId={1}
      access={panelAccess}
      event={event}
      candidate={target}
      templates={templates}
      syncConfigured={syncConfigured}
      onStale={onStale}
    />,
    { wrapper: Wrapper },
  );
}

function sendResult(state: ExternalWriteback['state']): PromoSendResult {
  return {
    id: 77,
    earns_points: true,
    points_awarded: 1,
    sent_at: '2026-11-14T00:00:00Z',
    writeback: { state, reason: null, delivery_id: 'd-77' },
  };
}

async function loadedText(): Promise<HTMLTextAreaElement> {
  const box = (await screen.findByTestId(
    'promo-message-text',
  )) as HTMLTextAreaElement;
  await waitFor(() => expect(box.value).toBe(RENDERED));
  return box;
}

const sender = {
  pk: 5,
  username: 'organizer',
  nickname: 'Org Lead',
  avatarUrl: null,
} as UserType;

beforeEach(() => {
  useUserStore.setState({ currentUser: sender });
});

afterEach(() => {
  vi.mocked(renderPromo).mockReset();
  vi.mocked(sendPromo).mockReset();
});

describe('ComposePanel', () => {
  it('fills the raw text from the server render and previews it without raw codes', async () => {
    vi.mocked(renderPromo).mockResolvedValue({
      text: RENDERED,
      warnings: [],
      will_earn: true,
    });
    renderPanel();
    await loadedText();
    expect(renderPromo).toHaveBeenCalledWith(1, 9, {
      template_id: 3,
      recipient_id: 42,
    });
    const preview = screen.getByTestId('promo-discord-preview');
    expect(preview.textContent).toContain('Hey Ana, Friday Inhouse is');
    expect(preview.textContent).not.toContain('<t:');
    expect(preview.querySelectorAll('time')).toHaveLength(2);
  });

  it('previews as the organizer sending from their own account', async () => {
    vi.mocked(renderPromo).mockResolvedValue({
      text: RENDERED,
      warnings: [],
      will_earn: true,
    });
    renderPanel();
    await loadedText();
    const preview = screen.getByTestId('promo-discord-preview');
    const header = within(preview).getByTestId('discord-message-author');
    expect(header).toHaveTextContent('Org Lead');
    expect(header).not.toHaveTextContent('APP');
    expect(
      within(preview).getByTestId('promo-sender-avatar'),
    ).toBeInTheDocument();
  });

  it('turns the character counter into a warning over 2000', async () => {
    vi.mocked(renderPromo).mockResolvedValue({
      text: RENDERED,
      warnings: [],
      will_earn: true,
    });
    renderPanel();
    const box = await loadedText();
    const counter = screen.getByTestId('promo-char-count');
    expect(counter).not.toHaveClass('text-warning');
    fireEvent.change(box, { target: { value: 'x'.repeat(2001) } });
    await waitFor(() => expect(counter).toHaveClass('text-warning'));
    expect(counter).toHaveTextContent('2001');
    expect(screen.getByTestId('promo-mark-sent-btn')).toBeEnabled();
  });

  it('disables Mark sent when the text is empty', async () => {
    vi.mocked(renderPromo).mockResolvedValue({
      text: RENDERED,
      warnings: [],
      will_earn: true,
    });
    renderPanel();
    const box = await loadedText();
    expect(screen.getByTestId('promo-mark-sent-btn')).toBeEnabled();
    fireEvent.change(box, { target: { value: '' } });
    await waitFor(() =>
      expect(screen.getByTestId('promo-mark-sent-btn')).toBeDisabled(),
    );
    fireEvent.change(box, { target: { value: '   ' } });
    await waitFor(() =>
      expect(screen.getByTestId('promo-mark-sent-btn')).toBeDisabled(),
    );
  });

  it('disables Mark sent after a successful send so the undo stays reachable', async () => {
    vi.mocked(renderPromo).mockResolvedValue({
      text: RENDERED,
      warnings: [],
      will_earn: true,
    });
    vi.mocked(sendPromo).mockResolvedValue(sendResult('pending'));
    renderPanel();
    await loadedText();
    fireEvent.click(screen.getByTestId('promo-mark-sent-btn'));
    expect(await screen.findByTestId('promo-undo-77')).toBeInTheDocument();
    expect(screen.getByTestId('promo-mark-sent-btn')).toBeDisabled();
    expect(sendPromo).toHaveBeenCalledTimes(1);
  });

  it("says the message won't earn points when the server says so", async () => {
    vi.mocked(renderPromo).mockResolvedValue({
      text: RENDERED,
      warnings: [],
      will_earn: false,
    });
    renderPanel();
    await loadedText();
    expect(screen.getByTestId('promo-no-points-note')).toBeInTheDocument();
  });

  it('hides the no-points note when Contributions is locked', async () => {
    vi.mocked(renderPromo).mockResolvedValue({
      text: RENDERED,
      warnings: [],
      will_earn: false,
    });
    renderPanel({ ...access, canViewContributions: false });
    await loadedText();
    expect(
      screen.queryByTestId('promo-no-points-note'),
    ).not.toBeInTheDocument();
  });

  it('shows only the earned outcome after a send, not the refreshed no-points note', async () => {
    // The send invalidates the render, which now says a repeat would not earn.
    vi.mocked(renderPromo)
      .mockResolvedValueOnce({ text: RENDERED, warnings: [], will_earn: true })
      .mockResolvedValue({ text: RENDERED, warnings: [], will_earn: false });
    vi.mocked(sendPromo).mockResolvedValue(sendResult('pending'));
    renderPanel();
    await loadedText();
    fireEvent.click(screen.getByTestId('promo-mark-sent-btn'));
    expect(await screen.findByTestId('promo-earned-hint')).toHaveTextContent(
      'You earned 1 point.',
    );
    await waitFor(() =>
      expect(vi.mocked(renderPromo).mock.calls.length).toBeGreaterThan(1),
    );
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
    expect(screen.queryByTestId('promo-no-points-note')).toBeNull();
    expect(screen.queryByTestId('promo-earn-points-note')).toBeNull();
  });

  it('pluralizes points earned above one', async () => {
    vi.mocked(renderPromo).mockResolvedValue({
      text: RENDERED,
      warnings: [],
      will_earn: true,
    });
    vi.mocked(sendPromo).mockResolvedValue({
      ...sendResult('pending'),
      points_awarded: 3,
    });
    renderPanel();
    await loadedText();
    fireEvent.click(screen.getByTestId('promo-mark-sent-btn'));
    expect(await screen.findByTestId('promo-earned-hint')).toHaveTextContent(
      'You earned 3 points.',
    );
  });

  it('links to the recipient Discord profile', async () => {
    vi.mocked(renderPromo).mockResolvedValue({
      text: RENDERED,
      warnings: [],
      will_earn: true,
    });
    renderPanel();
    await loadedText();
    expect(screen.getByTestId('promo-discord-profile-link')).toHaveAttribute(
      'href',
      'https://discord.com/users/1234',
    );
  });
});

describe('ComposePanel external writeback feedback', () => {
  async function sendWith(
    state: ExternalWriteback['state'],
    syncConfigured: boolean,
  ): Promise<void> {
    vi.mocked(renderPromo).mockResolvedValue({
      text: RENDERED,
      warnings: [],
      will_earn: true,
    });
    vi.mocked(sendPromo).mockResolvedValue(sendResult(state));
    renderPanel(access, { syncConfigured });
    await loadedText();
    fireEvent.click(screen.getByTestId('promo-mark-sent-btn'));
    await screen.findByTestId('promo-sent-banner');
  }

  it.each([
    ['pending', /Waiting to be recorded externally/],
    ['paused', /External recording is paused/],
    [
      'reconciliation_required',
      /needs review before it can be recorded externally/,
    ],
    ['retry', /will try recording it externally again/],
  ] as const)(
    'reports a %s writeback separately from the recorded send, never as synced',
    async (state, text) => {
      await sendWith(state, true);
      expect(screen.getByTestId('promo-sent-banner')).toHaveTextContent(
        'Sent to',
      );
      const note = screen.getByTestId('promo-external-writeback');
      expect(note).toHaveAttribute('data-state', state);
      expect(note).toHaveTextContent(text);
      expect(note).not.toHaveTextContent(/synced/i);
      expect(note).not.toHaveTextContent(/^Recorded externally/);
    },
  );

  it('reports a positive external receipt as recorded externally', async () => {
    await sendWith('applied', true);
    expect(screen.getByTestId('promo-external-writeback')).toHaveTextContent(
      'Recorded externally',
    );
  });

  it('shows no writeback line for an org without the integration', async () => {
    await sendWith('pending', false);
    expect(screen.queryByTestId('promo-external-writeback')).toBeNull();
  });

  it('disables Mark sent for a recipient whose contact is already recorded externally', async () => {
    vi.mocked(renderPromo).mockResolvedValue({
      text: RENDERED,
      warnings: [],
      will_earn: true,
    });
    renderPanel(access, {
      target: {
        ...candidate,
        contact_recorded: true,
        external_contact: EXTERNAL_CONTACT,
      },
    });
    await loadedText();
    expect(screen.getByTestId('promo-mark-sent-btn')).toBeDisabled();
    expect(screen.getByTestId('promo-copy-btn')).toBeEnabled();
  });

  it('drops the recipient when the server says the contact was already recorded', async () => {
    vi.mocked(renderPromo).mockResolvedValue({
      text: RENDERED,
      warnings: [],
      will_earn: true,
    });
    vi.mocked(sendPromo).mockRejectedValue({
      response: {
        status: 409,
        data: {
          code: 'contact_already_recorded',
          detail: 'a contact with this player is already recorded externally',
        },
      },
    });
    const onStale = vi.fn();
    renderPanel(access, { syncConfigured: true, onStale });
    await loadedText();
    fireEvent.click(screen.getByTestId('promo-mark-sent-btn'));
    await waitFor(() => expect(onStale).toHaveBeenCalledTimes(1));
    expect(screen.queryByTestId('promo-sent-banner')).toBeNull();
  });
});
