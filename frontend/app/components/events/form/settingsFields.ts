import type { EventFormTabValue } from './tabs';

export interface SettingsFieldMeta {
  label: string;
  description?: string;
  /** Extra search terms that appear in neither the label nor the description. */
  keywords?: readonly string[];
}

export type SectionFieldMeta = Record<
  EventFormTabValue,
  Record<string, SettingsFieldMeta>
>;

export const PROFILE_REMINDER_DESCRIPTION: string =
  'Posts a reminder in the announcement channel asking signed-up members to complete the profile details this event requires (such as Friend ID) before the event. Needs an announcement channel.';

/**
 * Every event-form field, under the section that renders it by default, with the
 * text the settings search matches. A modal that renders a field elsewhere (signup
 * rules sit on the Event section of the series and defaults forms) is resolved from
 * the DOM at runtime; this map is the fallback and the source for unmounted panels.
 */
export const EVENT_SECTION_FIELDS: SectionFieldMeta = {
  event: {
    name: { label: 'Event Name', keywords: ['title'] },
    description: { label: 'Description' },
    is_recurring: {
      label: 'Recurring Event (Event Repeater)',
      description: 'Automatically generates events on a schedule',
      keywords: ['series', 'repeat', 'weekly'],
    },
    scheduled_at: {
      label: 'Scheduled Date & Time',
      keywords: ['start', 'date', 'when'],
    },
    event_ends_at: { label: 'End Date & Time', keywords: ['finish'] },
    signup_open_mode: {
      label: 'When to open signups',
      keywords: [
        'registration',
        'open immediately',
        'open manually',
        'schedule signups',
      ],
    },
    signups_open_hours_before: {
      label: 'Days before event',
      description: 'Signups open this many days before the scheduled start',
      keywords: ['hours before'],
    },
    timezone: { label: 'Timezone', keywords: ['time zone', 'tz', 'utc'] },
    frequency: {
      label: 'Frequency',
      keywords: ['daily', 'weekly', 'monthly', 'repeat'],
    },
    day_of_week: { label: 'Day of Week', keywords: ['weekday'] },
    time_of_day: { label: 'Time', keywords: ['start time'] },
    starts_at: { label: 'Starts', keywords: ['start date', 'first event'] },
    ends_at: { label: 'Ends', keywords: ['end date', 'last event'] },
    generate_days_ahead: {
      label: 'Generate Days Ahead',
      keywords: ['create in advance', 'schedule'],
    },
    max_players: { label: 'Max Players', keywords: ['limit', 'capacity'] },
    auto_approve: { label: 'Auto-approve signups' },
  },
  tournament: {
    tournament_name: { label: 'Tournament Name' },
    tournament_league: { label: 'League' },
    tournament_type: {
      label: 'Bracket type',
      keywords: ['format', 'elimination', 'swiss', 'round robin'],
    },
    game_type: { label: 'Game', keywords: ['dota'] },
    people_per_team: {
      label: 'People Per Team',
      keywords: ['team size', 'players'],
    },
    number_of_teams: { label: 'Max Teams', keywords: ['unlimited'] },
    draft_type: {
      label: 'Draft type',
      description: 'How captains build their teams',
      keywords: ['snake', 'shuffle', 'captains'],
    },
    draft_timer_enabled: {
      label: 'Team draft timer',
      description:
        'Captains get a countdown for each player pick. Unchecked, they pick without a time limit.',
      keywords: ['player pick timer'],
    },
    draft_grace_time_s: {
      label: 'Grace time (seconds)',
      description: 'Resets every pick',
      keywords: ['team draft timer'],
    },
    draft_reserve_time_s: {
      label: 'Reserve time (seconds)',
      description: 'Bank each captain draws on after grace runs out',
      keywords: ['team draft timer'],
    },
    draft_timeout_action: {
      label: 'On timeout',
      description: 'When grace and reserve both run out',
      keywords: ['auto pick', 'random pick'],
    },
    hero_timer_enabled: {
      label: 'Hero draft timer',
      description:
        'Each team gets a countdown for hero picks and bans. Unchecked, there is no time limit.',
      keywords: ['ban timer'],
    },
    hero_grace_time_s: {
      label: 'Grace per pick (seconds)',
      description: 'Resets every pick or ban',
      keywords: ['hero draft timer'],
    },
    hero_reserve_time_s: {
      label: 'Reserve per team (seconds)',
      description: 'Shared bank for the whole hero draft',
      keywords: ['hero draft timer'],
    },
  },
  lobby: {
    game_mode: {
      label: 'Game Mode',
      keywords: ["captain's mode", 'turbo', 'normal', 'custom'],
    },
    custom_game_name: { label: 'Custom Game Name' },
    captains_draft_time: {
      label: 'Draft Time (seconds)',
      description: "Seconds per pick in Captain's Mode draft",
    },
    lobby_steam_league_id: {
      label: 'Steam League ID',
      keywords: ['ticket', 'dota league'],
    },
    dota_lobby_mode: {
      label: 'Hosted lobbies',
      description:
        "A lobby bot creates each match's in-game lobby and invites the players.",
      keywords: ['bot', 'automatic lobby'],
    },
    dota_lobby_launch: {
      label: 'Match start',
      keywords: ['launch', 'ready'],
    },
    dota_lobby_region: {
      label: 'Server region',
      description: 'A region name the lobby service knows, such as us_east.',
      keywords: ['location'],
    },
    discord_send_lobby_info: {
      label: 'Send lobby info',
      description:
        'DM players the in-game lobby name, password and side when their lobby is created',
    },
    dota_lobby_password_mode: {
      label: 'Password',
      keywords: ['lobby password', 'random', 'fixed'],
    },
    dota_lobby_password: { label: 'Lobby password' },
    dota_lobby_password_saved: { label: 'Saved lobby password' },
  },
  approval: {
    allow_active_mmr: {
      label: 'Active MMR Players',
      description: 'Players with a current ranked medal',
    },
    discord_require_rank_screenshot: {
      label: 'Require MMR screenshot',
      description: 'Player must upload a screenshot before signup completes',
      keywords: ['rank screenshot', 'proof'],
    },
    min_mmr: { label: 'Minimum MMR', keywords: ['rank', 'skill'] },
    allow_previous_rank: {
      label: 'Previously Ranked Players',
      description: 'Players who had a rank but are no longer active',
    },
    allow_battlecup_rating: {
      label: 'Battle Cup Players (Never Ranked)',
      description:
        'Players who have never played ranked — use battle cup tier for estimation',
    },
    discord_require_battlecup_screenshot: {
      label: 'Require battle cup screenshot',
      description:
        'Player must upload a screenshot of their battle cup ticket tier',
    },
    require_steam_id: {
      label: 'Require Friend ID',
      description: 'Player must provide their Steam Friend ID',
      keywords: ['steam'],
    },
    require_mmr_verified: {
      label: 'Require verified MMR',
      description: 'Player must have admin-verified MMR on their org profile',
    },
    require_profile_complete: {
      label: 'Require complete profile',
      description: 'Player must have nickname, Steam ID, and Discord linked',
    },
    allow_user_signups: {
      label: 'Members can sign themselves up',
      description: 'When off, only organizers can add players.',
      keywords: ['self signup'],
    },
    line_withdraw_forfeits: {
      label: 'Withdrawing gives up your place',
      description:
        'A member who withdraws, declines or is rejected and signs up again goes to the back of the line. When off, they get their old place back.',
      keywords: [
        'line',
        'line order',
        'back of the line',
        'waitlist',
        'withdraw',
      ],
    },
    line_switch_restamps: {
      label: 'Switching Main/Maybe gives up your place',
      description:
        'Moving between Main and Maybe sends the signup to the back of the line. When off, it keeps its place.',
      keywords: [
        'line',
        'line order',
        'back of the line',
        'maybe',
        'tentative',
      ],
    },
  },
  ready: {
    roll_call_enabled: {
      label: 'Mandatory RSVP Confirmation',
      description: 'Every rostered member must confirm before teams are made.',
      keywords: ['roll call', 'ready check', 'rsvp', 'check in'],
    },
    auto_confirm: {
      label: 'Auto-confirm signups',
      description: 'Signups are marked as confirmed without asking the member',
    },
    roll_call_mode: {
      label: 'Mode',
      keywords: ['roll-call mode', 'staff-verified', 'automatic'],
    },
    ready_check_scope: {
      label: 'Who is asked',
      keywords: ['main roster', 'fill list'],
    },
    ready_check_open_minutes: {
      label: 'Opens (minutes)',
      description:
        'Minutes before start. Each asked member gets a Ready button by DM.',
      keywords: ['ready check opens'],
    },
    ready_check_escalation_minutes: {
      label: 'Nudge unconfirmed members by DM (minutes)',
      description:
        'Minutes before start (0 = off). Staff also get the unconfirmed count as an ops notice.',
      keywords: ['reminder', 'escalation'],
    },
    ready_check_close_minutes: {
      label: 'Closes (minutes)',
      description: 'Minutes before start',
      keywords: ['ready check closes'],
    },
    ready_check_chase_minutes: {
      label: 'Ops notice per unconfirmed member (minutes)',
      description:
        'Minutes before close. Shown to org and league staff, the event host and helpers on the event page, and sent wherever the org routes ops notices.',
      keywords: ['ops chase', 'alert staff'],
    },
    ready_check_min_completion_pct: {
      label: 'Minimum confirmed (%)',
      keywords: ['completion', 'percent'],
    },
    ready_check_low_completion_action: {
      label: 'If too few confirm',
      description:
        'Non-binding and held checks raise an urgent ops notice for staff.',
      keywords: ['non-binding', 'hold drops', 'drop unconfirmed'],
    },
    ready_check_notify_on_signup: {
      label: 'DM members on their first sign-up that confirmation is mandatory',
      description:
        'If their DMs are closed they get a reply only they can see, and staff get an ops notice.',
    },
    ready_check_drop_notice: {
      label: 'DM members who are dropped',
      description:
        'Members can turn this off under roster changes in their notification settings.',
      keywords: ['drop notice'],
    },
    event_voice_channel_id: {
      label: 'Event voice channel',
      keywords: ['discord voice', 'call'],
    },
    voice_presence_confirms: {
      label: 'Count presence in the voice channel as ready',
    },
    start_cull_enabled: {
      label: 'Remove members absent from the voice channel after start',
      description:
        'Removed members get the drop notice DM. If the bot cannot see the voice channel, nobody is removed and staff get an ops notice.',
      keywords: ['start cull', 'no-show'],
    },
    start_cull_minutes_after: {
      label: 'Cull after (minutes)',
      description: 'Minutes after start',
    },
    post_cull_fill_mode: {
      label: 'After the cull, fill open seats by',
      description: 'Members moved into a seat get a promotion DM.',
      keywords: ['line order', 'arrival'],
    },
  },
  discord: {
    discord_create_event: {
      label: 'Create Discord scheduled event',
      description:
        'Automatically creates a scheduled event in your Discord server',
    },
    discord_sync_signups: {
      label: 'Synchronize signups',
      description: 'Keep website and Discord event signups in sync',
    },
    discord_mark_interested: {
      label: 'Mark signups as interested',
      description:
        'Players who sign up will be marked as interested on the Discord event',
    },
    discord_event_title: {
      label: 'Event title',
      description:
        'Custom title for the Discord event. If blank, the event name is used.',
    },
    discord_event_description: {
      label: 'Event description',
      description:
        'Shown as the main description of the Discord scheduled event',
    },
    discord_event_info: {
      label: 'Additional info',
      description: 'Extra information appended to the Discord event details',
    },
    discord_signup_reminder: {
      label: 'Send signup reminder',
      description:
        "DM series subscribers who haven't signed up yet, before the event starts",
    },
    discord_signup_reminder_hours: {
      label: 'Signup reminder: hours before event',
    },
    discord_profile_reminder: {
      label: 'Profile update reminder',
      description: PROFILE_REMINDER_DESCRIPTION,
    },
    discord_profile_reminder_hours: { label: 'Profile reminder: when to send' },
    discord_confirm_attendance: {
      label: 'Post attendance reminder in Discord',
      description:
        "Posts a reminder in the announcement channel before the event. It doesn't track replies; use the ready check to require confirmation.",
    },
    discord_confirm_attendance_hours: {
      label: 'Attendance reminder: when to send',
    },
    discord_post_signups: {
      label: 'Post event signup embed',
      description:
        'Post an embed to a channel where users can react to sign up',
    },
    discord_post_signups_channel_id: {
      label: 'Signup channel',
      description: 'Channel where the signup embed will be posted',
    },
    discord_signup_role_ids: {
      label: 'Mention roles in signup post',
      description: 'Discord role IDs to @mention in the signup post',
      keywords: ['ping'],
    },
    discord_start_mention: {
      label: 'Mention signed-up members before start',
      description:
        'Reply to the signup post with an @mention of every signed-up member shortly before the event starts',
      keywords: ['ping', 'reminder'],
    },
    discord_start_mention_minutes: {
      label: 'Start mention: when to send',
    },
    discord_start_mention_scope: {
      label: 'Who to mention',
      keywords: ['waitlist', 'main list'],
    },
    discord_announcement: {
      label: 'Pre-day announcement',
      description: 'Post an announcement in a channel before the event',
    },
    discord_announcement_channel_id: {
      label: 'Announcement channel',
      description:
        'Shared by the pre-day announcement, attendance reminder, profile reminder and series new-event posts.',
    },
    discord_announcement_hours: {
      label: 'Hours before event',
      description: 'How many hours before the event to post the announcement',
    },
    discord_announcement_role_ids: {
      label: 'Mention roles in announcement',
      description: 'Discord role IDs to @mention when announcement is posted',
      keywords: ['ping'],
    },
    discord_notify_new_events: {
      label: 'Post new events',
      description:
        'Post each new series event in the announcement channel when it is created',
      keywords: ['new event', 'channel', 'notify'],
    },
  },
};
