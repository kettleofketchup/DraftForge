export interface LeagueTestIds {
  trigger: string;
  itemPrefix: string;
  search: string;
  clear: string;
}

export interface EventFieldTestIds {
  name: string;
  description: string;
  tournamentName: string;
  league: LeagueTestIds;
  game: string;
  peoplePerTeam: string;
  maxTeams: string;
  unlimited: string;
  bracket: string;
  draftType: string;
  scheduled: string;
  endsAt: string;
  timezone: string;
}

type EventFieldTestIdOverrides = Partial<
  Omit<EventFieldTestIds, 'league'> & { league: Partial<LeagueTestIds> }
>;

/** data-testids for the shared event fields, built from one dialog prefix. */
export function eventFieldTestIds(
  p: string,
  overrides: EventFieldTestIdOverrides = {},
): EventFieldTestIds {
  const { league, ...rest } = overrides;
  return {
    name: `${p}-name-input`,
    description: `${p}-description-input`,
    tournamentName: `${p}-tournament-name-input`,
    game: `${p}-game-select`,
    peoplePerTeam: `${p}-people-per-team-input`,
    maxTeams: `${p}-max-teams-input`,
    unlimited: `${p}-unlimited-checkbox`,
    bracket: `${p}-bracket-select`,
    draftType: `${p}-draft-select`,
    scheduled: `${p}-scheduled-input`,
    endsAt: `${p}-end-datetime-input`,
    timezone: `${p}-timezone-input`,
    ...rest,
    league: {
      trigger: `${p}-league-select`,
      itemPrefix: `${p}-league-option-`,
      search: `${p}-league-search`,
      clear: `${p}-league-clear`,
      ...league,
    },
  };
}

export const READY_CHECK_TEST_IDS = {
  section: 'ready-check-section',
  toggle: 'ready-check-toggle',
  settingsTrigger: 'ready-check-settings-trigger',
  mode: 'ready-check-mode',
  scope: 'ready-check-scope',
  open: 'ready-check-open-minutes',
  escalation: 'ready-check-escalation-minutes',
  close: 'ready-check-close-minutes',
  chase: 'ready-check-chase-minutes',
  chaseOff: 'ready-check-chase-off',
  minCompletion: 'ready-check-min-completion-pct',
  lowCompletionAction: 'ready-check-low-completion-action',
  notifyOnSignup: 'ready-check-notify-on-signup',
  dropNotice: 'ready-check-drop-notice',
  voiceTrigger: 'ready-check-voice-trigger',
  voiceChannel: 'ready-check-voice-channel',
  voiceConfirms: 'ready-check-voice-confirms',
  cullEnabled: 'ready-check-cull-enabled',
  cullMinutes: 'ready-check-cull-minutes',
  fillMode: 'ready-check-fill-mode',
  autoConfirm: 'ready-check-auto-confirm',
} as const;
