import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  closeGameLobby,
  createGameLobby,
  getGameLobby,
  inviteToGameLobby,
  launchGameLobby,
  type CreateLobbyOptions,
  type InviteRequest,
} from '~/components/lobby/api';

export const gameLobbyKey = (gameId: number | null | undefined) => ['gameLobby', gameId] as const;

/**
 * A game's dota_lobby lobby. The tournament websocket invalidates it on
 * `lobby_event`; the interval is the fallback when the socket is down.
 */
export function useGameLobby(gameId: number | null | undefined, enabled = true) {
  return useQuery({
    queryKey: gameLobbyKey(gameId),
    queryFn: () => getGameLobby(gameId!),
    enabled: enabled && !!gameId,
    staleTime: 0,
    refetchInterval: 15_000,
    retry: false,
  });
}

function useLobbyMutation<TVars, TData>(
  gameId: number | null | undefined,
  fn: (gameId: number, vars: TVars) => Promise<TData>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (vars: TVars) => {
      if (!gameId) throw new Error('No game ID');
      return fn(gameId, vars);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: gameLobbyKey(gameId) });
    },
  });
}

export function useCreateGameLobby(gameId: number | null | undefined) {
  return useLobbyMutation(gameId, (id, options: CreateLobbyOptions) =>
    createGameLobby(id, options),
  );
}

export function useCloseGameLobby(gameId: number | null | undefined) {
  return useLobbyMutation(gameId, (id, _vars: void) => closeGameLobby(id));
}

export function useInviteToGameLobby(gameId: number | null | undefined) {
  return useLobbyMutation(gameId, (id, body: InviteRequest) => inviteToGameLobby(id, body));
}

export function useLaunchGameLobby(gameId: number | null | undefined) {
  return useLobbyMutation(gameId, (id, force: boolean) => launchGameLobby(id, force));
}
