import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  approveSignup as approveSignupAPI,
  cancelEvent as cancelEventAPI,
  cancelSignup as cancelSignupAPI,
  confirmSignup as confirmSignupAPI,
  getEvent,
  getEvents,
  getEventSignups,
  openSignups as openSignupsAPI,
  rejectSignup as rejectSignupAPI,
  rsvpForEvent,
  startRollCall as startRollCallAPI,
  startTournament as startTournamentAPI,
} from '~/components/api/api';
import type { EventSignupType, EventType } from '~/components/events/schemas';

export function useEvents(params?: { organization?: number; state?: string }) {
  return useQuery<EventType[]>({
    queryKey: ['events', params],
    queryFn: () => getEvents(params),
  });
}

export function useEvent(eventId: number | null) {
  return useQuery<EventType>({
    queryKey: ['event', eventId],
    queryFn: () => getEvent(eventId!),
    enabled: eventId !== null,
  });
}

export function useEventSignups(eventId: number | null) {
  return useQuery<EventSignupType[]>({
    queryKey: ['event-signups', eventId],
    queryFn: () => getEventSignups(eventId!),
    enabled: eventId !== null,
  });
}

export function useRsvpMutation(eventId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => rsvpForEvent(eventId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['event', eventId] });
      queryClient.invalidateQueries({ queryKey: ['event-signups', eventId] });
    },
  });
}

export function useEventActionMutation(eventId: number) {
  const queryClient = useQueryClient();
  return {
    openSignups: useMutation({
      mutationFn: () => openSignupsAPI(eventId),
      onSuccess: (data) => queryClient.setQueryData(['event', eventId], data),
    }),
    startRollCall: useMutation({
      mutationFn: () => startRollCallAPI(eventId),
      onSuccess: (data) => queryClient.setQueryData(['event', eventId], data),
    }),
    startTournament: useMutation({
      mutationFn: () => startTournamentAPI(eventId),
      onSuccess: (data) => queryClient.setQueryData(['event', eventId], data),
    }),
    cancelEvent: useMutation({
      mutationFn: () => cancelEventAPI(eventId),
      onSuccess: (data) => {
        queryClient.setQueryData(['event', eventId], data);
        queryClient.invalidateQueries({ queryKey: ['events'] });
      },
    }),
  };
}

/** Signup management mutations (approve, reject, confirm, cancel). */
export function useSignupActionMutations(eventId: number) {
  const queryClient = useQueryClient();
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['event-signups', eventId] });
    queryClient.invalidateQueries({ queryKey: ['event', eventId] });
  };
  return {
    approve: useMutation({ mutationFn: (id: number) => approveSignupAPI(id), onSuccess: invalidate }),
    reject: useMutation({ mutationFn: (id: number) => rejectSignupAPI(id), onSuccess: invalidate }),
    confirm: useMutation({ mutationFn: (id: number) => confirmSignupAPI(id), onSuccess: invalidate }),
    cancel: useMutation({ mutationFn: (id: number) => cancelSignupAPI(id), onSuccess: invalidate }),
  };
}
