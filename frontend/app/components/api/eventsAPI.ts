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

export async function createEvent(payload: Partial<EventType>): Promise<EventType> {
  const { data } = await axios.post<EventType>('/events/', payload);
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

export async function getEventSignups(eventId: number): Promise<EventSignupType[]> {
  const { data } = await axios.get<EventSignupType[]>(`/events/signups/?event=${eventId}`);
  return data;
}

export async function approveSignup(signupId: number): Promise<EventSignupType> {
  const { data } = await axios.post<EventSignupType>(`/events/signups/${signupId}/approve/`);
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
