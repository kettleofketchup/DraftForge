import api from '~/components/api/axios';
import {
  AttendanceSchema,
  ConductSettingsSchema,
  ForecastSchema,
  MemberConductSchema,
  type Attendance,
  type AttendancePut,
  type ConductSettings,
  type ConductSettingsForm,
  type Forecast,
  type HistoryPage,
  type MemberConduct,
} from './schemas';

function base(orgId: number): string {
  return `/organizations/${orgId}/conduct`;
}

export async function getMemberConduct(
  orgId: number,
  orgUserPk: number,
  page: HistoryPage,
): Promise<MemberConduct> {
  const response = await api.get(`${base(orgId)}/members/${orgUserPk}/`, {
    params: { limit: page.limit, offset: page.offset },
  });
  return MemberConductSchema.parse(response.data);
}

export async function getConductSettings(
  orgId: number,
): Promise<ConductSettings> {
  const response = await api.get(`${base(orgId)}/settings/`);
  return ConductSettingsSchema.parse(response.data);
}

export async function patchConductSettings(
  orgId: number,
  body: Partial<ConductSettingsForm>,
): Promise<ConductSettings> {
  const response = await api.patch(`${base(orgId)}/settings/`, body);
  return ConductSettingsSchema.parse(response.data);
}

function eventBase(orgId: number, eventId: number): string {
  return `${base(orgId)}/events/${eventId}`;
}

export async function getAttendance(
  orgId: number,
  eventId: number,
): Promise<Attendance> {
  const response = await api.get(`${eventBase(orgId, eventId)}/attendance/`);
  return AttendanceSchema.parse(response.data);
}

export async function putAttendance(
  orgId: number,
  eventId: number,
  body: AttendancePut,
): Promise<Attendance> {
  const response = await api.put(
    `${eventBase(orgId, eventId)}/attendance/`,
    body,
  );
  return AttendanceSchema.parse(response.data);
}

export async function getForecast(
  orgId: number,
  eventId: number,
): Promise<Forecast> {
  const response = await api.get(`${eventBase(orgId, eventId)}/forecast/`);
  return ForecastSchema.parse(response.data);
}
