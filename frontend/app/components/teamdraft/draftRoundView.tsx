// Redesigned draft view with pick order + current team at top
// Full screen with alternating columns on md+ (2 cols) and xl+ (3 cols)
import { memo, useEffect } from 'react';
import { Card } from '~/components/ui/card';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import { DoublePickThreshold } from './shuffle/DoublePickThreshold';
import { PickOrderSection, CurrentTeamSection, AvailablePlayersSection } from './sections';
import type { DraftRoundType } from './types';

const log = getLogger('DraftRoundView');

// Granular selectors for minimal re-renders
const selectDraftRounds = (state: ReturnType<typeof useUserStore.getState>) => state.draft?.draft_rounds;
const selectDraftStyle = (state: ReturnType<typeof useUserStore.getState>) => state.draft?.draft_style;
const selectLatestRoundPk = (state: ReturnType<typeof useUserStore.getState>) => state.draft?.latest_round;
const selectCurDraftRoundPk = (state: ReturnType<typeof useUserStore.getState>) => state.curDraftRound?.pk;
const selectCurDraftRoundChoice = (state: ReturnType<typeof useUserStore.getState>) => state.curDraftRound?.choice;
const selectCurDraftRoundPickNumber = (state: ReturnType<typeof useUserStore.getState>) => state.curDraftRound?.pick_number;
const selectDraftIndex = (state: ReturnType<typeof useUserStore.getState>) => state.draftIndex;

export const DraftRoundView: React.FC = memo(() => {
  // Use granular selectors - component only re-renders when these specific values change
  const draftRounds = useUserStore(selectDraftRounds);
  const draftStyle = useUserStore(selectDraftStyle);
  const latestRoundPk = useUserStore(selectLatestRoundPk);
  const curDraftRoundPk = useUserStore(selectCurDraftRoundPk);
  const curDraftRoundChoice = useUserStore(selectCurDraftRoundChoice);
  const curDraftRoundPickNumber = useUserStore(selectCurDraftRoundPickNumber);
  const draftIndex = useUserStore(selectDraftIndex);

  useEffect(() => {
    log.debug('Draft view updated - index:', draftIndex);
  }, [draftIndex]);

  const latestRound = draftRounds?.find(
    (round: DraftRoundType) => round.pk === latestRoundPk
  );

  const isShuffle = draftStyle === 'shuffle';

  // Early return: no draft data
  if (!draftRounds || draftRounds.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-xl font-bold">No Draft Information Available</h1>
          <p className="text-muted-foreground">Start the draft with the init draft button below</p>
        </div>
      </div>
    );
  }

  // Early return: viewing a past round (not the latest)
  const isNotLatestRound =
    latestRoundPk &&
    latestRoundPk !== curDraftRoundPk &&
    !curDraftRoundChoice;

  if (isNotLatestRound) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <h3 className="text-xl font-bold">Not Current Round</h3>
          <p className="text-muted-foreground">
            Pick {curDraftRoundPickNumber} of {latestRound?.pick_number}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full gap-2 p-2 md:gap-4 md:p-4">
      {/* Top Section: Pick Order + Current Team - unified card */}
      <Card className="p-2 md:p-4 shrink-0">
        <div className="flex flex-col lg:flex-row gap-3 md:gap-4">
          {/* Pick Order - Left side */}
          <PickOrderSection />

          {/* Divider */}
          <div className="hidden lg:block w-px bg-border" />

          {/* Current Team + Position Coverage - Right side */}
          <CurrentTeamSection />
        </div>
      </Card>

      {/* Double Pick Threshold for shuffle - more compact */}
      {isShuffle && (
        <div className="shrink-0">
          <DoublePickThreshold />
        </div>
      )}

      {/* Bottom Section: Available Players */}
      <AvailablePlayersSection />
    </div>
  );
});

DraftRoundView.displayName = 'DraftRoundView';

export default DraftRoundView;
