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
import { UserAvatar } from '~/components/user/UserAvatar';
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
  /** Toolbar pickers beside the roster table (add stand-in, replace captain). */
  addStandinSlot?: ReactNode;
  onReplaceCaptain?: () => void;
}

const NO_DEPUTY = 'none';
const NO_CAPTAIN = 'none';

const byName = (a: RosterUser, b: RosterUser): number =>
  DisplayName(a).localeCompare(DisplayName(b));

/** Avatar and truncating name on one row; the select trigger shows it too. */
function LeaderOption({
  user,
  label = DisplayName(user),
  icon,
}: {
  user: RosterUser;
  label?: string;
  icon?: ReactNode;
}) {
  return (
    <span className="flex min-w-0 items-center gap-2">
      {icon}
      <span aria-hidden className="flex shrink-0">
        <UserAvatar
          user={user}
          size="tiny"
          data-testid="leader-option-avatar"
        />
      </span>
      <span className="truncate" data-testid="leader-option-name">
        {label}
      </span>
    </span>
  );
}

function MemberItem({ user }: { user: RosterUser }) {
  return (
    <BrandSelectItem value={String(user.pk)} textValue={DisplayName(user)}>
      <LeaderOption user={user} />
    </BrandSelectItem>
  );
}

function GhostItem({ user, note }: { user: RosterUser; note: string }) {
  const label = `${DisplayName(user)} (${note})`;
  return (
    <BrandSelectItem value={String(user.pk)} textValue={label} disabled>
      <LeaderOption
        user={user}
        label={label}
        icon={<TriangleAlert className="text-destructive" aria-hidden />}
      />
    </BrandSelectItem>
  );
}

export function TeamRosterPanel({
  team,
  pending,
  error,
  onRequestAction,
  addStandinSlot,
  onReplaceCaptain,
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
              className="max-w-full sm:max-w-80"
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
                <MemberItem key={m.pk} user={m} />
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
              className="max-w-full sm:max-w-80"
            >
              <SelectValue />
            </BrandSelectTrigger>
            <BrandSelectContent>
              <BrandSelectItem value={NO_DEPUTY}>No deputy</BrandSelectItem>
              {deputy && deputyMarker ? (
                <GhostItem user={deputy} note={deputyMarker} />
              ) : null}
              {deputyOptions.map((m) => (
                <MemberItem key={m.pk} user={m} />
              ))}
            </BrandSelectContent>
          </BrandSelect>
        </label>
      </div>

      <RosterTable
        team={team}
        pending={pending}
        onRequestAction={onRequestAction}
        onReplaceCaptain={onReplaceCaptain}
        toolbarActions={addStandinSlot}
      />
    </div>
  );
}
