import type { QueryClient } from '@tanstack/react-query';
import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useMutationState,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import { useEffect, useMemo } from 'react';

import type {
  EventRepeaterListItem,
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
  deleteEventRepeater as deleteEventRepeaterAPI,
  demoteSignup as demoteSignupAPI,
  getEvent,
  getEventRepeater,
  getEventRepeaters,
  getEvents,
  getEventSignupHistory,
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
import { organizationQueryKey } from '~/components/organization/hooks/useOrganization';
import { orgUsersQueryKey } from '~/components/organization/hooks/useOrgUsersQuery';
import type { UserType } from '~/components/user/types';
import {
  invalidateConductQueries,
  invalidateOrgContributionQueries,
} from '~/features/org-features/queryKeys';
import { nextCursor } from '~/hooks/useTournamentList';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useUserStore } from '~/store/userStore';

/** Lists filter and sort on state and signup counts, so refresh them all. */
export async function invalidateEventLists(
  queryClient: QueryClient,
): Promise<void> {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ['events'] }),
    queryClient.invalidateQueries({ queryKey: ['repeater-events'] }),
  ]);
}

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

export type SignupHistoryFilters = { user?: number; action?: string };

export const signupHistoryKey = (
  eventId: number,
  filters: SignupHistoryFilters,
) => ['event-signup-history', eventId, filters] as const;

export function useSignupHistory(
  eventId: number | undefined,
  filters: SignupHistoryFilters,
  enabled: boolean,
) {
  const key: SignupHistoryFilters = {
    ...(filters.user !== undefined && { user: filters.user }),
    ...(filters.action !== undefined && { action: filters.action }),
  };
  return useInfiniteQuery({
    queryKey: signupHistoryKey(eventId ?? 0, key),
    queryFn: ({ pageParam }) =>
      getEventSignupHistory(eventId!, {
        ...key,
        ...(pageParam !== null && { cursor: pageParam }),
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => nextCursor(last.next),
    enabled: !!eventId && enabled,
    staleTime: 15_000,
    placeholderData: keepPreviousData,
  });
}

export function invalidateSignupHistory(
  queryClient: QueryClient,
  eventId: number,
): void {
  void queryClient.invalidateQueries({
    queryKey: ['event-signup-history', eventId],
  });
}

export function removeSignupHistoryQueries(
  queryClient: QueryClient,
  eventId: number,
): void {
  queryClient.removeQueries({ queryKey: ['event-signup-history', eventId] });
}

/** The server fills an empty `steam_account_id` from the signup; mirror it. */
export function syncCurrentUserFriendId(body: SignupBody): void {
  const submitted = String(body.profile?.steam_account_id ?? '').trim();
  const { currentUser, patchCurrentUser } = useUserStore.getState();
  if (!submitted || !currentUser || currentUser.steam_account_id != null) {
    return;
  }
  patchCurrentUser({ steam_account_id: Number(submitted) });
}

export function useSignupMutation(eventId: number) {
  const queryClient = useQueryClient();
  // Use a Zustand selector so the hook reactively tracks user changes.
  const currentUserPk = useUserStore((s) => s.currentUser?.pk ?? null);

  return useMutation({
    mutationFn: (body: SignupBody) => signupForEvent(eventId, body),
    onSuccess: (_signup, body) => {
      syncCurrentUserFriendId(body);
      queryClient.invalidateQueries({ queryKey: ['event', eventId] });
      queryClient.invalidateQueries({ queryKey: ['event-signups', eventId] });
      void invalidateEventLists(queryClient);
      queryClient.invalidateQueries({
        queryKey: ['event-lobby-password', eventId],
      });
      invalidateSignupHistory(queryClient, eventId);
      if (currentUserPk != null) {
        // Match useUserDotaProfile's queryKey shape: ['user-dota-profile', userPk, orgId].
        // We don't have orgId in scope here, so invalidate the prefix — TanStack
        // Query treats this as "match any orgId for this user."
        queryClient.invalidateQueries({
          queryKey: ['user-dota-profile', currentUserPk],
        });
      }
      const orgId = queryClient.getQueryData<EventType>([
        'event',
        eventId,
      ])?.organization;
      if (orgId) {
        void queryClient.invalidateQueries({
          queryKey: orgUsersQueryKey(orgId),
        });
      }
      void invalidateConductQueries(queryClient, orgId);
    },
  });
}

export function useEventActionMutation(eventId: number) {
  const queryClient = useQueryClient();
  return {
    openSignups: useMutation({
      mutationFn: () => openSignupsAPI(eventId),
      onSuccess: (data) => {
        queryClient.setQueryData(['event', eventId], data);
        void invalidateEventLists(queryClient);
        invalidateSignupHistory(queryClient, eventId);
      },
    }),
    startRollCall: useMutation({
      mutationFn: () => startRollCallAPI(eventId),
      onSuccess: (data) => {
        queryClient.setQueryData(['event', eventId], data);
        void invalidateEventLists(queryClient);
        invalidateSignupHistory(queryClient, eventId);
        void invalidateConductQueries(queryClient, data.organization);
      },
    }),
    reopenSignups: useMutation({
      // Corrective transition; no optimistic update intentionally.
      mutationFn: () => reopenSignupsAPI(eventId),
      onSuccess: (data) => {
        queryClient.setQueryData(['event', eventId], data);
        void invalidateEventLists(queryClient);
        invalidateSignupHistory(queryClient, eventId);
        void invalidateConductQueries(queryClient, data.organization);
      },
    }),
    startTournament: useMutation({
      mutationFn: () => startTournamentAPI(eventId),
      onSuccess: (data) => {
        queryClient.setQueryData(['event', eventId], data);
        void invalidateEventLists(queryClient);
        invalidateSignupHistory(queryClient, eventId);
        void invalidateConductQueries(queryClient, data.organization);
      },
    }),
    cancelEvent: useMutation({
      mutationFn: () => cancelEventAPI(eventId),
      onSuccess: (data) => {
        queryClient.setQueryData(['event', eventId], data);
        void invalidateEventLists(queryClient);
        invalidateSignupHistory(queryClient, eventId);
        void invalidateConductQueries(queryClient, data.organization);
      },
    }),
    deleteEvent: useMutation({
      mutationFn: () => deleteEventAPI(eventId),
      onSuccess: () => {
        void invalidateEventLists(queryClient);
        queryClient.removeQueries({ queryKey: ['event', eventId] });
        removeSignupHistoryQueries(queryClient, eventId);
        void invalidateConductQueries(queryClient);
      },
    }),
    restartTournament: useMutation({
      mutationFn: () => restartTournamentAPI(eventId),
      onSuccess: (data) => {
        queryClient.setQueryData(['event', eventId], data);
        void invalidateEventLists(queryClient);
        invalidateSignupHistory(queryClient, eventId);
        void invalidateConductQueries(queryClient, data.organization);
      },
    }),
    completeEvent: useMutation({
      mutationFn: () => completeEventAPI(eventId),
      onSuccess: (data) => {
        queryClient.setQueryData(['event', eventId], data);
        void invalidateEventLists(queryClient);
        invalidateSignupHistory(queryClient, eventId);
        void invalidateOrgContributionQueries(queryClient, data.organization);
        void invalidateConductQueries(queryClient, data.organization);
      },
    }),
    setEventStaff: useMutation({
      mutationFn: (payload: EventStaffPayload) =>
        setEventStaffAPI(eventId, payload),
      onSuccess: (data) => {
        queryClient.setQueryData(['event', eventId], data);
        invalidateSignupHistory(queryClient, eventId);
        void invalidateOrgContributionQueries(queryClient, data.organization);
        void queryClient.invalidateQueries({
          queryKey: organizationQueryKey(data.organization),
        });
      },
    }),
  };
}

export const repeaterKeys = {
  lists: () => ['event-repeaters'] as const,
  list: (params?: { organization?: number }) =>
    ['event-repeaters', params] as const,
  detail: (id: number | null) => ['repeater', id] as const,
  subscribers: (id: number) => ['repeater-subscribers', id] as const,
  events: (id: number | null) => ['repeater-events', id] as const,
};

export function useEventRepeaters(params?: { organization?: number }) {
  return useQuery<EventRepeaterListItem[]>({
    queryKey: repeaterKeys.list(params),
    queryFn: () => getEventRepeaters(params),
  });
}

export function useEventRepeater(id: number | null) {
  return useQuery<EventRepeaterType>({
    queryKey: repeaterKeys.detail(id),
    queryFn: () => getEventRepeater(id as number),
    enabled: id !== null,
  });
}

export function useCreateEventMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      payload,
      openSignups = false,
    }: {
      payload: EventWritePayload;
      openSignups?: boolean;
    }) => createEventAPI(payload, openSignups),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['events'] });
      queryClient.invalidateQueries({ queryKey: repeaterKeys.lists() });
    },
  });
}

export function useCreateEventRepeaterMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<EventRepeaterType>) =>
      createEventRepeaterAPI(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['events'] });
      queryClient.invalidateQueries({ queryKey: repeaterKeys.lists() });
    },
  });
}

export function useUpdateEventRepeaterMutation(repeaterId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<EventRepeaterType>) =>
      updateEventRepeaterAPI(repeaterId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: repeaterKeys.lists() });
      queryClient.invalidateQueries({
        queryKey: repeaterKeys.detail(repeaterId),
      });
      queryClient.invalidateQueries({ queryKey: ['events'] });
      // The series cascade may have changed its events' passwords.
      queryClient.invalidateQueries({
        queryKey: ['repeater-lobby-password', repeaterId],
      });
      queryClient.invalidateQueries({ queryKey: ['event-lobby-password'] });
    },
  });
}

export function useDeleteEventRepeaterMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (repeater: { id: number; organization: number }) =>
      deleteEventRepeaterAPI(repeater.id),
    onSuccess: (_data, repeater) => {
      queryClient.removeQueries({ queryKey: repeaterKeys.detail(repeater.id) });
      queryClient.removeQueries({ queryKey: repeaterKeys.events(repeater.id) });
      queryClient.invalidateQueries({ queryKey: ['events'] });
      queryClient.invalidateQueries({ queryKey: repeaterKeys.lists() });
      void invalidateConductQueries(queryClient, repeater.organization);
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
      void invalidateConductQueries(queryClient, data.organization);
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
      void invalidateEventLists(queryClient);
      invalidateSignupHistory(queryClient, eventId);
      queryClient.invalidateQueries({
        queryKey: ['event-lobby-password', eventId],
      });
      void invalidateConductQueries(
        queryClient,
        queryClient.getQueryData<EventType>(['event', eventId])?.organization,
      );
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
  const onSuccess = (_data: void, repeaterId: number) => {
    queryClient.invalidateQueries({ queryKey: repeaterKeys.lists() });
    queryClient.invalidateQueries({
      queryKey: repeaterKeys.detail(repeaterId),
    });
    queryClient.invalidateQueries({
      queryKey: repeaterKeys.subscribers(repeaterId),
    });
  };
  return {
    subscribe: useMutation({
      mutationFn: (repeaterId: number) => subscribeToRepeater(repeaterId),
      onSuccess,
    }),
    unsubscribe: useMutation({
      mutationFn: (repeaterId: number) => unsubscribeFromRepeater(repeaterId),
      onSuccess,
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
  eventOrgId: number | null | undefined,
  /** The event's game: `org_user_mmr` is filed under it. */
  gameType: GameTypeValue,
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
        base.mmr_game_type = gameType;
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
