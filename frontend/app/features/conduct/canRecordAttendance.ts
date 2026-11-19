export function canRecordAttendance(
  event: { user_can_manage?: boolean | null } | null | undefined,
  eventOrg: { features?: readonly string[] | null } | null | undefined,
): boolean {
  return (
    event?.user_can_manage === true &&
    (eventOrg?.features ?? []).includes('conduct')
  );
}
