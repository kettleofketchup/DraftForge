import { useEffect } from 'react';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import type { DraftRoundType } from '../types';
import { DraftRoundCard } from './draftRoundCard';
const log = getLogger('CaptainCards');
interface CaptainCardsProps {}

export const CaptainCards: React.FC<CaptainCardsProps> = ({}) => {
  const draft = useUserStore((state) => state.draft);
  const curDraftRound = useUserStore((state) => state.curDraftRound);
  const draftIndex = useUserStore((state) => state.draftIndex);
  const tournament = useUserStore((state) => state.tournament);
  useEffect(() => {}, [curDraftRound?.pk, draft?.pk]);

  const totalRounds = (tournament?.teams?.length || 0) * 4;

  useEffect(() => {
    log.debug('index changed:');

  }, [draftIndex]);
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center">
        <DraftRoundCard
          draftRound={
            draft?.draft_rounds?.[draftIndex] || ({} as DraftRoundType)
          }
          maxRounds={totalRounds}
          isCur={true}
        />

        {draftIndex < totalRounds - 1 &&
        draft &&
        draft.draft_rounds &&
        draft.draft_rounds[draftIndex + 1] ? (
          <div className="hidden lg:flex lg:w-full lg:pl-8">
            <DraftRoundCard
              draftRound={draft.draft_rounds[draftIndex + 1]}
              maxRounds={totalRounds}
              isCur={false}
            />
          </div>
        ) : (
          <></>
        )}
      </div>
    </div>
  );
};
