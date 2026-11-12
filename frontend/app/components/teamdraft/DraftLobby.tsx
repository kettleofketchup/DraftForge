import { useState } from 'react';
import { setDraftReady, startTeamDraft } from '~/components/api/draftAPI';
import type { TeamType } from '~/components/team/types';
import { PrimaryButton } from '~/components/ui/buttons';
import { ConfirmDialog } from '~/components/ui/dialogs';
import { DisplayName } from '~/components/user/avatar';
import { UserAvatar } from '~/components/user/UserAvatar';
import type { TournamentType } from '~/index';
import { hydrateTournament } from '~/lib/hydrateTournament';
import { cn } from '~/lib/utils';
import { useUserStore } from '~/store/userStore';
import { runTimerAction } from './timer/runTimerAction';

export interface DraftLobbyProps {
  draftPk: number;
  teams: TeamType[];
  currentUserPk: number | undefined;
  isStaff: boolean;
  onReadyToggle?: (ready: boolean) => Promise<unknown>;
  onStart?: () => Promise<unknown>;
}

export function DraftLobby({
  draftPk,
  teams,
  currentUserPk,
  isStaff,
  onReadyToggle,
  onStart,
}: DraftLobbyProps) {
  const setTournament = useUserStore((s) => s.setTournament);
  const setDraft = useUserStore((s) => s.setDraft);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const ordered = [...teams].sort((a, b) => (a.draft_order ?? 0) - (b.draft_order ?? 0));
  const withCaptain = ordered.filter((t) => t.captain);
  const notReady = withCaptain.filter((t) => !t.draft_is_ready);
  const allReady = notReady.length === 0;
  const myTeam = currentUserPk === undefined
    ? undefined
    : teams.find((t) => t.captain?.pk === currentUserPk);
  const myReady = !!myTeam?.draft_is_ready;

  const applyResponse = (raw: unknown) => {
    const data = hydrateTournament(raw as TournamentType & { _users?: Record<number, unknown> }) as TournamentType;
    setTournament(data);
    if (data.draft) setDraft(data.draft);
  };

  const run = async (action: () => Promise<unknown>, fallback: string) => {
    setBusy(true);
    try {
      await runTimerAction(async () => {
        const res = await action();
        if (res && typeof res === 'object' && Object.keys(res).length > 0) applyResponse(res);
      }, fallback);
    } finally {
      setBusy(false);
    }
  };

  const toggleReady = () =>
    run(
      () => (onReadyToggle ?? ((r: boolean) => setDraftReady(draftPk, r)))(!myReady),
      'Failed to update ready state',
    );
  const start = () =>
    run(() => (onStart ?? (() => startTeamDraft(draftPk)))(), 'Failed to start draft');

  const onStartClick = () => {
    if (allReady) void start();
    else setConfirmOpen(true);
  };

  return (
    <div data-testid="draft-lobby" className="flex flex-col gap-4">
      <ul className="flex flex-col gap-2">
        {ordered.map((team) => (
          <li
            key={team.pk}
            data-testid={`lobby-team-row-${team.pk}`}
            className="flex items-center gap-3 rounded-md border border-border/50 px-3 py-2"
          >
            {team.captain && <UserAvatar user={team.captain} size="sm" />}
            <span className="flex-1 truncate">{team.captain ? DisplayName(team.captain) : team.name}</span>
            <span
              data-testid={`lobby-connected-dot-${team.pk}`}
              data-state={team.draft_is_connected ? 'connected' : 'disconnected'}
              title={team.draft_is_connected ? 'Connected' : 'Disconnected'}
              className={cn('h-2.5 w-2.5 rounded-full', team.draft_is_connected ? 'bg-green-500' : 'bg-gray-500')}
            />
            <span
              data-testid={`lobby-ready-check-${team.pk}`}
              data-state={team.draft_is_ready ? 'ready' : 'not-ready'}
              className={cn('text-sm', team.draft_is_ready ? 'text-green-400' : 'text-muted-foreground')}
            >
              {team.draft_is_ready ? 'Ready' : 'Not ready'}
            </span>
          </li>
        ))}
      </ul>

      {myTeam && (
        <PrimaryButton data-testid="lobby-ready-toggle" disabled={busy} onClick={() => void toggleReady()}>
          {myReady ? 'Not ready' : 'Ready up'}
        </PrimaryButton>
      )}
      {myTeam && !isStaff && allReady && (
        <p data-testid="lobby-waiting-for-staff" className="text-sm text-muted-foreground">
          Waiting for staff to start
        </p>
      )}

      {isStaff && (
        <>
          <PrimaryButton data-testid="lobby-start-button" disabled={busy} onClick={onStartClick}>
            {allReady ? 'Start draft' : 'Force start'}
          </PrimaryButton>
          <ConfirmDialog
            open={confirmOpen}
            onOpenChange={setConfirmOpen}
            title="Force start the draft?"
            description="The clock starts for the first captain immediately, whether or not they are here."
            confirmLabel="Force start"
            variant="warning"
            isLoading={busy}
            contentTestId="lobby-force-start-dialog"
            confirmTestId="lobby-force-start-confirm"
            bodyContent={
              <ul data-testid="lobby-force-start-not-ready" className="list-disc pl-5">
                {notReady.map((t) => (
                  <li key={t.pk}>{DisplayName(t.captain!)}</li>
                ))}
              </ul>
            }
            onConfirm={async () => {
              setConfirmOpen(false);
              await start();
            }}
          />
        </>
      )}
    </div>
  );
}
