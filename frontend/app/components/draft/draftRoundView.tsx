// Holds the general draft view
import React, { useEffect, useMemo } from 'react';
import { Separator } from '~/components/ui/separator';

import type { DraftRoundType } from '~/index';
import { getLogger } from '~/lib/logger';
import { useTeamDraftStore } from '~/store/teamDraftStore';
import { useTournamentDataStore } from '~/store/tournamentDataStore';
import { CaptainCards } from './roundView/captainCards';
import { PlayerChoiceView } from './roundView/choiceCard';
import { CurrentTeamView } from './roundView/currentTeam';
import { TurnIndicator } from './roundView/TurnIndicator';
import { ShufflePickOrder } from './shuffle/ShufflePickOrder';

const log = getLogger('DraftRoundView');

export const DraftRoundView: React.FC = () => {
  // Subscribe to specific draft fields (not entire draft object)
  const draftRounds = useTeamDraftStore((state) => state.draft?.draft_rounds);
  const draftStyle = useTeamDraftStore((state) => state.draft?.draft_style);
  const latestRoundPk = useTeamDraftStore((state) => state.draft?.latest_round);
  const draftPk = useTeamDraftStore((state) => state.draft?.pk);
  const usersRemainingLength = useTeamDraftStore((state) => state.draft?.users_remaining?.length);
  const currentRoundIndex = useTeamDraftStore((state) => state.currentRoundIndex);

  // Derive current round from subscribed state (reactive)
  const curDraftRound = useMemo(() => {
    if (!draftRounds || draftRounds.length === 0) return null;
    return draftRounds[currentRoundIndex] ?? null;
  }, [draftRounds, currentRoundIndex]);

  // Tournament data for teams
  const teams = useTournamentDataStore((state) => state.teams);

  useEffect(() => {
    log.debug('Current draft round changed:', curDraftRound);
  }, [currentRoundIndex]);

  useEffect(() => {
    log.debug('Tournament teams updated:', teams);
  }, [teams?.length]);

  useEffect(() => {
    log.debug('rerender: Tournament users_remaining.length updated');
  }, [usersRemainingLength]);

  useEffect(() => {
    log.debug('rerender: Draft updated from pk:', draftPk);
  }, [draftPk]);

  useEffect(() => {
    log.debug(
      'rerender: Draft updated from curDraftRound.pk:',
      curDraftRound?.pk,
    );
  }, [curDraftRound?.pk]);

  const latestRound = () =>
    draftRounds?.find(
      (round: DraftRoundType) => round.pk === latestRoundPk,
    );

  const noDraftView = () => {
    return (
      <>
        <h1> No Draft Information Available</h1>
        <p> Start the draft with the init draft button below</p>
      </>
    );
  };

  if (!draftRounds) return <>{noDraftView()}</>;

  const isNotLatestRound =
    latestRoundPk &&
    latestRoundPk !== curDraftRound?.pk &&
    !curDraftRound?.choice;

  if (isNotLatestRound) {
    log.debug('Not latest round');
    return (
      <>
        {draftStyle === 'shuffle' ? (
          <ShufflePickOrder />
        ) : (
          <CaptainCards />
        )}

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
      {draftStyle === 'shuffle' ? (
        <ShufflePickOrder />
      ) : (
        <CaptainCards />
      )}
      <div className="p-4">
        <TurnIndicator />
        <div className="flex items-center text-center justify-between my-4">
          <h2 className="text-2xl font-bold">My Current Team</h2>
        </div>
        <CurrentTeamView />

        <Separator className="my-4" />

        <div className="flex items-center justify-between mb-4">
          <h2 className="text-2xl font-bold text-center">Pick A player</h2>
        </div>
        <PlayerChoiceView />
      </div>
    </>
  );
};

export default DraftRoundView;
