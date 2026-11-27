import {
  hashKey,
  useQuery,
  useQueryClient,
  type QueryKey,
} from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useDebouncedValue } from '~/hooks/useDebouncedValue';
import { useUserStore } from '~/store/userStore';
import {
  getEventPermissionChecks,
  postEventPermissionChecks,
  postOrgPermissionChecks,
} from './api';
import { beginPermissionRefresh } from './lifecycle';
import { discordPermissionKeys, normalizeDescriptors } from './queryKeys';
import {
  isExpired,
  type CheckDescriptor,
  type PermissionCheckResult,
  type PermissionChecksResponse,
  type PermissionScope,
} from './schemas';

export type PermissionQuery = {
  results: Map<string, PermissionCheckResult>;
  state: 'idle' | 'checking' | 'ready' | 'error';
  error: unknown;
  refetch: () => Promise<unknown>;
  recheck: () => Promise<void>;
  isRechecking: boolean;
};
type Refresh = ReturnType<typeof beginPermissionRefresh>;
type Manual = {
  identity: string;
  handle: Refresh;
  loading: boolean;
  error: unknown;
  dataUpdateCount: number;
};

function usePermissionQuery({
  key,
  identity,
  enabled,
  pending,
  request,
}: {
  key: QueryKey;
  identity: string;
  enabled: boolean;
  pending: boolean;
  request: (
    refresh: boolean,
    signal: AbortSignal,
  ) => Promise<PermissionChecksResponse>;
}): PermissionQuery {
  const client = useQueryClient();
  const currentIdentity = useRef(identity);
  currentIdentity.current = identity;
  const active = useRef<Refresh | null>(null);
  const [manual, setManual] = useState<Manual | null>(null);
  const [, render] = useState(0);
  const query = useQuery({
    queryKey: key,
    queryFn: ({ signal }) => request(false, signal),
    enabled: enabled && !pending,
    refetchOnWindowFocus: true,
    notifyOnChangeProps: ['data', 'error', 'isFetching'],
    refetchInterval: 60_000,
    staleTime: 0,
    retry: false,
  });
  const keyHash = hashKey(key);
  useEffect(() => {
    const reassess = () => render((value) => value + 1);
    window.addEventListener('focus', reassess);
    document.addEventListener('visibilitychange', reassess);
    return () => {
      window.removeEventListener('focus', reassess);
      document.removeEventListener('visibilitychange', reassess);
    };
  }, []);
  useEffect(
    () => () => {
      active.current?.abort();
      active.current = null;
    },
    [identity],
  );
  useEffect(
    () =>
      client.getQueryCache().subscribe((event) => {
        if (event.type === 'removed' && event.query.queryHash === keyHash)
          render((v) => v + 1);
      }),
    [client, keyHash],
  );

  const visibleManual =
    manual?.identity === identity && manual.handle.isCurrent() ? manual : null;
  const dataUpdateCount = client.getQueryState(key)?.dataUpdateCount ?? 0;
  const error =
    (visibleManual?.dataUpdateCount === dataUpdateCount
      ? visibleManual.error
      : null) ?? query.error;
  const data = client.getQueryData(key) === query.data ? query.data : undefined;
  useEffect(() => {
    const now = Date.now();
    const expiries = (data?.checks ?? [])
      .flatMap((result) =>
        result.expires_at ? [Date.parse(result.expires_at)] : [],
      )
      .filter((time) => time > now);
    if (!expiries.length) return;
    const timer = setTimeout(
      () => render((v) => v + 1),
      Math.min(...expiries) - now,
    );
    return () => clearTimeout(timer);
  });

  const recheck = useCallback(async () => {
    if (!enabled || pending || active.current) return;
    const handle = beginPermissionRefresh(client, key);
    active.current = handle;
    const isCurrent = () =>
      handle.isCurrent() && currentIdentity.current === identity;
    handle.signal.addEventListener(
      'abort',
      () => {
        if (active.current === handle) active.current = null;
        setManual((value) => (value?.handle === handle ? null : value));
      },
      { once: true },
    );
    setManual({
      identity,
      handle,
      loading: true,
      error: null,
      dataUpdateCount,
    });
    try {
      await client.cancelQueries({ queryKey: key, exact: true });
      if (!isCurrent()) return;
      const response = await request(true, handle.signal);
      if (isCurrent()) {
        client.setQueryData(key, response);
        setManual({
          identity,
          handle,
          loading: false,
          error: null,
          dataUpdateCount,
        });
      }
    } catch (error) {
      if (isCurrent())
        setManual({
          identity,
          handle,
          loading: false,
          error,
          dataUpdateCount: client.getQueryState(key)?.dataUpdateCount ?? 0,
        });
    } finally {
      handle.finish();
      if (active.current === handle) active.current = null;
    }
  }, [client, keyHash, identity, enabled, pending, request]);

  const results = new Map<string, PermissionCheckResult>();
  if (enabled && !pending && !error && !visibleManual?.loading) {
    for (const result of data?.checks ?? []) {
      results.set(
        result.key,
        isExpired(result, new Date())
          ? { ...result, status: 'unknown', expired: true }
          : result,
      );
    }
  }
  return {
    results,
    state: !enabled
      ? 'idle'
      : pending || visibleManual?.loading
        ? 'checking'
        : error
          ? 'error'
          : data
            ? 'ready'
            : 'checking',
    error: enabled && !pending ? error : null,
    refetch: query.refetch,
    recheck,
    isRechecking: !!visibleManual?.loading,
  };
}

export function usePermissionPreview({
  scope,
  descriptors,
  enabled,
}: {
  scope: PermissionScope;
  descriptors: CheckDescriptor[];
  enabled: boolean;
}): PermissionQuery {
  const viewerPk = useUserStore((state) => state.currentUser?.pk ?? null);
  const serialized = JSON.stringify(normalizeDescriptors(descriptors));
  const stableDescriptors = useMemo<CheckDescriptor[]>(
    () => JSON.parse(serialized),
    [serialized],
  );
  const debounced = useDebouncedValue(stableDescriptors, 300);
  const pending = stableDescriptors !== debounced;
  const key = discordPermissionKeys.draft(viewerPk ?? 0, scope, debounced);
  const identity = hashKey(
    discordPermissionKeys.draft(viewerPk ?? 0, scope, stableDescriptors),
  );
  const id = scope.kind === 'org' ? scope.orgId : scope.eventId;
  return usePermissionQuery({
    key,
    identity,
    pending,
    enabled: enabled && !!viewerPk && !!id && descriptors.length > 0,
    request: (refresh, signal) =>
      scope.kind === 'org'
        ? postOrgPermissionChecks(
            scope.orgId,
            { checks: debounced, refresh },
            signal,
          )
        : postEventPermissionChecks(
            scope.eventId,
            { checks: debounced, refresh },
            signal,
          ),
  });
}

export function useSavedEventPermissions({
  eventId,
  guildId,
  enabled,
}: {
  eventId: number | null;
  guildId: string | null;
  enabled: boolean;
}): PermissionQuery {
  const viewerPk = useUserStore((state) => state.currentUser?.pk ?? null);
  const key = discordPermissionKeys.saved(viewerPk ?? 0, eventId ?? 0, guildId);
  return usePermissionQuery({
    key,
    identity: hashKey(key),
    pending: false,
    enabled: enabled && !!viewerPk && !!eventId,
    request: (refresh, signal) =>
      getEventPermissionChecks(eventId!, refresh, signal),
  });
}

export function useRecheckPermissions(): (
  query: PermissionQuery,
) => Promise<void> {
  return useCallback((query: PermissionQuery) => query.recheck(), []);
}
