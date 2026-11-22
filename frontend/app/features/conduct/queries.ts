import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';
import {
  conductKeys,
  invalidateConductQueries,
  type OrgFeatureAccess,
} from '~/features/org-features';
import {
  getAttendance,
  getConductSettings,
  getForecast,
  getMemberConduct,
  patchConductSettings,
  putAttendance,
} from './api';
import type {
  Attendance,
  AttendancePut,
  ConductSettings,
  ConductSettingsForm,
  Forecast,
  HistoryPage,
  MemberConduct,
} from './schemas';

function canView(access: OrgFeatureAccess): boolean {
  return access.settled && (access.canViewConduct || access.canViewOwnConduct);
}

function canManage(access: OrgFeatureAccess): boolean {
  return access.settled && access.canManageConduct;
}

export function useMemberConduct(
  orgId: number,
  access: OrgFeatureAccess,
  orgUserPk: number | null,
  page: HistoryPage,
): UseQueryResult<MemberConduct> {
  return useQuery({
    queryKey: conductKeys.member(orgId, access.viewerPk, orgUserPk ?? 0, page),
    queryFn: () => getMemberConduct(orgId, orgUserPk!, page),
    enabled: canView(access) && orgUserPk != null,
    placeholderData: (previous, previousQuery) =>
      previousQuery?.queryKey[1] === orgId &&
      previousQuery.queryKey[2] === access.viewerPk &&
      previousQuery.queryKey[3] === 'member' &&
      previousQuery.queryKey[4] === orgUserPk
        ? previous
        : undefined,
  });
}

export function useConductSettings(
  orgId: number,
  access: OrgFeatureAccess,
  enabled = true,
): UseQueryResult<ConductSettings> {
  return useQuery({
    queryKey: conductKeys.settings(orgId, access.viewerPk),
    queryFn: () => getConductSettings(orgId),
    enabled: enabled && canManage(access),
  });
}

export function usePatchConductSettings(
  orgId: number,
  access: OrgFeatureAccess,
): UseMutationResult<ConductSettings, unknown, Partial<ConductSettingsForm>> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body) => patchConductSettings(orgId, body),
    onSuccess: (saved) => {
      queryClient.setQueryData(
        conductKeys.settings(orgId, access.viewerPk),
        saved,
      );
    },
    onSettled: (_saved, error) =>
      invalidateConductQueries(
        queryClient,
        orgId,
        error == null
          ? { except: conductKeys.settings(orgId, access.viewerPk) }
          : undefined,
      ),
  });
}

export function useAttendance(
  orgId: number,
  access: OrgFeatureAccess,
  eventId: number,
  enabled: boolean,
): UseQueryResult<Attendance> {
  return useQuery({
    queryKey: conductKeys.attendance(orgId, access.viewerPk, eventId),
    queryFn: () => getAttendance(orgId, eventId),
    enabled: enabled && access.settled,
  });
}

export function useForecast(
  orgId: number,
  access: OrgFeatureAccess,
  eventId: number,
  enabled: boolean,
): UseQueryResult<Forecast> {
  return useQuery({
    queryKey: conductKeys.forecast(orgId, access.viewerPk, eventId),
    queryFn: () => getForecast(orgId, eventId),
    enabled: enabled && access.settled,
  });
}

export function usePutAttendance(
  orgId: number,
  access: OrgFeatureAccess,
  eventId: number,
): UseMutationResult<Attendance, unknown, AttendancePut> {
  const queryClient = useQueryClient();
  const key = conductKeys.attendance(orgId, access.viewerPk, eventId);
  return useMutation({
    mutationFn: (body) => putAttendance(orgId, eventId, body),
    onSuccess: (saved) => {
      queryClient.setQueryData(key, saved);
    },
    onSettled: (_saved, error) =>
      invalidateConductQueries(
        queryClient,
        orgId,
        error == null ? { except: key } : undefined,
      ),
  });
}
