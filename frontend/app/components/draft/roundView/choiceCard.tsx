import { useEffect } from 'react';
import type { UserClassType } from '~/index';
import { getLogger } from '~/lib/logger';
import { UserCard } from '../../user';
import type { DraftRoundType } from '../types';
import { DraftTable } from './draftTable';
const log = getLogger('choiceCard');
interface PlayerChoiceViewProps {
  curRound: DraftRoundType;
}
export const PlayerChoiceView: React.FC<PlayerChoiceViewProps> = ({
  curRound,
}) => {
  useEffect(() => {
    log.debug('Current choice updated:', curRound?.choice);
  }, [curRound?.choice]);

  if (!curRound || !curRound?.choice) return <DraftTable curRound={curRound} />;

  return (
    <div className="mb-4">
      <h3 className="text-xl font-bold">Current Choice</h3>
      <div className="flex flex-col items-center justify-center">
        <UserCard user={curRound?.choice as UserClassType} compact={true} />
      </div>
    </div>
  );
};
