import type { Control, FieldValues } from 'react-hook-form';
import {
  DRAFT_TYPE_DESCRIPTION,
  DraftSettingsSection,
} from '~/components/teamdraft/DraftSettingsSection';
import { DraftTypeField } from '~/components/teamdraft/DraftTypeField';
import type { DraftSettingsFormInput } from '~/components/teamdraft/schemas';
import { BracketTypeField } from '../fields/BracketTypeField';
import { GameAndTeamsRow } from '../fields/GameAndTeamsRow';
import type { GameTypeFields } from '../fields/GameTypeField';
import { LeagueField } from '../fields/LeagueField';
import type { TeamSizeFieldValues } from '../fields/TeamSizeFields';
import { TournamentNameField } from '../fields/TournamentNameField';
import type { EventFieldTestIds } from '../testIds';

type TournamentFields = GameTypeFields &
  TeamSizeFieldValues & {
    tournament_name: string;
    tournament_league?: number | null;
    tournament_type: string;
    draft_type: string;
  };

interface Props<T extends FieldValues & TournamentFields> {
  control: Control<T>;
  testIds: EventFieldTestIds;
  /** Omit for forms without a league. */
  league?: { organizationId: number | undefined };
  tournamentName?: {
    label?: string;
    placeholder?: string;
    description?: string;
  };
  /** Overrides the draft type select's testid. */
  draftTypeTestId?: string;
  /** Only false for forms whose schema lacks the draft timer fields. */
  draftSettings?: boolean;
  resetLobbyLeague?: boolean;
}

/** The Tournament tab: name, league, game, team sizes, bracket and draft. */
export function EventTournamentFields<
  T extends FieldValues & TournamentFields,
>({
  control,
  testIds,
  league,
  tournamentName,
  draftTypeTestId,
  draftSettings = true,
  resetLobbyLeague = true,
}: Props<T>) {
  const name = (
    <TournamentNameField
      control={control}
      testId={testIds.tournamentName}
      {...tournamentName}
    />
  );
  return (
    <>
      {league ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {name}
          <LeagueField
            control={control}
            organizationId={league.organizationId}
            testIds={testIds.league}
          />
        </div>
      ) : (
        name
      )}
      <GameAndTeamsRow
        control={control}
        testIds={testIds}
        resetLobbyLeague={resetLobbyLeague}
      />
      <BracketTypeField control={control} triggerTestId={testIds.bracket} />
      {draftSettings ? (
        <DraftSettingsSection
          control={
            control as unknown as Control<
              DraftSettingsFormInput & { draft_type: string }
            >
          }
          draftTypeTestId={draftTypeTestId}
        />
      ) : (
        <DraftTypeField
          control={control}
          label="Draft type"
          description={DRAFT_TYPE_DESCRIPTION}
          testId={draftTypeTestId}
        />
      )}
    </>
  );
}
