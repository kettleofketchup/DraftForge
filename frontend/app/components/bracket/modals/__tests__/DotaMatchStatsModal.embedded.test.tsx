// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ACTIVITY_RESOURCE_MAPPINGS, openExternal } from '~/lib/discord';
import type { MatchDetail } from '~/lib/dota/schemas';
import { DotaMatchStatsModal } from '../DotaMatchStatsModal';

vi.mock('~/lib/discord', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/lib/discord')>()),
  openExternal: vi.fn(async () => true),
}));

const player = (slot: number, hero: number) => ({
  steam_id: slot + 1,
  username: `p${slot}`,
  player_slot: slot,
  hero_id: hero,
  kills: 1,
  deaths: 2,
  assists: 3,
  gold_per_min: 400,
  xp_per_min: 500,
  last_hits: 100,
  denies: 5,
  hero_damage: 10000,
  tower_damage: 1000,
  hero_healing: 0,
});

const matchDetail: MatchDetail = {
  match_id: 8123,
  radiant_win: true,
  duration: 1800,
  start_time: 1_700_000_000,
  game_mode: 2,
  lobby_type: 1,
  players: [player(0, 1), player(128, 2)],
};

vi.mock('~/hooks/useMatchStats', () => ({
  useMatchStats: () => ({ data: matchDetail, isLoading: false, error: null }),
}));

const allowedHosts = new Set(ACTIVITY_RESOURCE_MAPPINGS.map((m) => m.target));

function imageHosts(): string[] {
  return Array.from(document.querySelectorAll('img'))
    .map((img) => img.getAttribute('src') ?? '')
    .filter((src) => /^https?:\/\//.test(src))
    .map((src) => new URL(src).host);
}

describe('DotaMatchStatsModal embedded in the Activity', () => {
  beforeEach(() => {
    vi.mocked(openExternal).mockClear();
  });

  it('loads no image from a host outside the Activity URL mappings', () => {
    render(
      <DotaMatchStatsModal open onClose={() => {}} matchId={8123} embedded />,
    );

    expect(screen.getByText('Match 8123')).toBeInTheDocument();
    expect(screen.queryByAltText('Dotabuff')).not.toBeInTheDocument();
    expect(screen.queryByAltText('OpenDota')).not.toBeInTheDocument();
    expect(imageHosts().filter((h) => !allowedHosts.has(h))).toEqual([]);
  });

  it('opens Dotabuff and OpenDota through the Discord SDK', () => {
    render(
      <DotaMatchStatsModal open onClose={() => {}} matchId={8123} embedded />,
    );

    fireEvent.click(screen.getByRole('link', { name: /Dotabuff/ }));
    expect(openExternal).toHaveBeenCalledWith(
      'https://www.dotabuff.com/matches/8123',
    );

    fireEvent.click(screen.getByRole('link', { name: /OpenDota/ }));
    expect(openExternal).toHaveBeenLastCalledWith(
      'https://www.opendota.com/matches/8123',
    );
  });

  it('keeps the logos and plain links on the website', () => {
    render(<DotaMatchStatsModal open onClose={() => {}} matchId={8123} />);

    expect(screen.getByAltText('Dotabuff')).toBeInTheDocument();
    expect(screen.getByAltText('OpenDota')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Dotabuff/ })).toHaveAttribute(
      'target',
      '_blank',
    );
  });
});
