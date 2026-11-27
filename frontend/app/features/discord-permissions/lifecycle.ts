import {
  hashKey,
  matchQuery,
  type Query,
  type QueryClient,
  type QueryFilters,
  type QueryKey,
} from '@tanstack/react-query';
import { discordPermissionKeys } from './queryKeys';

type Generation = {
  value: number;
  query: Query;
  controllers: Set<AbortController>;
};
const generations = new WeakMap<QueryClient, Map<string, Generation>>();
function registry(client: QueryClient): Map<string, Generation> {
  let entries = generations.get(client);
  if (!entries) {
    entries = new Map();
    generations.set(client, entries);
  }
  return entries;
}

export function beginPermissionRefresh(client: QueryClient, key: QueryKey) {
  const entries = registry(client);
  const hash = hashKey(key);
  let entry = entries.get(hash);
  const query = client.getQueryCache().build(client, { queryKey: key });
  if (!entry) {
    entry = { value: 0, query, controllers: new Set() };
    entries.set(hash, entry);
  }
  entry.query = query;
  const generation = entry.value;
  const controller = new AbortController();
  entry.controllers.add(controller);
  return {
    signal: controller.signal,
    abort: () => controller.abort(),
    isCurrent: () => !controller.signal.aborted && entry.value === generation,
    finish: () => {
      entry.controllers.delete(controller);
    },
  };
}

export async function invalidatePermissionChecks(
  client: QueryClient,
  filters: QueryFilters,
  mode: 'reset' | 'remove',
): Promise<void> {
  const restricted: QueryFilters = {
    ...filters,
    predicate: (query) =>
      query.queryKey[0] === discordPermissionKeys.all[0] &&
      (!filters.predicate || filters.predicate(query)),
  };
  for (const entry of registry(client).values()) {
    if (!matchQuery(restricted, entry.query)) continue;
    entry.value += 1;
    for (const controller of entry.controllers) controller.abort();
  }
  await client.cancelQueries(restricted);
  if (mode === 'reset') await client.resetQueries(restricted);
  else client.removeQueries(restricted);
}
