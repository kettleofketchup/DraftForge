import {
  useMutation,
  useMutationState,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import { useEffect, useMemo } from 'react';

import type {
  EventRepeaterType,
  EventStaffPayload,
  EventWritePayload,
  SignupBody,
} from '~/components/api/api';
import {
  approveSignup as approveSignupAPI,
  cancelEvent as cancelEventAPI,
  cancelSignup as cancelSignupAPI,
  completeEvent as completeEventAPI,
  confirmSignup as confirmSignupAPI,
  createEvent as createEventAPI,
  createEventRepeater as createEventRepeaterAPI,
  deleteEvent as deleteEventAPI,
  demoteSignup as demoteSignupAPI,
  getEvent,
  getEventRepeaters,
  getEvents,
  getEventSignups,
  openSignups as openSignupsAPI,
  reinstateSignup as reinstateSignupAPI,
  rejectSignup as rejectSignupAPI,
  reopenSignups as reopenSignupsAPI,
  restartTournament as restartTournamentAPI,
  setEventStaff as setEventStaffAPI,
  signupForEvent,
  startRollCall as startRollCallAPI,
  startTournament as startTournamentAPI,
  subscribeToRepeater,
  unconfirmSignup as unconfirmSignupAPI,
  unsubscribeFromRepeater,
  updateEvent as updateEventAPI,
  updateEventRepeater as updateEventRepeaterAPI,
  updateOrgEventDefaults,
} from '~/components/api/api';
import type { EventSignupType, EventType } from '~/components/events/schemas';
import type {
  PendingSignupAction,
  SignupAction,
} from '~/components/events/signupOptimistic';
import {
  isSignupAction,
  overlayPendingSignups,
  replaceSignup,
  signupIdOf,
} from '~/components/events/signupOptimistic';
import type { GameTypeValue } from '~/components/game/constants';
import type { UserType } from '~/components/user/types';
import { useOrgStore } from '~/store/orgStore';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useUserStore } from '~/store/userStore';

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

export function useSignupMutation(eventId: number) {
  const queryClient = useQueryClient();
  // Use a Zustand selector so the hook reactively tracks user changes.
  const currentUserPk = useUserStore((s) => s.currentUser?.pk ?? null);

  return useMutation({
    mutationFn: (body: SignupBody) => signupForEvent(eventId, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['event', eventId] });
      queryClient.invalidateQueries({ queryKey: ['event-signups', eventId] });
      queryClient.invalidateQueries({
        queryKey: ['event-lobby-password', eventId],
      });
      if (currentUserPk != null) {
        // Match useUserDotaProfile's queryKey shape: ['user-dota-profile', userPk, orgId].
        // We don't have orgId in scope here, so invalidate the prefix — TanStack
        // Query treats this as "match any orgId for this user."
        queryClient.invalidateQueries({
          queryKey: ['user-dota-profile', currentUserPk],
        });
      }
      useOrgStore.getState().clearOrgUsers();
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
    completeEvent: useMutation({
      mutationFn: () => completeEventAPI(eventId),
      onSuccess: (data) => {
        queryClient.setQueryData(['event', eventId], data);
        queryClient.invalidateQueries({ queryKey: ['events'] });
        queryClient.invalidateQueries({
          queryKey: ['org-contributions', data.organization],
        });
      },
    }),
    setEventStaff: useMutation({
      mutationFn: (payload: EventStaffPayload) =>
        setEventStaffAPI(eventId, payload),
      onSuccess: (data) => {
        queryClient.setQueryData(['event', eventId], data);
        queryClient.invalidateQueries({
          queryKey: ['org-contributions', data.organization],
        });
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
      queryClient.invalidateQueries({
        queryKey: ['events', { organization: organizationId }],
      });
    },
  });
}

export function useCreateEventRepeaterMutation(organizationId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<EventRepeaterType>) =>
      createEventRepeaterAPI(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['events', { organization: organizationId }],
      });
      queryClient.invalidateQueries({
        queryKey: ['event-repeaters', { organization: organizationId }],
      });
    },
  });
}

export function useUpdateEventRepeaterMutation(repeaterId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<EventRepeaterType>) =>
      updateEventRepeaterAPI(repeaterId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['event-repeaters'] });
      queryClient.invalidateQueries({ queryKey: ['events'] });
      // The series cascade may have changed its events' passwords.
      queryClient.invalidateQueries({
        queryKey: ['repeater-lobby-password', repeaterId],
      });
      queryClient.invalidateQueries({ queryKey: ['event-lobby-password'] });
    },
  });
}

export function useUpdateEventMutation(eventId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: EventWritePayload) =>
      updateEventAPI(eventId, payload),
    onSuccess: (data) => {
      queryClient.setQueryData(['event', eventId], data);
      queryClient.invalidateQueries({ queryKey: ['events'] });
      // The Activity Log + Task Schedule panels poll on their own
      // cadences; invalidate them here so reminder-timing edits surface
      // immediately instead of after the next 15s poll.
      queryClient.invalidateQueries({ queryKey: ['event-discord', eventId] });
      queryClient.invalidateQueries({
        queryKey: ['event-task-schedule', eventId],
      });
      queryClient.invalidateQueries({
        queryKey: ['event-lobby-password', eventId],
      });
    },
  });
}

/** Signup management mutations (approve, reject, confirm, cancel). */
export const signupActionKey = (eventId: number) =>
  ['signup-action', eventId] as const;

/**
 * Staff actions on individual signups. Rows update straight away: pending
 * actions are drawn over the list by `useOptimisticEventSignups`, each
 * success writes the server's row into the cache, and the list, event and
 * lobby password refetch once the last in-flight action settles. A failed
 * action simply stops being drawn, which rolls the row back.
 */
export function useSignupActionMutations(eventId: number) {
  const queryClient = useQueryClient();
  const signupsKey = ['event-signups', eventId];

  const options = <TVars>(
    action: SignupAction,
    mutationFn: (vars: TVars) => Promise<EventSignupType>,
  ) => ({
    mutationKey: [...signupActionKey(eventId), action],
    mutationFn,
    onMutate: () => queryClient.cancelQueries({ queryKey: signupsKey }),
    onSuccess: (updated: EventSignupType) => {
      queryClient.setQueryData<EventSignupType[]>(signupsKey, (old) =>
        old ? replaceSignup(old, updated) : old,
      );
    },
    onSettled: () => {
      // This mutation still counts itself, so 1 means it is the last one.
      if (queryClient.isMutating({ mutationKey: signupActionKey(eventId) }) > 1)
        return;
      queryClient.invalidateQueries({ queryKey: signupsKey });
      queryClient.invalidateQueries({ queryKey: ['event', eventId] });
      queryClient.invalidateQueries({
        queryKey: ['event-lobby-password', eventId],
      });
    },
  });

  return {
    approve: useMutation(
      options('approve', ({ id, mmr }: { id: number; mmr?: number }) =>
        approveSignupAPI(id, mmr),
      ),
    ),
    reject: useMutation(options('reject', (id: number) => rejectSignupAPI(id))),
    confirm: useMutation(
      options('confirm', (id: number) => confirmSignupAPI(id)),
    ),
    cancel: useMutation(options('cancel', (id: number) => cancelSignupAPI(id))),
    unconfirm: useMutation(
      options('unconfirm', (id: number) => unconfirmSignupAPI(id)),
    ),
    demote: useMutation(options('demote', (id: number) => demoteSignupAPI(id))),
    reinstate: useMutation(
      options('reinstate', (id: number) => reinstateSignupAPI(id)),
    ),
  };
}

/** In-flight signup actions for an event, oldest first. */
export function usePendingSignupActions(
  eventId: number | null,
): PendingSignupAction[] {
  const entries = useMutationState({
    filters: {
      mutationKey: signupActionKey(eventId ?? 0),
      status: 'pending',
    },
    select: (mutation) => ({
      action: mutation.options.mutationKey?.[2],
      id: signupIdOf(mutation.state.variables),
      submittedAt: mutation.state.submittedAt,
    }),
  });
  return useMemo(
    () =>
      entries
        .filter(
          (e): e is { action: SignupAction; id: number; submittedAt: number } =>
            isSignupAction(e.action) && e.id !== null,
        )
        .sort((a, b) => a.submittedAt - b.submittedAt)
        .map(({ action, id }) => ({ action, id })),
    [entries],
  );
}

/**
 * Signups with in-flight staff actions already applied, plus the ids of
 * rows that still have a request outstanding.
 */
export function useOptimisticEventSignups(
  eventId: number | null,
  eventState: string | undefined,
) {
  const query = useEventSignups(eventId);
  const pending = usePendingSignupActions(eventId);
  const server = query.data;
  const signups = useMemo(
    () => overlayPendingSignups(server ?? EMPTY_SIGNUPS, pending, eventState),
    [server, pending, eventState],
  );
  const pendingIds = useMemo(
    () => new Set(pending.map((p) => p.id)),
    [pending],
  );
  return { ...query, signups, pendingIds };
}

const EMPTY_SIGNUPS: EventSignupType[] = [];

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
      queryClient.invalidateQueries({
        queryKey: ['org-event-defaults', orgId],
      });
    },
  });
}

/**
 * Upsert signup user data into the entity adapter cache.
 * Call this after fetching signups to ensure all signup users are in the cache.
 */
export function useEventSignupUsers(
  signups: EventSignupType[] | undefined,
  /**
   * Optional event organization id. When provided, each user's org-scoped
   * cache slot is hydrated with the signup's org MMR + `org_user_pk` so
   * `<UserStrip organizationId={...} />` can show the right MMR badge
   * without a second fetch.
   */
  eventOrgId?: number | null,
  /** The event's game: `org_user_mmr` is filed under it (Dota 2 if omitted). */
  gameType?: GameTypeValue,
) {
  useEffect(() => {
    if (!signups) return;
    const users: (UserType & { pk: number })[] = [];
    for (const s of signups) {
      if (!s.user_data) continue;
      const base = { ...s.user_data } as UserType & { pk: number };
      if (eventOrgId && s.org_user_pk != null && s.org_user_mmr != null) {
        base.orgUserPk = s.org_user_pk;
        base.mmr = s.org_user_mmr;
        if (gameType != null) base.mmr_game_type = gameType;
        if (s.org_user_game_mmrs) base.game_mmrs = s.org_user_game_mmrs;
      }
      users.push(base);
    }
    if (users.length > 0) {
      useUserCacheStore
        .getState()
        .upsert(users, eventOrgId ? { orgId: eventOrgId } : undefined);
    }
  }, [signups, eventOrgId, gameType]);
}
