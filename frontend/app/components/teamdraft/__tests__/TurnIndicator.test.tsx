// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { DisplayName } from '~/components/user/avatar';
import { useDraftWebSocketStore } from '~/store/draftWebSocketStore';
import { useUserStore } from '~/store/userStore';
import { TurnIndicator } from '../roundView/TurnIndicator';
import { tick, user } from './fixtures';

describe('TurnIndicator', () => {
  beforeEach(() => {
    useUserStore.setState({
      currentUser: user(7) as never,
      curDraftRound: { pk: 22, pick_number: 5, captain: user(7), choice: null } as never,
    });
    useDraftWebSocketStore.getState().reset();
  });

  it('untimed draft: my round is my turn even without a tick', () => {
    useDraftWebSocketStore.setState({ draftState: { pk: 1, latest_round: 22, draft_options: { timer_enabled: false } } as never });
    render(<TurnIndicator />);
    expect(screen.getByTestId('turn-indicator')).toHaveTextContent("It's YOUR turn");
  });

  it('timed draft: my skipped (deferred) round is not my turn and says when I pick', () => {
    useUserStore.setState({ curDraftRound: { pk: 22, pick_number: 5, captain: user(7), choice: null, skip_count: 1 } as never });
    useDraftWebSocketStore.setState({
      draftState: { pk: 1, state: 'drafting', latest_round: 23, draft_options: { timer_enabled: true } } as never,
      tick: tick({ active_round_pk: 23, active_captain_id: 8 }),
    });
    render(<TurnIndicator />);
    expect(screen.getByTestId('turn-indicator-deferred')).toHaveTextContent(`Pick #5 — deferred, ${DisplayName(user(7))} picks after #4`);
    expect(screen.queryByText(/YOUR turn/)).toBeNull();
  });

  it('timed draft: my future never-skipped round is plain "Waiting for", not deferred, not my turn', () => {
    useUserStore.setState({ curDraftRound: { pk: 27, pick_number: 7, captain: user(7), choice: null, skip_count: 0 } as never });
    useDraftWebSocketStore.setState({
      draftState: { pk: 1, state: 'drafting', latest_round: 21, draft_options: { timer_enabled: true } } as never,
      tick: tick({ active_round_pk: 21, active_captain_id: 8 }),
    });
    render(<TurnIndicator />);
    expect(screen.getByTestId('turn-indicator')).toHaveTextContent('Waiting for');
    expect(screen.queryByTestId('turn-indicator-deferred')).toBeNull();
    expect(screen.queryByText(/YOUR turn/)).toBeNull();
  });

  it('timed draft: the active round for me is my turn', () => {
    useDraftWebSocketStore.setState({
      draftState: { pk: 1, latest_round: 22, draft_options: { timer_enabled: true } } as never,
      tick: tick({ active_round_pk: 22, active_captain_id: 7 }),
    });
    render(<TurnIndicator />);
    expect(screen.getByTestId('turn-indicator')).toHaveTextContent("It's YOUR turn");
  });
});
