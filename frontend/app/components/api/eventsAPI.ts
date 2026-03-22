import type { EventSignupType, EventType } from '~/components/events/schemas';
import axios from './axios';

export async function getEvents(params?: { organization?: number; state?: string }): Promise<EventType[]> {
  const sp = new URLSearchParams();
  if (params?.organization) sp.set('organization', String(params.organization));
  if (params?.state) sp.set('state', params.state);
  const q = sp.toString();
  const { data } = await axios.get<EventType[]>(`/events/${q ? `?${q}` : ''}`);
  return data;
}

export async function getEvent(eventId: number): Promise<EventType> {
  const { data } = await axios.get<EventType>(`/events/${eventId}/`);
  return data;
}

export async function createEvent(payload: Partial<EventType>, openSignups = false): Promise<EventType> {
  const params = openSignups ? '?open_signups=true' : '';
  const { data } = await axios.post<EventType>(`/events/${params}`, payload);
  return data;
}

export async function updateEvent(eventId: number, payload: Partial<EventType>): Promise<EventType> {
  const { data } = await axios.patch<EventType>(`/events/${eventId}/`, payload);
  return data;
}

export async function deleteEvent(eventId: number): Promise<void> {
  await axios.delete(`/events/${eventId}/`);
}

export async function rsvpForEvent(eventId: number): Promise<EventSignupType> {
  const { data } = await axios.post<EventSignupType>(`/events/${eventId}/rsvp/`);
  return data;
}

export async function openSignups(eventId: number): Promise<EventType> {
  const { data } = await axios.post<EventType>(`/events/${eventId}/open_signups/`);
  return data;
}

export async function startRollCall(eventId: number): Promise<EventType> {
  const { data } = await axios.post<EventType>(`/events/${eventId}/start_roll_call/`);
  return data;
}

export async function startTournament(eventId: number): Promise<EventType> {
  const { data } = await axios.post<EventType>(`/events/${eventId}/start_tournament/`);
  return data;
}

export async function cancelEvent(eventId: number): Promise<EventType> {
  const { data } = await axios.post<EventType>(`/events/${eventId}/cancel/`);
  return data;
}

export async function restartTournament(eventId: number): Promise<EventType> {
  const { data } = await axios.post<EventType>(`/events/${eventId}/restart_tournament/`);
  return data;
}

export async function getEventSignups(eventId: number): Promise<EventSignupType[]> {
  const { data } = await axios.get<EventSignupType[]>(`/events/signups/?event=${eventId}`);
  return data;
}

export async function approveSignup(signupId: number, mmr?: number): Promise<EventSignupType> {
  const { data } = await axios.post<EventSignupType>(
    `/events/signups/${signupId}/approve/`,
    mmr != null ? { mmr } : undefined,
  );
  return data;
}

export async function rejectSignup(signupId: number): Promise<EventSignupType> {
  const { data } = await axios.post<EventSignupType>(`/events/signups/${signupId}/reject/`);
  return data;
}

export async function confirmSignup(signupId: number): Promise<EventSignupType> {
  const { data } = await axios.post<EventSignupType>(`/events/signups/${signupId}/confirm/`);
  return data;
}

export async function cancelSignup(signupId: number): Promise<EventSignupType> {
  const { data } = await axios.post<EventSignupType>(`/events/signups/${signupId}/cancel_signup/`);
  return data;
}

export async function unconfirmSignup(signupId: number): Promise<EventSignupType> {
  const { data } = await axios.post<EventSignupType>(`/events/signups/${signupId}/unconfirm/`);
  return data;
}

export async function demoteSignup(signupId: number): Promise<EventSignupType> {
  const { data } = await axios.post<EventSignupType>(`/events/signups/${signupId}/demote/`);
  return data;
}

export async function reinstateSignup(signupId: number): Promise<EventSignupType> {
  const { data } = await axios.post<EventSignupType>(`/events/signups/${signupId}/reinstate/`);
  return data;
}

// --- EventRepeater ---

export interface EventRepeaterType {
  id: number;
  organization: number;
  organization_name: string;
  name: string;
  description: string;
  frequency: string;
  day_of_week: number | null;
  time_of_day: string;
  starts_at: string;
  ends_at: string | null;
  generate_days_ahead: number;
  is_active: boolean;
  created_by: number | null;
  created_at: string;
  updated_at: string;
  tournament_name: string;
  tournament_league: number;
  tournament_type: string;
  game_type: number;
  draft_type: string;
  game_mode: string;
  custom_game_name: string;
  captains_draft_time: number;
  lobby_steam_league_id: number | null;
  people_per_team: number;
  number_of_teams: number | null;
  tournament_date: string | null;
  timezone: string;
  min_players: number | null;
  max_players: number | null;
  signup_deadline_hours: number | null;
  allow_team_signups: boolean;
  allow_user_signups: boolean;
  auto_approve: boolean;
  auto_confirm: boolean;
  require_mmr_verified: boolean;
  require_steam_id: boolean;
  require_profile_complete: boolean;
  roll_call_enabled: boolean;
  roll_call_mode: string;
  discord_create_event: boolean;
  discord_sync_signups: boolean;
  discord_event_title: string;
  discord_event_description: string;
  discord_event_info: string;
  discord_signup_reminder: boolean;
  discord_signup_reminder_hours: number;
  discord_confirm_attendance: boolean;
  discord_profile_reminder: boolean;
  discord_mark_interested: boolean;
  discord_post_signups: boolean;
  discord_post_signups_channel_id: string;
  discord_announcement: boolean;
  discord_announcement_channel_id: string;
  discord_announcement_hours: number;
  discord_require_rank_screenshot: boolean;
  discord_require_battlecup_screenshot: boolean;
  min_mmr: number | null;
  discord_notify_new_events: boolean;
  discord_profile_reminder_hours: number;
  discord_confirm_attendance_hours: number;
  subscriber_count: number;
  is_subscribed: boolean;
}

export async function getEventRepeaters(params?: { organization?: number }): Promise<EventRepeaterType[]> {
  const sp = new URLSearchParams();
  if (params?.organization) sp.set('organization', String(params.organization));
  const q = sp.toString();
  const { data } = await axios.get<EventRepeaterType[]>(`/events/repeaters/${q ? `?${q}` : ''}`);
  return data;
}

export async function createEventRepeater(payload: Partial<EventRepeaterType>): Promise<EventRepeaterType> {
  const { data } = await axios.post<EventRepeaterType>('/events/repeaters/', payload);
  return data;
}

export async function updateEventRepeater(repeaterId: number, payload: Partial<EventRepeaterType>): Promise<EventRepeaterType> {
  const { data } = await axios.patch<EventRepeaterType>(`/events/repeaters/${repeaterId}/`, payload);
  return data;
}

// --- OrgEventDefaults ---

export interface OrgEventDefaultsType {
  id: number;
  organization: number;
  tournament_name: string;
  tournament_league: number | null;
  tournament_type: string;
  game_type: number;
  draft_type: string;
  people_per_team: number;
  number_of_teams: number | null;
  tournament_date: string | null;
  game_mode: string;
  custom_game_name: string;
  captains_draft_time: number;
  lobby_steam_league_id: number | null;
  timezone: string;
  min_players: number | null;
  max_players: number | null;
  signup_deadline_hours: number | null;
  allow_team_signups: boolean;
  allow_user_signups: boolean;
  auto_approve: boolean;
  auto_confirm: boolean;
  require_mmr_verified: boolean;
  require_steam_id: boolean;
  require_profile_complete: boolean;
  roll_call_enabled: boolean;
  roll_call_mode: string;
  discord_create_event: boolean;
  discord_sync_signups: boolean;
  discord_event_title: string;
  discord_event_description: string;
  discord_event_info: string;
  discord_signup_reminder: boolean;
  discord_signup_reminder_hours: number;
  discord_confirm_attendance: boolean;
  discord_confirm_attendance_hours: number;
  discord_profile_reminder: boolean;
  discord_profile_reminder_hours: number;
  discord_mark_interested: boolean;
  discord_post_signups: boolean;
  discord_post_signups_channel_id: string;
  discord_announcement: boolean;
  discord_announcement_channel_id: string;
  discord_announcement_hours: number;
  discord_require_rank_screenshot: boolean;
  discord_require_battlecup_screenshot: boolean;
  min_mmr: number | null;
}

export async function getOrgEventDefaults(orgId: number): Promise<OrgEventDefaultsType> {
  const { data } = await axios.get<OrgEventDefaultsType>(
    `/events/defaults/?organization=${orgId}`
  );
  return data;
}

export async function updateOrgEventDefaults(
  defaultsId: number,
  payload: Partial<OrgEventDefaultsType>
): Promise<OrgEventDefaultsType> {
  const { data } = await axios.patch<OrgEventDefaultsType>(
    `/events/defaults/${defaultsId}/`,
    payload
  );
  return data;
}

export interface DiscordChannel {
  id: string;
  name: string;
  type: number;
  type_label: string;
}

export interface DiscordRole {
  id: string;
  name: string;
  color: number;
  mentionable: boolean;
  position: number;
}

export async function subscribeToRepeater(repeaterId: number): Promise<void> {
  await axios.post(`/events/repeaters/${repeaterId}/subscribe/`);
}

export async function unsubscribeFromRepeater(repeaterId: number): Promise<void> {
  await axios.post(`/events/repeaters/${repeaterId}/unsubscribe/`);
}

export async function getEventDiscordState(eventId: number) {
  try {
    const { data } = await axios.get(`/events/${eventId}/discord/`);
    return data;
  } catch {
    return null;
  }
}

export async function getDiscordChannels(
  orgId: number,
  refresh = false
): Promise<DiscordChannel[]> {
  const params = refresh ? '?refresh=true' : '';
  const { data } = await axios.get<{ channels: DiscordChannel[] }>(
    `/discord/organizations/${orgId}/channels/${params}`
  );
  return data.channels;
}

export async function getDiscordRoles(
  orgId: number,
  refresh = false
): Promise<DiscordRole[]> {
  const params = refresh ? '?refresh=true' : '';
  const { data } = await axios.get<{ roles: DiscordRole[] }>(
    `/discord/organizations/${orgId}/roles/${params}`
  );
  return data.roles;
}
