// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import type { EventSignupType } from '~/components/events/schemas';
import { GAME_TYPE } from '~/components/game/constants';
import { useGameTypeStore } from '~/store/gameTypeStore';
import { RankSignalsCard } from './RankSignalsCard';

function signup(over: Partial<EventSignupType> = {}): EventSignupType {
  return {
    id: 1,
    org_user_mmr: 2400,
    dota_profile: null,
    suggested_mmr: null,
    suggested_mmr_range: null,
    suggested_mmr_range_source: 'none',
    self_reported_rank: null,
    self_reported_rank_date: null,
    ...over,
  } as EventSignupType;
}

beforeEach(() => {
  useGameTypeStore.setState({ currentGameType: null } as never);
});

describe('RankSignalsCard gameType prop', () => {
  it('Dota prop renders the Dota card even with no ambient game', () => {
    render(<RankSignalsCard signup={signup()} gameType={GAME_TYPE.DOTA2} />);
    expect(screen.getByTestId('rank-signals-self-report')).toBeTruthy();
    expect(screen.getByTestId('rank-signals-prior-mmr').textContent).toContain(
      'Prior Dota 2 org MMR',
    );
  });

  it('Deadlock prop renders the Deadlock card with the self-reported rank', () => {
    render(
      <RankSignalsCard
        signup={signup({
          self_reported_rank: 'Archon 3',
          self_reported_rank_date: '2026-10-01',
        })}
        gameType={GAME_TYPE.DEADLOCK}
      />,
    );
    expect(screen.queryByTestId('rank-signals-self-report')).toBeNull();
    const rank = screen.getByTestId('rank-signals-deadlock-rank');
    expect(rank.textContent).toContain('Archon 3');
    expect(rank.textContent).toContain('2026-10-01');
    const prior = screen.getByTestId('rank-signals-prior-mmr').textContent;
    expect(prior).toContain('Prior Deadlock org MMR');
    expect(prior).toContain('2,400');
  });

  it('Deadlock card shows a dash when no rank is reported', () => {
    render(<RankSignalsCard signup={signup()} gameType={GAME_TYPE.DEADLOCK} />);
    expect(
      screen.getByTestId('rank-signals-deadlock-rank').textContent,
    ).toContain('—');
  });

  it('ambient Dota game does not override a Deadlock prop', () => {
    useGameTypeStore.setState({ currentGameType: GAME_TYPE.DOTA2 } as never);
    render(<RankSignalsCard signup={signup()} gameType={GAME_TYPE.DEADLOCK} />);
    expect(screen.getByTestId('rank-signals-deadlock-rank')).toBeTruthy();
  });
});
