import { useEffect } from 'react';
import type { UserClassType } from '~/index';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import { UserCard } from '../../user';
import { DoublePickThreshold } from '../shuffle/DoublePickThreshold';
import { DraftTable } from './draftTable';
const log = getLogger('choiceCard');
interface PlayerChoiceViewProps {}
export const PlayerChoiceView: React.FC<PlayerChoiceViewProps> = ({}) => {
  const draft = useUserStore((state) => state.draft);
  const curRound = useUserStore((state) => state.curDraftRound);
  useEffect(() => {
    log.debug('rerender: Current choice updated:', curRound?.choice);
  }, [curRound?.choice]);
  useEffect(() => {
    log.debug(
      'rerender: draft users remaining updated:',
      draft?.users_remaining?.length,
    );
  }, [draft?.users_remaining?.length]);

  if (!curRound || !curRound?.choice)
    return (
      <div>
        <DoublePickThreshold />
        <DraftTable />
      </div>
    );

  return (
    <div className="mb-4">
      <h3 className="text-xl font-bold">Current Choice</h3>
      <div className="flex flex-col items-center justify-center">
        <UserCard user={curRound?.choice as UserClassType} compact={true} />
      </div>
    </div>
  );
};
