// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { I18nextProvider } from 'react-i18next';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import type { OrgFeatureAccess } from '~/features/org-features';
import { createI18nInstance } from '~/i18n/config';
import { renderPromo, sendPromo } from '../api';
import { ComposePanel } from '../ComposePanel';
import type { CandidateRow, PromoEvent, PromoTemplate } from '../schemas';

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

const event: PromoEvent = {
  id: 9,
  name: 'Friday Inhouse',
  scheduled_at: '2026-11-15T01:00:00Z',
  ends_at: null,
  state: 'upcoming',
  signups_open_at: null,
};

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

function renderPanel(panelAccess: OrgFeatureAccess = access): void {
  render(
    <ComposePanel
      orgId={1}
      access={panelAccess}
      event={event}
      candidate={candidate}
      templates={templates}
    />,
    { wrapper: Wrapper },
  );
}

async function loadedText(): Promise<HTMLTextAreaElement> {
  const box = (await screen.findByTestId(
    'promo-message-text',
  )) as HTMLTextAreaElement;
  await waitFor(() => expect(box.value).toBe(RENDERED));
  return box;
}

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
    vi.mocked(sendPromo).mockResolvedValue({
      id: 77,
      earns_points: true,
      points_awarded: 1,
      sent_at: '2026-11-14T00:00:00Z',
    });
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
