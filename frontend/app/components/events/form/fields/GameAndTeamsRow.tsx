import type { Control, FieldValues } from 'react-hook-form';
import type { EventFieldTestIds } from '../testIds';
import { GameTypeField, type GameTypeFields } from './GameTypeField';
import { TeamSizeFields, type TeamSizeFieldValues } from './TeamSizeFields';

type RowFields = GameTypeFields & TeamSizeFieldValues;

interface Props<T extends FieldValues & RowFields> {
  control: Control<T>;
  testIds: Pick<
    EventFieldTestIds,
    'game' | 'peoplePerTeam' | 'maxTeams' | 'unlimited'
  >;
  resetLobbyLeague?: boolean;
}

export function GameAndTeamsRow<T extends FieldValues & RowFields>({
  control,
  testIds,
  resetLobbyLeague,
}: Props<T>) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      <GameTypeField
        control={control}
        testId={testIds.game}
        resetLobbyLeague={resetLobbyLeague}
      />
      <TeamSizeFields control={control} testIds={testIds} />
    </div>
  );
}
