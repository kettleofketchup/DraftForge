const ACTION_LABELS: Record<string, string> = {
  set_captain: 'Set captain',
  set_deputy: 'Set deputy',
  mark_dropout: 'Marked dropout',
  restore_member: 'Restored',
  add_standin: 'Added stand-in',
  remove_standin: 'Removed stand-in',
  sub_in: 'Subbed in',
  rename: 'Renamed',
  legacy_patch: 'Edited (legacy)',
  system_succession: 'Automatic captain succession',
  empty_team_kept: 'Empty team kept',
  team_deleted: 'Team deleted',
  materialize: 'Materialized',
  replace_captain: 'Replace captain',
  set_placement: 'Set placement',
};

const VIA_LABELS: Record<string, string> = {
  web: 'Web',
  discord: 'Discord',
  api: 'API',
  system: 'System',
};

export const teamLogActionLabel = (action: string): string =>
  Object.hasOwn(ACTION_LABELS, action) ? ACTION_LABELS[action] : action;

export const teamLogViaLabel = (via: string): string =>
  Object.hasOwn(VIA_LABELS, via) ? VIA_LABELS[via] : via;
