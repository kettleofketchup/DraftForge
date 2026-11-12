import { beforeEach, describe, expect, it } from 'vitest';
import { useUserStore } from '../userStore';

describe('getCurrentDraftRound', () => {
  beforeEach(() => {
    useUserStore.setState({
      tournament: { draft: { pk: 1, latest_round: 2, draft_rounds: [{ pk: 1 }, { pk: 2 }, { pk: 3 }] } } as never,
      getCurrentTournament: async () => {},
    });
  });

  it('keeps the viewed pk', async () => {
    useUserStore.setState({ curDraftRound: { pk: 3 } as never });
    await useUserStore.getState().getCurrentDraftRound();
    expect(useUserStore.getState().curDraftRound.pk).toBe(3);
  });

  it('falls back to latest_round when the viewed pk is gone', async () => {
    useUserStore.setState({ curDraftRound: { pk: 99 } as never });
    await useUserStore.getState().getCurrentDraftRound();
    expect(useUserStore.getState().curDraftRound.pk).toBe(2);
  });
});
