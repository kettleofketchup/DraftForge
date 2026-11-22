// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { EventSignupType } from '~/components/events/schemas';
import { GAME_TYPE } from '~/components/game/constants';
import { resetGameType, withGameType } from '~/test-utils/gameType';
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

afterEach(resetGameType);

describe('RankSignalsCard reads the page game', () => {
  it('renders the Dota card outside any game context', () => {
    render(<RankSignalsCard signup={signup()} />);
    expect(screen.getByTestId('rank-signals-self-report')).toBeTruthy();
    expect(screen.getByTestId('rank-signals-prior-mmr').textContent).toContain(
      'Prior Dota 2 org MMR',
    );
  });

  it('renders the Deadlock card with the self-reported rank on a Deadlock page', () => {
    withGameType(GAME_TYPE.DEADLOCK);
    render(
      <RankSignalsCard
        signup={signup({
          self_reported_rank: 'Archon 3',
          self_reported_rank_date: '2026-10-01',
        })}
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
    withGameType(GAME_TYPE.DEADLOCK);
    render(<RankSignalsCard signup={signup()} />);
    expect(
      screen.getByTestId('rank-signals-deadlock-rank').textContent,
    ).toContain('—');
  });
});
