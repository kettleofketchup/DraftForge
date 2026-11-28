import { useQuery, useQueryClient } from '@tanstack/react-query';
import { isAxiosError } from 'axios';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import { z } from 'zod';

import { fetchOrganization } from '~/components/api/api';
import type { OverrideAcknowledgement } from '~/components/api/overridesAPI';
import {
  isTeamManagementError,
  RosterUserSchema,
  type ManagedTeam,
  type RosterUser,
  type TeamAction,
  type TeamActionKind,
} from '~/components/api/teamManagementAPI';
import { OverrideWarningDialog } from '~/components/events/OverrideWarningDialog';
import { useOverrideRetry } from '~/components/events/useOverrideRetry';
import { organizationQueryKey } from '~/components/organization/hooks/useOrganization';
import {
  DIALOG_SCREEN_CSS,
  DIALOG_SCREEN_SCROLL_CSS,
} from '~/components/reusable/modal';
import { TeamStatusBadge } from '~/components/team/TeamStatusBadge';
import { Alert, AlertDescription } from '~/components/ui/alert';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { ScrollArea } from '~/components/ui/scroll-area';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { getLogger } from '~/lib/logger';
import { cn } from '~/lib/utils';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useUserStore } from '~/store/userStore';
import { AddStandinPicker } from './AddStandinPicker';
import { teamCandidateRows } from './candidateStatus';
import type { PendingTeamAction } from './pendingTeamAction';
import { resolveLogUser } from './resolveLogUser';
import { addStandinRequest, replaceCaptainRequest } from './teamActionCopy';
import {
  TeamActionReasonDialog,
  type TeamActionReasonValues,
} from './TeamActionReasonDialog';
import { TeamHistoryTable } from './TeamHistoryTable';
import { TeamPlacementControl } from './TeamPlacementControl';
import { TeamRosterPanel } from './TeamRosterPanel';
import { UserCandidatePicker } from './UserCandidatePicker';
import {
  teamManageKeys,
  useManagedTeam,
  useTeamActionMutation,
  useTeamHistory,
} from './useTeamManagement';

const log = getLogger('teamManage');

const OVERRIDE_REASON_LABEL = 'Reason (recorded in team history)';
const NO_PERMISSION = 'You no longer have permission to manage this team';
const TEAM_GONE = 'This team no longer exists';
const GENERIC_FAILURE = 'Something went wrong. Try again.';

const ReasonErrorSchema = z.object({ reason: z.array(z.string()).min(1) });

export interface TeamManageDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  teamId: number;
  tournamentPk: number | undefined;
  organizationPk: number | null | undefined;
  leaguePk: number | null | undefined;
  onTeamGone: () => void;
}

type PendingSubmit = { action: TeamAction; reason: string };

const statusOf = (err: unknown): number | undefined =>
  isAxiosError(err) ? err.response?.status : undefined;

function withReplacing(
  action: TeamAction,
  team: ManagedTeam,
  replacingId: number | null | undefined,
): TeamAction {
  if (action.kind !== 'sub_in') return action;
  const replacing =
    replacingId == null
      ? null
      : (team.members.find((m) => m.pk === replacingId) ?? null);
  return { ...action, replacing };
}

function withOutgoingDropout(
  action: TeamAction,
  markOutgoingDropout: boolean | undefined,
): TeamAction {
  if (action.kind !== 'replace_captain' || markOutgoingDropout === undefined) {
    return action;
  }
  return { ...action, markOutgoingDropout };
}

/**
 * Radix wraps viewport content in a `display: table` div, which defeats
 * `table-fixed`; the inner `p-1` keeps focus rings inside the viewport clip.
 */
const TAB_SCROLL_CSS = cn(
  DIALOG_SCREEN_SCROLL_CSS,
  '[&_[data-slot=scroll-area-viewport]>div]:!block',
);

const rosterPks = (team: ManagedTeam): number[] =>
  [...team.members, ...team.dropin_members, ...team.left_members].map(
    (u) => u.pk,
  );

export function TeamManageDialog({
  open,
  onOpenChange,
  teamId,
  tournamentPk,
  organizationPk,
  leaguePk,
  onTeamGone,
}: TeamManageDialogProps) {
  const queryClient = useQueryClient();
  const managed = useManagedTeam(teamId, { enabled: open });
  const { data: organization } = useQuery({
    queryKey: organizationQueryKey(organizationPk ?? -1),
    queryFn: () => fetchOrganization(organizationPk!),
    enabled: open && organizationPk != null,
  });

  const [tab, setTab] = useState('roster');
  const [historyPage, setHistoryPage] = useState(1);
  const history = useTeamHistory(teamId, historyPage, {
    enabled: open && tab === 'history',
  });
  const tournamentUsers = useUserStore((s) =>
    s.tournament?.pk === tournamentPk ? s.tournament?.users : undefined,
  );
  const candidateUsers = useMemo(
    () =>
      (tournamentUsers ?? []).flatMap((u): RosterUser[] => {
        const parsed = RosterUserSchema.safeParse(u);
        return parsed.success ? [parsed.data] : [];
      }),
    [tournamentUsers],
  );
  const [request, setRequest] = useState<PendingTeamAction | null>(null);
  const [reasonOpen, setReasonOpen] = useState(false);
  const [captainPickerOpen, setCaptainPickerOpen] = useState(false);
  const openCaptainPicker = useCallback(() => setCaptainPickerOpen(true), []);
  const [actionReason, setActionReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const lastReasons = useRef<Partial<Record<TeamActionKind, string>>>({});
  const pendingRef = useRef<PendingSubmit | null>(null);

  const { mutateAsync } = useTeamActionMutation(teamId, tournamentPk);

  useEffect(() => {
    if (open) log.debug('Team manage opened', { teamId });
  }, [open, teamId]);

  const handleTeamGone = useCallback(
    (kind?: TeamActionKind) => {
      log.warn('Team action refused', { teamId, kind, code: 'not_found' });
      setReasonOpen(false);
      onOpenChange(false);
      onTeamGone();
      if (tournamentPk != null) {
        queryClient.invalidateQueries({
          queryKey: ['tournament', tournamentPk],
        });
      }
      toast.error(TEAM_GONE);
    },
    [teamId, tournamentPk, onOpenChange, onTeamGone, queryClient],
  );

  const managedStatus = statusOf(managed.error);
  const historyStatus = statusOf(history.error);
  const goneHandled = useRef(false);
  useEffect(() => {
    if (!open) {
      goneHandled.current = false;
      setTab('roster');
      setHistoryPage(1);
      return;
    }
    if (
      (managedStatus === 404 || historyStatus === 404) &&
      !goneHandled.current
    ) {
      goneHandled.current = true;
      handleTeamGone();
    }
  }, [open, managedStatus, historyStatus, handleTeamGone]);

  useEffect(() => setHistoryPage(1), [teamId]);

  const runAction = useCallback(
    (ack: OverrideAcknowledgement) => {
      const pending = pendingRef.current;
      if (!pending) return Promise.reject(new Error('No team action pending'));
      return mutateAsync({
        action: pending.action,
        body: {
          reason: ack.acknowledged_codes.length
            ? (ack.reason ?? pending.reason)
            : pending.reason,
          acknowledged_codes: ack.acknowledged_codes,
        },
      });
    },
    [mutateAsync],
  );

  const onSuccess = useCallback(() => {
    const kind = pendingRef.current?.action.kind;
    if (kind) delete lastReasons.current[kind];
    pendingRef.current = null;
    setError(null);
  }, []);

  const onError = useCallback(
    (err: unknown) => {
      const kind = pendingRef.current?.action.kind;
      const status = statusOf(err);
      if (isTeamManagementError(err)) {
        const { code, detail } = err.response!.data;
        setError(detail);
        toast.error(detail);
        log.warn('Team action refused', { teamId, kind, code });
        return;
      }
      const reasonError =
        status === 400 && isAxiosError(err)
          ? ReasonErrorSchema.safeParse(err.response?.data)
          : null;
      if (reasonError?.success) {
        const message = reasonError.data.reason[0];
        setError(message);
        toast.error(message);
        log.warn('Team action refused', { teamId, kind, code: 'reason' });
        return;
      }
      if (status === 403) {
        toast.error(NO_PERMISSION);
        log.warn('Team action refused', {
          teamId,
          kind,
          code: 'not_permitted',
        });
        queryClient.invalidateQueries({
          queryKey: teamManageKeys.managed(teamId),
        });
        return;
      }
      if (status === 404) {
        handleTeamGone(kind);
        return;
      }
      toast.error(GENERIC_FAILURE);
      log.error('Team action failed', { teamId, kind, status });
    },
    [teamId, queryClient, handleTeamGone],
  );

  const { run, pending, dialogProps } = useOverrideRetry(runAction, {
    onSuccess,
    onError,
  });

  const requestAction = useCallback((next: PendingTeamAction) => {
    setRequest(next);
    setReasonOpen(true);
  }, []);

  const team = managed.data;
  const placementTournamentPk = team?.tournament?.pk ?? tournamentPk;

  const resolveUser = useCallback(
    (pk: number) =>
      resolveLogUser(pk, {
        team,
        tournamentUsers,
        cache: useUserCacheStore.getState(),
      }),
    [team, tournamentUsers],
  );

  const submit = (values: TeamActionReasonValues): Promise<void> => {
    if (!request || !team) return Promise.resolve();
    const action = withOutgoingDropout(
      withReplacing(request.action, team, values.replacing_id),
      values.mark_outgoing_dropout,
    );
    lastReasons.current[action.kind] = values.reason;
    pendingRef.current = { action, reason: values.reason };
    setActionReason(values.reason);
    setError(null);
    return run().then(() => undefined);
  };

  const handleOpenChange = (next: boolean) => {
    if (!next) setError(null);
    onOpenChange(next);
  };

  return (
    <>
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent
          data-testid="team-manage-dialog"
          className={DIALOG_SCREEN_CSS}
        >
          <DialogHeader>
            <div
              className="flex flex-wrap items-center gap-2"
              data-testid="team-manage-title-row"
            >
              <DialogTitle>
                {team ? `Manage ${team.name}` : 'Manage team'}
              </DialogTitle>
              {team ? <TeamStatusBadge placement={team.placement} /> : null}
              {team?.can_manage_team && placementTournamentPk != null ? (
                <TeamPlacementControl
                  tournamentId={placementTournamentPk}
                  teamId={team.pk}
                  teamName={team.name}
                  placement={team.placement}
                />
              ) : null}
            </div>
            <DialogDescription>
              Every change needs a reason and is recorded in the team history.
            </DialogDescription>
          </DialogHeader>
          <Tabs
            value={tab}
            onValueChange={setTab}
            className="min-h-0 min-w-0 flex-1"
          >
            <TabsList className="self-start">
              <TabsTrigger value="roster" data-testid="team-manage-tab-roster">
                Roster
              </TabsTrigger>
              <TabsTrigger
                value="history"
                data-testid="team-manage-tab-history"
              >
                History
              </TabsTrigger>
            </TabsList>
            <TabsContent value="roster" className="flex min-h-0 flex-col">
              <ScrollArea
                className={TAB_SCROLL_CSS}
                data-testid="team-manage-roster-scroll"
              >
                <div className="p-1">
                  {team ? (
                    <TeamRosterPanel
                      team={team}
                      pending={pending}
                      error={error}
                      onRequestAction={requestAction}
                      onReplaceCaptain={openCaptainPicker}
                      addStandinSlot={
                        <div className="flex flex-wrap gap-2">
                          <AddStandinPicker
                            organization={organization ?? null}
                            leaguePk={leaguePk}
                            excludePks={rosterPks(team)}
                            otherTeamPks={team.other_team_user_pks ?? []}
                            otherTeams={team.other_teams}
                            disabled={pending}
                            onPick={(user) =>
                              requestAction(addStandinRequest(team, user))
                            }
                          />
                          <UserCandidatePicker
                            mode="captain"
                            testIdPrefix="team-captain"
                            triggerTestId="team-replace-captain-trigger"
                            organization={organization ?? null}
                            leaguePk={leaguePk}
                            excludePks={rosterPks(team)}
                            otherTeamPks={team.other_team_user_pks ?? []}
                            otherTeams={team.other_teams}
                            teamRows={teamCandidateRows(team)}
                            tournamentUsers={candidateUsers}
                            open={captainPickerOpen}
                            onOpenChange={setCaptainPickerOpen}
                            disabled={pending}
                            onPick={(user) =>
                              requestAction(replaceCaptainRequest(team, user))
                            }
                          />
                        </div>
                      }
                    />
                  ) : managed.isError && managedStatus !== 404 ? (
                    <Alert variant="destructive">
                      <AlertDescription>
                        This team could not be loaded. Try again.
                      </AlertDescription>
                    </Alert>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      Loading team…
                    </p>
                  )}
                </div>
              </ScrollArea>
            </TabsContent>
            <TabsContent value="history" className="flex min-h-0 flex-col">
              <ScrollArea
                className={TAB_SCROLL_CSS}
                data-testid="team-manage-history-scroll-area"
              >
                <div className="p-1">
                  {history.isError && historyStatus !== 404 ? (
                    <Alert variant="destructive">
                      <AlertDescription>
                        Team history could not be loaded. Try again.
                      </AlertDescription>
                    </Alert>
                  ) : (
                    <TeamHistoryTable
                      page={history.data}
                      resolveUser={resolveUser}
                      loading={history.isFetching}
                      onPrevious={() =>
                        setHistoryPage((p) => Math.max(1, p - 1))
                      }
                      onNext={() => setHistoryPage((p) => p + 1)}
                    />
                  )}
                </div>
              </ScrollArea>
            </TabsContent>
          </Tabs>
        </DialogContent>
      </Dialog>

      {request ? (
        <TeamActionReasonDialog
          open={reasonOpen}
          onOpenChange={setReasonOpen}
          title={request.title}
          summary={request.summary}
          warning={request.warning}
          confirmText={request.confirmText}
          destructive={request.destructive}
          defaultReason={lastReasons.current[request.action.kind] ?? ''}
          replacingOptions={request.withReplacing ? team?.members : undefined}
          replacingCaptain={request.replacingCaptain}
          outgoingDropout={request.outgoingDropout}
          pending={pending}
          onSubmit={submit}
        />
      ) : null}

      <OverrideWarningDialog
        {...dialogProps}
        organization={organization ?? null}
        minReasonLength={3}
        reasonLabel={OVERRIDE_REASON_LABEL}
        defaultReason={actionReason}
      />
    </>
  );
}
