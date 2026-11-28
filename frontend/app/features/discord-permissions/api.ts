import api from '~/components/api/axios';
import {
  PermissionChecksResponseSchema,
  type PermissionChecksRequest,
  type PermissionChecksResponse,
} from './schemas';

export async function postOrgPermissionChecks(
  orgId: number,
  body: PermissionChecksRequest,
  signal?: AbortSignal,
): Promise<PermissionChecksResponse> {
  const { data } = await api.post(
    `/discord/organizations/${orgId}/permission-checks/`,
    body,
    { signal },
  );
  return PermissionChecksResponseSchema.parse(data);
}

export async function getEventPermissionChecks(
  eventId: number,
  refresh = false,
  signal?: AbortSignal,
): Promise<PermissionChecksResponse> {
  const { data } = await api.get(`/events/${eventId}/permission-checks/`, {
    params: { refresh },
    signal,
  });
  return PermissionChecksResponseSchema.parse(data);
}

export async function postEventPermissionChecks(
  eventId: number,
  body: PermissionChecksRequest,
  signal?: AbortSignal,
): Promise<PermissionChecksResponse> {
  const { data } = await api.post(
    `/events/${eventId}/permission-checks/`,
    body,
    { signal },
  );
  return PermissionChecksResponseSchema.parse(data);
}
