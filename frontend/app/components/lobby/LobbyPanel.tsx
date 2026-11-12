import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Copy, Loader2, Mail, Play, Plus, RotateCcw, X } from 'lucide-react';
import { Badge } from '~/components/ui/badge';
import { DestructiveButton, PrimaryButton, SecondaryButton } from '~/components/ui/buttons';
import { ConfirmDialog } from '~/components/ui/dialogs';
import {
  useCloseGameLobby,
  useCreateGameLobby,
  useGameLobby,
  useInviteToGameLobby,
  useLaunchGameLobby,
} from '~/hooks/useGameLobby';
import { cn } from '~/lib/utils';
import { useUserStore } from '~/store/userStore';
import { lobbyErrorText, lobbyRequestErrorText } from './api';
import { isInLobby, needsInvite, playerStatusText } from './players';
import {
  JOINABLE_LOBBY_STATES,
  PREGAME_LOBBY_STATES,
  type GameLobby,
  type GameLobbyResponse,
  type LobbyPlayer,
} from './schemas';
import { lobbyStateLabel, lobbyStateTone } from './states';

interface LobbyPanelProps {
  gameId: number;
}

/**
 * The game's dota_lobby lobby in the match modal: state, name and password
 * for the game's players and staff, invite and seat status, and the staff
 * controls (create, retry, invite, launch, close). Hidden when lobbies are
 * off for the tournament and the game never had one.
 */
export function LobbyPanel({ gameId }: LobbyPanelProps) {
  const { data, isLoading } = useGameLobby(gameId);

  if (isLoading) {
    return (
      <div className="border-t pt-4" data-testid="lobby-panel-loading">
        <Loader2 className="size-4 animate-spin text-muted-foreground" />
      </div>
    );
  }
  if (!data || (!data.enabled && !data.lobby)) return null;

  return <LobbyPanelBody gameId={gameId} data={data} />;
}

export function LobbyPanelBody({ gameId, data }: { gameId: number; data: GameLobbyResponse }) {
  const lobby = data.lobby;
  const active = lobby && !lobby.ended ? lobby : null;
  const players = lobby?.players?.length ? lobby.players : (data.players ?? []);
  const currentUserPk = useUserStore((state) => state.currentUser?.pk);
  const self = players.find((p) => p.user_id === currentUserPk);
  const joinable = !!active && JOINABLE_LOBBY_STATES.includes(active.state);

  return (
    <div className="border-t pt-4 space-y-3" data-testid="lobby-panel">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium">Dota lobby</p>
        {lobby ? (
          <Badge
            variant="outline"
            className={cn('text-xs', lobbyStateTone(lobby.state))}
            data-testid="lobby-state-badge"
            data-lobby-state={lobby.state}
          >
            {lobbyStateLabel(lobby.state)}
          </Badge>
        ) : (
          <span className="text-xs text-muted-foreground" data-testid="lobby-state-none">
            No lobby yet
          </span>
        )}
      </div>

      {lobby && <LobbyDetails lobby={lobby} />}
      {lobby && <ProvisionalResult lobby={lobby} />}
      {lobby?.last_error_code && (
        <p className="text-xs text-destructive" data-testid="lobby-error">
          {lobbyErrorText(lobby.last_error_code, lobby.last_error_detail ?? undefined)}
        </p>
      )}

      {data.can_manage && !active && data.eligibility && !data.eligibility.ok && (
        <EligibilityHint eligibility={data.eligibility} />
      )}

      {players.length > 0 && (
        <PlayerList
          gameId={gameId}
          players={players}
          canManage={data.can_manage}
          canInvite={joinable}
        />
      )}

      {data.is_player && joinable && !(self && isInLobby(self)) && (
        <SelfInviteButton gameId={gameId} />
      )}

      {data.can_manage && (
        <StaffControls gameId={gameId} data={data} active={active} players={players} />
      )}
    </div>
  );
}

function LobbyDetails({ lobby }: { lobby: GameLobby }) {
  const copyPassword = async () => {
    if (!lobby.password) return;
    try {
      await navigator.clipboard.writeText(lobby.password);
      toast.success('Password copied');
    } catch {
      toast.error('Could not copy the password');
    }
  };

  return (
    <div className="space-y-1 text-sm">
      {lobby.name && (
        <p data-testid="lobby-name">
          <span className="text-muted-foreground">Name: </span>
          {lobby.name}
        </p>
      )}
      {lobby.password && (
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground">Password: </span>
          <code className="rounded bg-muted px-1.5 py-0.5" data-testid="lobby-password">
            {lobby.password}
          </code>
          <SecondaryButton
            size="sm"
            onClick={copyPassword}
            aria-label="Copy lobby password"
            data-testid="lobby-copy-password"
          >
            <Copy className="size-4" />
          </SecondaryButton>
        </div>
      )}
      {lobby.radiant_team && lobby.dire_team && (
        <p className="text-xs text-muted-foreground" data-testid="lobby-sides">
          Radiant: {lobby.radiant_team.name} · Dire: {lobby.dire_team.name}
        </p>
      )}
      {lobby.match_id && (
        <p className="text-xs text-muted-foreground" data-testid="lobby-match-id">
          Lobby match ID: {lobby.match_id}
        </p>
      )}
    </div>
  );
}

function provisionalWinnerName(lobby: GameLobby): string | null {
  const teams = [lobby.radiant_team, lobby.dire_team];
  const byId = teams.find((t) => t && t.id === lobby.provisional_winner_team_id);
  if (byId) return byId.name;
  if (lobby.provisional_winner_side === 'radiant') return lobby.radiant_team?.name ?? 'Radiant';
  if (lobby.provisional_winner_side === 'dire') return lobby.dire_team?.name ?? 'Dire';
  return null;
}

function ProvisionalResult({ lobby }: { lobby: GameLobby }) {
  if (lobby.provisional_scored === false) {
    return (
      <p
        className="rounded-md border border-yellow-600/50 bg-yellow-500/10 p-2 text-xs"
        data-testid="lobby-provisional-result"
      >
        The lobby reported the match ended without a scored result.
      </p>
    );
  }
  const winner = provisionalWinnerName(lobby);
  if (!winner) return null;
  const side = lobby.provisional_winner_side === 'dire' ? 'Dire' : 'Radiant';
  return (
    <p
      className="rounded-md border border-yellow-600/50 bg-yellow-500/10 p-2 text-xs"
      data-testid="lobby-provisional-result"
    >
      Lobby reported: {winner} ({side}) win, provisional. Confirm the winner below; the
      Steam match link stays authoritative.
    </p>
  );
}

function EligibilityHint({
  eligibility,
}: {
  eligibility: NonNullable<GameLobbyResponse['eligibility']>;
}) {
  const missing = eligibility.details.players ?? [];
  return (
    <div className="text-xs text-muted-foreground" data-testid="lobby-eligibility">
      <p>{lobbyErrorText(eligibility.code)}</p>
      {missing.length > 0 && (
        <p data-testid="lobby-missing-players">
          Without Steam: {missing.map((p) => p.name).join(', ')}
        </p>
      )}
    </div>
  );
}

function PlayerList({
  gameId,
  players,
  canManage,
  canInvite,
}: {
  gameId: number;
  players: LobbyPlayer[];
  canManage: boolean;
  canInvite: boolean;
}) {
  const { t } = useTranslation('lobby');
  const invite = useInviteToGameLobby(gameId);

  const reinvite = async (player: LobbyPlayer) => {
    if (player.account_id === null) return;
    try {
      const result = await invite.mutateAsync({ players: [player.account_id] });
      if (result.invited.length) toast.success(`Invite sent to ${player.name}`);
      else toast.info(`${player.name} was not invited (${result.skipped[0]?.reason ?? 'skipped'})`);
    } catch (error) {
      toast.error('Invite failed', { description: lobbyRequestErrorText(error) });
    }
  };

  return (
    <div className="grid gap-3 sm:grid-cols-2" data-testid="lobby-players">
      {(['radiant', 'dire'] as const).map((side) => (
        <div key={side} className="min-w-0 space-y-1.5">
          <p className="text-xs font-medium capitalize text-muted-foreground">{side}</p>
          {players
            .filter((p) => p.side === side)
            .map((player) => (
              // Name first, status beneath: the name gets the full width and
              // wraps instead of being cut off by the status text.
              <div
                key={player.user_id}
                className="flex items-start justify-between gap-2 text-xs"
                data-testid={`lobby-player-${player.user_id}`}
                data-status={player.status}
                data-seat={player.seat ?? undefined}
              >
                <div className="min-w-0 flex-1">
                  <p
                    className="font-medium leading-snug [overflow-wrap:anywhere]"
                    data-testid={`lobby-player-name-${player.user_id}`}
                  >
                    {player.name}
                    {player.captain && (
                      <span className="font-normal text-muted-foreground"> (C)</span>
                    )}
                  </p>
                  <p
                    className={cn(
                      'leading-snug text-muted-foreground',
                      player.account_id === null && 'text-destructive',
                    )}
                    data-testid={`lobby-player-status-${player.user_id}`}
                  >
                    {playerStatusText(player, t)}
                  </p>
                </div>
                {canManage && canInvite && needsInvite(player) && (
                  <button
                    type="button"
                    className="shrink-0 rounded p-1 hover:bg-muted"
                    onClick={() => reinvite(player)}
                    disabled={invite.isPending}
                    aria-label={`Invite ${player.name} again`}
                    title={`Invite ${player.name} again`}
                    data-testid={`lobby-reinvite-${player.user_id}`}
                  >
                    <Mail className="size-3.5" />
                  </button>
                )}
              </div>
            ))}
        </div>
      ))}
    </div>
  );
}

function SelfInviteButton({ gameId }: { gameId: number }) {
  const invite = useInviteToGameLobby(gameId);
  const onClick = async () => {
    try {
      const result = await invite.mutateAsync({});
      if (result.invited.length) toast.success('Invite sent. Check your Dota 2 client.');
      else toast.info(`No invite sent (${result.skipped[0]?.reason ?? 'skipped'})`);
    } catch (error) {
      toast.error('Invite failed', { description: lobbyRequestErrorText(error) });
    }
  };
  return (
    <SecondaryButton
      size="sm"
      onClick={onClick}
      disabled={invite.isPending}
      data-testid="lobby-invite-me"
    >
      {invite.isPending ? (
        <Loader2 className="size-4 mr-1 animate-spin" />
      ) : (
        <Mail className="size-4 mr-1" />
      )}
      Send me an invite
    </SecondaryButton>
  );
}

function StaffControls({
  gameId,
  data,
  active,
  players,
}: {
  gameId: number;
  data: GameLobbyResponse;
  active: GameLobby | null;
  players: LobbyPlayer[];
}) {
  const create = useCreateGameLobby(gameId);
  const close = useCloseGameLobby(gameId);
  const invite = useInviteToGameLobby(gameId);
  const launch = useLaunchGameLobby(gameId);
  const [confirmClose, setConfirmClose] = useState(false);
  const [confirmForce, setConfirmForce] = useState(false);
  const [confirmReplay, setConfirmReplay] = useState(false);

  // The backend decides whether a lobby may be created; it also knows whether
  // a played match was for the game's current teams.
  const eligibility = data.eligibility;
  const missingSteam = eligibility?.code === 'missing_steam_ids';
  const canCreate = !active && (eligibility?.ok || missingSteam);
  // After a played match staff confirm the winner, or replay it on purpose.
  const canReplay = !active && eligibility?.code === 'lobby_match_played';
  const isRetry = !!data.lobby && data.lobby.ended;
  const joinable = !!active && JOINABLE_LOBBY_STATES.includes(active.state);
  const anyoneToInvite = players.some(needsInvite);
  const pregame = !!active && PREGAME_LOBBY_STATES.includes(active.state);

  const run = async (label: string, action: () => Promise<unknown>, success: string) => {
    try {
      await action();
      toast.success(success);
    } catch (error) {
      toast.error(`${label} failed`, { description: lobbyRequestErrorText(error) });
    }
  };

  if (!data.enabled && !active) return null;

  return (
    <div className="flex flex-wrap gap-2" data-testid="lobby-staff-controls">
      {canCreate && (
        <PrimaryButton
          size="sm"
          onClick={() =>
            run(
              'Lobby request',
              () => create.mutateAsync({ allowMissing: missingSteam }),
              'Lobby requested',
            )
          }
          disabled={create.isPending}
          data-testid="lobby-create-btn"
        >
          {create.isPending ? (
            <Loader2 className="size-4 mr-1 animate-spin" />
          ) : isRetry ? (
            <RotateCcw className="size-4 mr-1" />
          ) : (
            <Plus className="size-4 mr-1" />
          )}
          {isRetry ? 'Retry lobby' : 'Create lobby'}
          {missingSteam && ' without missing players'}
        </PrimaryButton>
      )}
      {canReplay && (
        <SecondaryButton
          size="sm"
          onClick={() => setConfirmReplay(true)}
          disabled={create.isPending}
          data-testid="lobby-replay-btn"
        >
          <RotateCcw className="size-4 mr-1" />
          Replay match
        </SecondaryButton>
      )}
      {pregame && active?.state !== 'requested' && (
        <SecondaryButton
          size="sm"
          onClick={() =>
            run('Lobby request', () => create.mutateAsync({ replace: true }), 'New lobby requested')
          }
          disabled={create.isPending}
          data-testid="lobby-recreate-btn"
        >
          <RotateCcw className="size-4 mr-1" />
          Recreate
        </SecondaryButton>
      )}
      {joinable && anyoneToInvite && (
        <SecondaryButton
          size="sm"
          onClick={() =>
            run('Invite', () => invite.mutateAsync({ missing: true }), 'Invites sent')
          }
          disabled={invite.isPending}
          data-testid="lobby-invite-missing-btn"
        >
          <Mail className="size-4 mr-1" />
          Invite missing
        </SecondaryButton>
      )}
      {joinable && (
        <SecondaryButton
          size="sm"
          onClick={() =>
            active?.state === 'ready'
              ? run('Launch', () => launch.mutateAsync(false), 'Launching the match')
              : setConfirmForce(true)
          }
          disabled={launch.isPending}
          data-testid="lobby-launch-btn"
        >
          {launch.isPending ? (
            <Loader2 className="size-4 mr-1 animate-spin" />
          ) : (
            <Play className="size-4 mr-1" />
          )}
          Launch
        </SecondaryButton>
      )}
      {pregame && (
        <DestructiveButton
          size="sm"
          onClick={() => setConfirmClose(true)}
          disabled={close.isPending}
          data-testid="lobby-close-btn"
        >
          <X className="size-4 mr-1" />
          Close
        </DestructiveButton>
      )}

      <ConfirmDialog
        open={confirmForce}
        onOpenChange={setConfirmForce}
        title="Force launch?"
        description="Not every player is seated and ready. Launching now starts the match as the lobby is."
        confirmLabel="Force launch"
        variant="warning"
        isLoading={launch.isPending}
        confirmTestId="lobby-force-launch-confirm"
        onConfirm={async () => {
          await run('Launch', () => launch.mutateAsync(true), 'Launching the match');
          setConfirmForce(false);
        }}
      />
      <ConfirmDialog
        open={confirmReplay}
        onOpenChange={setConfirmReplay}
        title="Replay the match?"
        description="These teams already played this game in a lobby. A new lobby hosts the match again; confirm the winner instead if its result stands."
        confirmLabel="Replay match"
        variant="warning"
        isLoading={create.isPending}
        confirmTestId="lobby-replay-confirm"
        onConfirm={async () => {
          await run(
            'Lobby request',
            () => create.mutateAsync({ replay: true }),
            'New lobby requested',
          );
          setConfirmReplay(false);
        }}
      />
      <ConfirmDialog
        open={confirmClose}
        onOpenChange={setConfirmClose}
        title="Close the lobby?"
        description="The bot closes the in-game lobby. You can create a new one afterwards."
        confirmLabel="Close lobby"
        variant="destructive"
        isLoading={close.isPending}
        confirmTestId="lobby-close-confirm"
        onConfirm={async () => {
          await run('Close', () => close.mutateAsync(), 'Lobby closed');
          setConfirmClose(false);
        }}
      />
    </div>
  );
}
