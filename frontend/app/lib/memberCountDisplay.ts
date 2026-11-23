export interface MemberCountInput {
  entityId: number | undefined;
  loadedForId: number | null | undefined;
  loading: boolean;
  loadedCount: number;
  fallbackCount: number | null | undefined;
}

// Loaded member list wins (it reflects adds/removes); otherwise the detail's users_count.
export function memberCountDisplay(input: MemberCountInput): number | '...' {
  if (!input.loading && input.loadedForId === input.entityId) {
    return input.loadedCount;
  }
  return input.fallbackCount ?? '...';
}
