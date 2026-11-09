// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DisplayName } from '~/components/user/avatar';
import { useUserStore } from '~/store/userStore';
import { CaptainCards } from '../roundView/captainCards';
import { user } from './fixtures';

const rounds = [
  { pk: 12, pick_number: 1, captain: user(8) },
  { pk: 11, pick_number: 2, captain: user(7) },
  { pk: 13, pick_number: 3, captain: user(9) },
];

describe('CaptainCards', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'IntersectionObserver',
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
    useUserStore.setState({
      draftIndex: 0,
      tournament: {
        teams: [7, 8, 9].map((c) => ({ pk: c, name: `Team ${c}`, captain: user(c) })),
        draft: { pk: 1, draft_rounds: rounds },
      } as never,
      draft: { pk: 1, draft_rounds: rounds } as never,
      curDraftRound: { pk: 11 } as never,
    });
  });

  afterEach(() => vi.unstubAllGlobals());

  it('next-round card follows curDraftRound.pk, not the stale draftIndex', () => {
    render(<CaptainCards />);
    expect(screen.getByText(new RegExp(`Next Captain:\\s*${DisplayName(user(9))}`))).toBeInTheDocument();
  });

  it('renders no cards when curDraftRound.pk is not in the rounds', () => {
    useUserStore.setState({ curDraftRound: { pk: 99 } as never });
    render(<CaptainCards />);
    expect(screen.queryByText(new RegExp(DisplayName(user(9))))).toBeNull();
  });
});
