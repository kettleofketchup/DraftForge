export function canSeeEventOpsNotices(
  event:
    | { user_is_event_operator?: boolean; user_can_manage?: boolean }
    | null
    | undefined,
): boolean {
  return event?.user_is_event_operator ?? event?.user_can_manage ?? false;
}
