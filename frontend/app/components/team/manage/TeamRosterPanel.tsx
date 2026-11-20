import { TriangleAlert } from 'lucide-react';
import { useRef, type ReactNode } from 'react';

import type {
  ManagedTeam,
  RosterUser,
} from '~/components/api/teamManagementAPI';
import { Alert, AlertDescription } from '~/components/ui/alert';
import {
  BrandSelect,
  BrandSelectContent,
  BrandSelectItem,
  BrandSelectTrigger,
  SelectValue,
} from '~/components/ui/brand-select';
import { DisplayName } from '~/components/user/avatar';
import { LeadershipProblemsBanner } from './LeadershipProblemsBanner';
import type { PendingTeamAction } from './pendingTeamAction';
import { RosterTable } from './RosterTable';
import {
  clearDeputyRequest,
  isMember,
  setCaptainRequest,
  setDeputyRequest,
} from './teamActionCopy';

export type { PendingTeamAction } from './pendingTeamAction';

export interface TeamRosterPanelProps {
  team: ManagedTeam;
  pending: boolean;
  error: string | null;
  onRequestAction: (request: PendingTeamAction) => void;
  addStandinSlot?: ReactNode;
}

const NO_DEPUTY = 'none';
const NO_CAPTAIN = 'none';

const byName = (a: RosterUser, b: RosterUser): number =>
  DisplayName(a).localeCompare(DisplayName(b));

function GhostItem({ user, note }: { user: RosterUser; note: string }) {
  return (
    <BrandSelectItem value={String(user.pk)} disabled>
      <TriangleAlert className="text-destructive" aria-hidden />
      <span className="truncate">{`${DisplayName(user)} (${note})`}</span>
    </BrandSelectItem>
  );
}

export function TeamRosterPanel({
  team,
  pending,
  error,
  onRequestAction,
  addStandinSlot,
}: TeamRosterPanelProps) {
  const captainRef = useRef<HTMLButtonElement>(null);
  const deputyRef = useRef<HTMLButtonElement>(null);
  const { captain, deputy_captain: deputy } = team;
  const members = [...team.members].sort(byName);
  const findMember = (pk: string) => members.find((m) => String(m.pk) === pk);

  const captainGhost = captain && !isMember(team, captain) ? captain : null;
  const deputyOptions = members.filter((m) => m.pk !== captain?.pk);
  const deputyMarker =
    deputy && deputy.pk === captain?.pk
      ? 'also captain'
      : deputy && !isMember(team, deputy)
        ? 'not a member'
        : null;

  return (
    <div className="flex flex-col gap-4">
      {error ? (
        <Alert variant="destructive" data-testid="team-manage-error">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <LeadershipProblemsBanner
        team={team}
        disabled={pending}
        onRequestAction={onRequestAction}
        onChooseCaptain={() => captainRef.current?.focus()}
        onChooseDeputy={() => deputyRef.current?.focus()}
      />

      <div className="flex flex-wrap gap-4">
        <label className="flex flex-col gap-1 text-sm">
          Captain
          <BrandSelect
            value={captain ? String(captain.pk) : NO_CAPTAIN}
            disabled={pending}
            onValueChange={(value) => {
              const user = findMember(value);
              if (user) onRequestAction(setCaptainRequest(team, user));
            }}
          >
            <BrandSelectTrigger
              ref={captainRef}
              data-testid="team-manage-captain-select"
            >
              <SelectValue />
            </BrandSelectTrigger>
            <BrandSelectContent>
              {captain ? null : (
                <BrandSelectItem value={NO_CAPTAIN} disabled>
                  No captain
                </BrandSelectItem>
              )}
              {captainGhost ? (
                <GhostItem user={captainGhost} note="not a member" />
              ) : null}
              {members.map((m) => (
                <BrandSelectItem key={m.pk} value={String(m.pk)}>
                  {DisplayName(m)}
                </BrandSelectItem>
              ))}
            </BrandSelectContent>
          </BrandSelect>
        </label>

        <label className="flex flex-col gap-1 text-sm">
          Deputy
          <BrandSelect
            value={deputy ? String(deputy.pk) : NO_DEPUTY}
            disabled={pending}
            onValueChange={(value) => {
              if (value === NO_DEPUTY) {
                onRequestAction(clearDeputyRequest(team));
                return;
              }
              const user = findMember(value);
              if (user) onRequestAction(setDeputyRequest(team, user));
            }}
          >
            <BrandSelectTrigger
              ref={deputyRef}
              data-testid="team-manage-deputy-select"
            >
              <SelectValue />
            </BrandSelectTrigger>
            <BrandSelectContent>
              <BrandSelectItem value={NO_DEPUTY}>No deputy</BrandSelectItem>
              {deputy && deputyMarker ? (
                <GhostItem user={deputy} note={deputyMarker} />
              ) : null}
              {deputyOptions.map((m) => (
                <BrandSelectItem key={m.pk} value={String(m.pk)}>
                  {DisplayName(m)}
                </BrandSelectItem>
              ))}
            </BrandSelectContent>
          </BrandSelect>
        </label>
      </div>

      <RosterTable
        team={team}
        pending={pending}
        onRequestAction={onRequestAction}
        toolbarActions={addStandinSlot}
      />
    </div>
  );
}
