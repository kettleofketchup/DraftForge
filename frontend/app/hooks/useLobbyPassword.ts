import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  getEventLobbyPassword,
  getRepeaterLobbyPassword,
  regenerateEventLobbyPassword,
} from '~/components/lobby/api';

export const eventLobbyPasswordKey = (eventId: number | null | undefined) =>
  ['event-lobby-password', eventId] as const;
export const repeaterLobbyPasswordKey = (repeaterId: number | null | undefined) =>
  ['repeater-lobby-password', repeaterId] as const;

/**
 * The event's lobby password, or null when the user may not see it (only
 * staff and registered players can). Signup changes invalidate it.
 */
export function useEventLobbyPassword(eventId: number | null | undefined, enabled = true) {
  return useQuery({
    queryKey: eventLobbyPasswordKey(eventId),
    queryFn: () => getEventLobbyPassword(eventId!),
    enabled: enabled && !!eventId,
    staleTime: 30_000,
    retry: false,
  });
}

/** The series' password settings (staff only). */
export function useRepeaterLobbyPassword(repeaterId: number | null | undefined, enabled = true) {
  return useQuery({
    queryKey: repeaterLobbyPasswordKey(repeaterId),
    queryFn: () => getRepeaterLobbyPassword(repeaterId!),
    enabled: enabled && !!repeaterId,
    staleTime: 0,
    retry: false,
  });
}

export function useRegenerateEventLobbyPassword(eventId: number | null | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => {
      if (!eventId) throw new Error('No event ID');
      return regenerateEventLobbyPassword(eventId);
    },
    onSuccess: (data) => {
      queryClient.setQueryData(eventLobbyPasswordKey(eventId), data);
    },
  });
}
