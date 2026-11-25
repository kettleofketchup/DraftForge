import { Building2, ExternalLink, Trophy } from 'lucide-react';
import { useMemo, useState, type ReactNode } from 'react';
import { Link } from 'react-router';
import { toast } from 'sonner';
import { GAME_LABEL, toGameType } from '~/components/game/constants';
import { SecondaryButton } from '~/components/ui/buttons';
import { Card, CardContent, CardHeader, CardTitle } from '~/components/ui/card';
import { ConfirmDialog } from '~/components/ui/dialogs';
import { Skeleton } from '~/components/ui/skeleton';
import { mmrScreenshotUrl } from './api';
import { formatMmrDate } from './format';
import { MmrStatusBadge } from './MmrStatusBadge';
import {
  useCancelMmrRequest,
  useMyMmrRequests,
  useUserMmrSummary,
} from './queries';
import { RequestMmrDialog, type RequestTarget } from './RequestMmrDialog';
import type {
  LastDecision,
  LeagueMmrEntry,
  OrgMmrEntry,
  PendingRequestRef,
  UserRef,
} from './schemas';

export interface OrgsMmrTabProps {
  userPk: number;
  isOwnProfile: boolean;
}

interface RowProps {
  testId: string;
  label: ReactNode;
  mmr: number;
  verified: boolean;
  legacy?: boolean;
  verifiedBy: UserRef | null;
  verifiedAt: string | null;
  pending: PendingRequestRef | null;
  lastDecision: LastDecision | null;
  requestedById: Map<number, number>;
  isOwnProfile: boolean;
  requestTestId: string;
  onRequest: (() => void) | null;
  onCancel: (id: number) => void;
}

function decisionText(
  decision: LastDecision,
  requested: number | undefined,
): string | null {
  const date = formatMmrDate(decision.reviewed_at);
  const on = date ? ` on ${date}` : '';
  const value = decision.decided_mmr;
  switch (decision.status) {
    case 'approved':
      if (value != null && requested != null && requested !== value) {
        return `Last decision: approved as ${value}, you asked ${requested}${date ? ` (${date})` : ''}`;
      }
      return `Last decision: Approved${value != null ? ` ${value}` : ''}${on}`;
    case 'rejected':
      return `Last decision: Rejected${date ? ` ${date}` : ''}${
        decision.rejection_reason ? `: ${decision.rejection_reason}` : ''
      }`;
    case 'superseded':
      return `Last decision: Replaced by a staff-set value${
        value != null ? ` of ${value}` : ''
      }${on}`;
    default:
      return null;
  }
}

function MmrRow({
  testId,
  label,
  mmr,
  verified,
  legacy,
  verifiedBy,
  verifiedAt,
  pending,
  lastDecision,
  requestedById,
  isOwnProfile,
  requestTestId,
  onRequest,
  onCancel,
}: RowProps) {
  const decision =
    isOwnProfile && lastDecision
      ? decisionText(lastDecision, requestedById.get(lastDecision.id))
      : null;
  const pendingDate = pending ? formatMmrDate(pending.created_at) : null;

  return (
    <div
      className="flex flex-col gap-2 border-b border-border/60 py-3 last:border-b-0 sm:flex-row sm:items-start sm:justify-between"
      data-testid={testId}
    >
      <div className="flex min-w-0 flex-col gap-1">
        <span className="text-sm text-muted-foreground">{label}</span>
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-lg font-semibold">
            {mmr > 0 ? mmr : '—'}
          </span>
          {mmr > 0 ? (
            <MmrStatusBadge
              verified={verified}
              legacy={legacy}
              pending={isOwnProfile && pending != null}
              verifiedBy={verifiedBy?.username}
              verifiedAt={verifiedAt}
            />
          ) : (
            <span className="text-sm text-muted-foreground">Not set</span>
          )}
        </div>
        {isOwnProfile && pending && (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span data-testid={`mmr-pending-${pending.id}`}>
              Pending: {pending.requested_mmr}
              {pendingDate ? ` since ${pendingDate}` : ''}
            </span>
            <a
              href={mmrScreenshotUrl(pending.id)}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline"
              data-testid={`mmr-pending-screenshot-${pending.id}`}
            >
              View screenshot
              <ExternalLink className="size-3.5" aria-hidden />
            </a>
            <SecondaryButton
              type="button"
              size="sm"
              onClick={() => onCancel(pending.id)}
              data-testid={`mmr-cancel-btn-${pending.id}`}
            >
              Cancel request
            </SecondaryButton>
            <span
              className="basis-full text-xs text-muted-foreground"
              data-testid={`mmr-pending-hint-${pending.id}`}
            >
              To ask for a different value, cancel this request first.
            </span>
          </div>
        )}
        {decision && lastDecision && (
          <span
            className="text-xs text-muted-foreground"
            data-testid={`mmr-last-decision-${lastDecision.id}`}
          >
            {decision}
          </span>
        )}
      </div>
      {isOwnProfile && onRequest && !pending && (
        <SecondaryButton
          type="button"
          size="sm"
          className="min-h-11 self-start sm:min-h-9"
          onClick={onRequest}
          data-testid={requestTestId}
        >
          Request update
        </SecondaryButton>
      )}
    </div>
  );
}

function OrgLogo({ org }: { org: OrgMmrEntry['organization'] }) {
  return org.logo ? (
    <img
      src={org.logo}
      alt={org.name}
      className="size-10 rounded-lg object-cover"
    />
  ) : (
    <div className="flex size-10 items-center justify-center rounded-lg bg-muted">
      <Building2 className="size-5 text-muted-foreground" aria-hidden />
    </div>
  );
}

export function OrgsMmrTab({ userPk, isOwnProfile }: OrgsMmrTabProps) {
  const summary = useUserMmrSummary(userPk);
  const mine = useMyMmrRequests(isOwnProfile);
  const cancel = useCancelMmrRequest(userPk);
  const [target, setTarget] = useState<RequestTarget | null>(null);
  const [cancelId, setCancelId] = useState<number | null>(null);

  const requestedById = useMemo(
    () => new Map((mine.data ?? []).map((r) => [r.id, r.requested_mmr])),
    [mine.data],
  );

  if (summary.isLoading) {
    return (
      <div className="space-y-4" data-testid="mmr-tab-loading">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (summary.isError || !summary.data) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          Couldn't load MMRs.
        </CardContent>
      </Card>
    );
  }

  const { orgs, leagues } = summary.data;
  const visibleOrgs = new Map(orgs.map((o) => [o.organization.pk, o]));
  const nested = (orgPk: number) =>
    leagues.filter((l) => l.organization_pk === orgPk);
  const standalone = leagues.filter(
    (l) => l.organization_pk == null || !visibleOrgs.has(l.organization_pk),
  );

  if (orgs.length === 0 && leagues.length === 0) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          <Trophy className="mx-auto mb-4 size-12 opacity-50" aria-hidden />
          <p>
            {isOwnProfile
              ? "You're not in any orgs yet"
              : 'No public org memberships'}
          </p>
        </CardContent>
      </Card>
    );
  }

  const confirmCancel = async () => {
    if (cancelId == null) return;
    try {
      await cancel.mutateAsync(cancelId);
      toast.success('Request cancelled');
    } catch (error) {
      const status = (error as { response?: { status?: number } })?.response
        ?.status;
      toast.error(
        status === 409
          ? 'This request was already reviewed'
          : 'Could not cancel the request',
      );
    }
  };

  const leagueRow = (entry: LeagueMmrEntry, orgName?: string) => {
    const leagueUserPk = entry.league_user_pk;
    return (
      <MmrRow
        key={`league-${entry.league.pk}`}
        testId={`mmr-row-league-${entry.league.pk}`}
        label={`League · ${entry.league.name}`}
        mmr={entry.mmr}
        verified={entry.verified}
        verifiedBy={entry.verified_by}
        verifiedAt={entry.verified_at}
        pending={entry.pending_request}
        lastDecision={entry.last_decision}
        requestedById={requestedById}
        isOwnProfile={isOwnProfile}
        requestTestId={`mmr-request-btn-league-${entry.league.pk}`}
        onRequest={
          leagueUserPk == null
            ? null
            : () =>
                setTarget({
                  kind: 'league',
                  leagueUserPk,
                  leagueName: entry.league.name,
                  orgName,
                  current: entry.mmr,
                  currentVerified: entry.verified,
                })
        }
        onCancel={setCancelId}
      />
    );
  };

  return (
    <div className="space-y-4" data-testid="mmr-tab">
      {orgs.map((entry) => {
        const org = entry.organization;
        const orgUserPk = entry.org_user_pk;
        return (
          <Card key={org.pk} data-testid={`mmr-org-block-${org.pk}`}>
            <CardHeader className="flex flex-row items-center gap-3">
              <OrgLogo org={org} />
              <CardTitle className="min-w-0 truncate text-lg">
                <Link
                  to={`/organizations/${org.pk}`}
                  className="hover:underline"
                >
                  {org.name}
                </Link>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {entry.game_mmrs.map((game) => (
                <MmrRow
                  key={game.game_type}
                  testId={`mmr-row-org-${org.pk}-${game.game_type}`}
                  label={GAME_LABEL[toGameType(game.game_type)]}
                  mmr={game.mmr}
                  verified={game.verified}
                  legacy={game.legacy_verified}
                  verifiedBy={game.verified_by}
                  verifiedAt={game.verified_at}
                  pending={game.pending_request}
                  lastDecision={game.last_decision}
                  requestedById={requestedById}
                  isOwnProfile={isOwnProfile}
                  requestTestId={`mmr-request-btn-org-${org.pk}-${game.game_type}`}
                  onRequest={
                    orgUserPk == null
                      ? null
                      : () =>
                          setTarget({
                            kind: 'org',
                            orgUserPk,
                            orgName: org.name,
                            gameType: game.game_type,
                            current: game.mmr,
                            currentVerified: game.verified,
                          })
                  }
                  onCancel={setCancelId}
                />
              ))}
              {nested(org.pk).map((league) => leagueRow(league, org.name))}
            </CardContent>
          </Card>
        );
      })}

      {standalone.length > 0 && (
        <Card data-testid="mmr-standalone-leagues">
          <CardHeader>
            <CardTitle className="text-lg">Leagues</CardTitle>
          </CardHeader>
          <CardContent>
            {standalone.map((league) => leagueRow(league))}
          </CardContent>
        </Card>
      )}

      {target && (
        <RequestMmrDialog
          open
          onOpenChange={(open) => {
            if (!open) setTarget(null);
          }}
          target={target}
        />
      )}

      <ConfirmDialog
        open={cancelId != null}
        onOpenChange={(open) => {
          if (!open) setCancelId(null);
        }}
        title="Cancel this MMR request?"
        description="Staff will no longer see it. You can send a new request afterwards."
        confirmLabel="Cancel request"
        cancelLabel="Keep it"
        variant="destructive"
        isLoading={cancel.isPending}
        onConfirm={confirmCancel}
        confirmTestId="mmr-cancel-confirm"
        cancelTestId="mmr-cancel-dismiss"
      />
    </div>
  );
}
