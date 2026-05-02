import { useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  approveSignup as approveSignupAPI,
  cancelEvent as cancelEventAPI,
  deleteEvent as deleteEventAPI,
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
  reopenSignups as reopenSignupsAPI,
  rejectSignup as rejectSignupAPI,
  unconfirmSignup as unconfirmSignupAPI,
  demoteSignup as demoteSignupAPI,
  reinstateSignup as reinstateSignupAPI,
  rsvpForEvent,
  tentativeForEvent,
  startRollCall as startRollCallAPI,
  startTournament as startTournamentAPI,
  subscribeToRepeater,
  unsubscribeFromRepeater,
  updateEvent as updateEventAPI,
  updateOrgEventDefaults,
} from '~/components/api/api';
import type { EventRepeaterType } from '~/components/api/api';
import type { EventSignupType, EventType } from '~/components/events/schemas';
import type { UserType } from '~/components/user/types';
import { useUserCacheStore } from '~/store/userCacheStore';

export function useEvents(params?: {
  organization?: number;
  state?: string;
  states?: string[];
  search?: string;
  ordering?: string;
  event_repeater?: number;
}) {
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
    staleTime: 5 * 1000, // 5s — signups change frequently during event lifecycle
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
    onError: () => {
      queryClient.invalidateQueries({ queryKey: ['event-signups', eventId] });
    },
  });
}

export function useTentativeMutation(eventId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => tentativeForEvent(eventId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['event', eventId] });
      queryClient.invalidateQueries({ queryKey: ['event-signups', eventId] });
    },
    onError: () => {
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
    reopenSignups: useMutation({
      // Corrective transition; no optimistic update intentionally.
      mutationFn: () => reopenSignupsAPI(eventId),
      onSuccess: (data) => {
        queryClient.setQueryData(['event', eventId], data);
        // The events list filters by state — a regression from roll_call → signups_open
        // changes which lists this event appears in.
        queryClient.invalidateQueries({ queryKey: ['events'] });
      },
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
    deleteEvent: useMutation({
      mutationFn: () => deleteEventAPI(eventId),
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['events'] });
        queryClient.removeQueries({ queryKey: ['event', eventId] });
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
      // The Activity Log + Task Schedule panels poll on their own
      // cadences; invalidate them here so reminder-timing edits surface
      // immediately instead of after the next 15s poll.
      queryClient.invalidateQueries({ queryKey: ['event-discord', eventId] });
      queryClient.invalidateQueries({ queryKey: ['event-task-schedule', eventId] });
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
    approve: useMutation({ mutationFn: ({ id, mmr }: { id: number; mmr?: number }) => approveSignupAPI(id, mmr), onSuccess: invalidate }),
    reject: useMutation({ mutationFn: (id: number) => rejectSignupAPI(id), onSuccess: invalidate }),
    confirm: useMutation({ mutationFn: (id: number) => confirmSignupAPI(id), onSuccess: invalidate }),
    cancel: useMutation({ mutationFn: (id: number) => cancelSignupAPI(id), onSuccess: invalidate }),
    unconfirm: useMutation({ mutationFn: (id: number) => unconfirmSignupAPI(id), onSuccess: invalidate }),
    demote: useMutation({ mutationFn: (id: number) => demoteSignupAPI(id), onSuccess: invalidate }),
    reinstate: useMutation({ mutationFn: (id: number) => reinstateSignupAPI(id), onSuccess: invalidate }),
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

/**
 * Upsert signup user data into the entity adapter cache.
 * Call this after fetching signups to ensure all signup users are in the cache.
 */
export function useEventSignupUsers(signups: EventSignupType[] | undefined) {
  useEffect(() => {
    if (!signups) return;
    const users = signups
      .map((s) => s.user_data)
      .filter(Boolean) as UserType[];
    if (users.length > 0) {
      useUserCacheStore.getState().upsert(users);
    }
  }, [signups]);
}
