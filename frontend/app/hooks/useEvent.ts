import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  approveSignup as approveSignupAPI,
  cancelEvent as cancelEventAPI,
  restartTournament as restartTournamentAPI,
  cancelSignup as cancelSignupAPI,
  confirmSignup as confirmSignupAPI,
  createEvent as createEventAPI,
  createEventRepeater as createEventRepeaterAPI,
  updateEventRepeater as updateEventRepeaterAPI,
  getEvent,
  getEvents,
  getEventRepeaters,
  getEventSignups,
  openSignups as openSignupsAPI,
  rejectSignup as rejectSignupAPI,
  rsvpForEvent,
  startRollCall as startRollCallAPI,
  startTournament as startTournamentAPI,
  subscribeToRepeater,
  unsubscribeFromRepeater,
  updateEvent as updateEventAPI,
  updateOrgEventDefaults,
} from '~/components/api/api';
import type { EventRepeaterType } from '~/components/api/api';
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
    restartTournament: useMutation({
      mutationFn: () => restartTournamentAPI(eventId),
      onSuccess: (data) => {
        queryClient.setQueryData(['event', eventId], data);
        queryClient.invalidateQueries({ queryKey: ['events'] });
      },
    }),
  };
}

export function useEventRepeaters(params?: { organization?: number }) {
  return useQuery<EventRepeaterType[]>({
    queryKey: ['event-repeaters', params],
    queryFn: () => getEventRepeaters(params),
  });
}

export function useCreateEventMutation(organizationId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<EventType>) => createEventAPI(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['events', { organization: organizationId }] });
    },
  });
}

export function useCreateEventRepeaterMutation(organizationId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<EventRepeaterType>) => createEventRepeaterAPI(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['events', { organization: organizationId }] });
      queryClient.invalidateQueries({ queryKey: ['event-repeaters', { organization: organizationId }] });
    },
  });
}

export function useUpdateEventRepeaterMutation(repeaterId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<EventRepeaterType>) => updateEventRepeaterAPI(repeaterId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['event-repeaters'] });
      queryClient.invalidateQueries({ queryKey: ['events'] });
    },
  });
}

export function useUpdateEventMutation(eventId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<EventType>) => updateEventAPI(eventId, payload),
    onSuccess: (data) => {
      queryClient.setQueryData(['event', eventId], data);
      queryClient.invalidateQueries({ queryKey: ['events'] });
    },
  });
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

export function useRepeaterSubscriptionMutation() {
  const queryClient = useQueryClient();
  return {
    subscribe: useMutation({
      mutationFn: (repeaterId: number) => subscribeToRepeater(repeaterId),
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['event-repeaters'] });
      },
    }),
    unsubscribe: useMutation({
      mutationFn: (repeaterId: number) => unsubscribeFromRepeater(repeaterId),
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['event-repeaters'] });
      },
    }),
  };
}

export function useUpdateOrgDefaultsMutation(orgId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Record<string, unknown> }) =>
      updateOrgEventDefaults(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['org-event-defaults', orgId] });
    },
  });
}
