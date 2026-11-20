import { TriangleAlert } from 'lucide-react';
import { useRef, type ReactNode } from 'react';

import type {
  ManagedTeam,
  RosterUser,
} from '~/components/api/teamManagementAPI';
import { Alert, AlertDescription } from '~/components/ui/alert';
import { Badge } from '~/components/ui/badge';
import {
  BrandSelect,
  BrandSelectContent,
  BrandSelectItem,
  BrandSelectTrigger,
  SelectValue,
} from '~/components/ui/brand-select';
import { DestructiveButton, SecondaryButton } from '~/components/ui/buttons';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { DisplayName } from '~/components/user/avatar';
import { UserAvatar } from '~/components/user/UserAvatar';
import { LeadershipProblemsBanner } from './LeadershipProblemsBanner';
import type { PendingTeamAction } from './pendingTeamAction';
import { RosterStatusBadge } from './RosterStatusBadge';
import {
  clearDeputyRequest,
  isMember,
  markDropoutRequest,
  removeStandinRequest,
  restoreMemberRequest,
  setCaptainRequest,
  setDeputyRequest,
  subInRequest,
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

function RosterRow({
  user,
  testId,
  badges,
  children,
}: {
  user: RosterUser;
  testId: string;
  badges?: ReactNode;
  children: ReactNode;
}) {
  return (
    <li
      data-testid={testId}
      className="flex flex-wrap items-center justify-between gap-2 py-1"
    >
      <span className="flex min-w-0 items-center gap-2">
        <UserAvatar user={user} size="sm" />
        <span className="truncate">{DisplayName(user)}</span>
        {badges}
      </span>
      <span className="flex flex-wrap gap-2">{children}</span>
    </li>
  );
}

function Section({
  title,
  action,
  children,
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-1">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        {action}
      </div>
      {children}
    </section>
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
  const lastMember = team.members.length === 1;

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

      <Section title={`Members (${members.length})`}>
        <ul>
          {members.map((m) => {
            const isCaptain = m.pk === captain?.pk;
            const dropout = (
              <DestructiveButton
                size="sm"
                disabled={pending || lastMember}
                onClick={() => onRequestAction(markDropoutRequest(team, m))}
              >
                Mark dropout
              </DestructiveButton>
            );
            return (
              <RosterRow
                key={m.pk}
                user={m}
                testId={`team-member-row-${m.pk}`}
                badges={
                  <>
                    {isCaptain ? (
                      <Badge variant="outline">Captain</Badge>
                    ) : null}
                    {m.pk === deputy?.pk ? (
                      <RosterStatusBadge status="deputy" />
                    ) : null}
                  </>
                }
              >
                {isCaptain ? null : (
                  <SecondaryButton
                    size="sm"
                    disabled={pending}
                    onClick={() => onRequestAction(setCaptainRequest(team, m))}
                  >
                    Make captain
                  </SecondaryButton>
                )}
                {lastMember ? (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      {/* A disabled button gets no pointer events; the span carries the tooltip. */}
                      <span tabIndex={0}>{dropout}</span>
                    </TooltipTrigger>
                    <TooltipContent>
                      A team needs at least one member
                    </TooltipContent>
                  </Tooltip>
                ) : (
                  dropout
                )}
              </RosterRow>
            );
          })}
        </ul>
      </Section>

      <Section
        title={`Stand-ins (${team.dropin_members.length})`}
        action={addStandinSlot}
      >
        <ul>
          {team.dropin_members.map((s) => (
            <RosterRow
              key={s.pk}
              user={s}
              testId={`team-standin-row-${s.pk}`}
              badges={<RosterStatusBadge status="standin" />}
            >
              <SecondaryButton
                size="sm"
                disabled={pending}
                onClick={() => onRequestAction(subInRequest(team, s))}
              >
                Sub in
              </SecondaryButton>
              <DestructiveButton
                size="sm"
                disabled={pending}
                onClick={() => onRequestAction(removeStandinRequest(team, s))}
              >
                Remove
              </DestructiveButton>
            </RosterRow>
          ))}
        </ul>
      </Section>

      <Section title={`Dropouts (${team.left_members.length})`}>
        <ul>
          {team.left_members.map((d) => (
            <RosterRow
              key={d.pk}
              user={d}
              testId={`team-dropout-row-${d.pk}`}
              badges={<RosterStatusBadge status="dropout" />}
            >
              <SecondaryButton
                size="sm"
                disabled={pending}
                onClick={() => onRequestAction(restoreMemberRequest(team, d))}
              >
                Restore
              </SecondaryButton>
            </RosterRow>
          ))}
        </ul>
      </Section>
    </div>
  );
}
