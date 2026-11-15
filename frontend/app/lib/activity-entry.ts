/** Discord launches the root URL configured in the Portal's URL mappings. */
export function activityEntryPath(
  pathname: string,
  search: string,
): string | null {
  if (pathname !== '/') return null;
  const params = new URLSearchParams(search);
  if (!params.has('frame_id') || !params.has('instance_id')) return null;
  return `/activity${search}`;
}
