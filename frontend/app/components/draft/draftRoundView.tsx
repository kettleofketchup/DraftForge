// Holds the general draft view
import { useEffect } from 'react';
import type { DraftRoundType, DraftType, TournamentType } from '~/index';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import { CaptainCards } from './roundView/captainCards';
import { PlayerChoiceView } from './roundView/choiceCard';
import { CurrentTeamView } from './roundView/currentTeam';
import { TurnIndicator } from './roundView/TurnIndicator';
import { ShufflePickOrder } from './shuffle/ShufflePickOrder';
const log = getLogger('DraftRoundView');

export const DraftRoundView: React.FC = () => {
  const curDraftRound: DraftRoundType = useUserStore(
    (state) => state.curDraftRound,
  );
  const draftIndex: number = useUserStore((state) => state.draftIndex);
  const tournament: TournamentType = useUserStore((state) => state.tournament);
  const draft: DraftType = useUserStore((state) => state.draft);

  useEffect(() => {
    log.debug('Current draft round changed:', curDraftRound);
  }, [draftIndex]);

  useEffect(() => {
    log.debug('Tournament teams updated:', tournament.teams);
  }, [tournament.teams?.length]);

  useEffect(() => {
    log.debug('rerender: Tournament users_remaining.length updated');
  }, [draft?.users_remaining?.length]);

  useEffect(() => {
    log.debug('rerender: Draft updated from pk:', draft);
  }, [draft?.pk]);

  useEffect(() => {
    log.debug(
      'rerender: Draft updated from curDraftRound.pk:',
      curDraftRound?.pk,
    );
  }, [curDraftRound?.pk]);
  const latestRound = () =>
    draft?.draft_rounds?.find(
      (round: DraftRoundType) => round.pk === draft?.latest_round,
    );
  const noDraftView = () => {
    return (
      <>
        <h1> No Draft Information Available</h1>
        <p> Start the draft with the init draft button below</p>
      </>
    );
  };

  if (!draft || !draft.draft_rounds) return <>{noDraftView()}</>;

  if (
    draft?.latest_round &&
    draft?.latest_round !== curDraftRound?.pk &&
    !curDraftRound?.choice
  ) {
    log.debug('Not latest round', draft);
    return (
      <>
        {draft.draft_style === 'shuffle' ? <ShufflePickOrder /> : <CaptainCards />}

        <div className="mb-4">
          <h3 className="text-xl font-bold">Not Current Round</h3>
          <h4>
            Current Pick Number: {curDraftRound?.pick_number} vs{' '}
            {latestRound()?.pick_number}
          </h4>
          <p className="text-gray-500">This is not the current draft round.</p>
        </div>
      </>
    );
  }

  return (
    <>
      {draft.draft_style === 'shuffle' ? <ShufflePickOrder /> : <CaptainCards />}
      <div className="p-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-2xl font-bold">Draft View</h2>
        </div>
        <TurnIndicator />
        <CurrentTeamView />
        <PlayerChoiceView />
      </div>
    </>
  );
};

export default DraftRoundView;
