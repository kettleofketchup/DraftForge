import { describe, it, expect, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { EventSignupModal } from '../EventSignupModal';
import { GameType } from '../schemas';

const event = {
  id: 1,
  name: 'Evt',
  game_type: GameType.DOTA2,
  require_steam_id: true,
  allow_active_mmr: true,
  allow_previous_rank: true,
  allow_battlecup_rating: true,
  discord_require_rank_screenshot: false,
  discord_require_battlecup_screenshot: false,
};

function renderModal(props: Parameters<typeof EventSignupModal>[0]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderToStaticMarkup(
    <QueryClientProvider client={qc}>
      <EventSignupModal {...props} />
    </QueryClientProvider>,
  );
}

describe('EventSignupModal', () => {
  it('uses correct title for rsvp vs tentative', () => {
    const html1 = renderModal({
      event: event as never,
      intent: 'rsvp',
      profile: null,
      open: true,
      onOpenChange: vi.fn(),
    });
    expect(html1).toContain('Sign Up for Evt');
    const html2 = renderModal({
      event: event as never,
      intent: 'tentative',
      profile: null,
      open: true,
      onOpenChange: vi.fn(),
    });
    expect(html2).toContain('Mark Tentative for Evt');
  });
});
