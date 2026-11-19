import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';
import { conductKeys, type OrgFeatureAccess } from '~/features/org-features';
import {
  getAttendance,
  getConductLeaderboard,
  getConductSettings,
  getForecast,
  getMemberConduct,
  patchConductSettings,
  putAttendance,
} from './api';
import type {
  Attendance,
  AttendancePut,
  ConductLeaderboard,
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

export function useConductLeaderboard(
  orgId: number,
  access: OrgFeatureAccess,
): UseQueryResult<ConductLeaderboard> {
  return useQuery({
    queryKey: conductKeys.leaderboard(orgId, access.viewerPk),
    queryFn: () => getConductLeaderboard(orgId),
    enabled: canView(access),
  });
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
  });
}

export function useConductSettings(
  orgId: number,
  access: OrgFeatureAccess,
): UseQueryResult<ConductSettings> {
  return useQuery({
    queryKey: conductKeys.settings(orgId, access.viewerPk),
    queryFn: () => getConductSettings(orgId),
    enabled: canManage(access),
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
    enabled: access.settled && enabled,
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
    enabled: access.settled && enabled,
  });
}

function useInvalidateConduct(
  orgId: number,
  access: OrgFeatureAccess,
): () => Promise<void> {
  const queryClient = useQueryClient();
  return () =>
    queryClient.invalidateQueries({
      queryKey: conductKeys.all(orgId, access.viewerPk),
    });
}

export function usePatchConductSettings(
  orgId: number,
  access: OrgFeatureAccess,
): UseMutationResult<ConductSettings, unknown, Partial<ConductSettingsForm>> {
  const invalidate = useInvalidateConduct(orgId, access);
  return useMutation({
    mutationFn: (body) => patchConductSettings(orgId, body),
    onSettled: invalidate,
  });
}

export function usePutAttendance(
  orgId: number,
  access: OrgFeatureAccess,
  eventId: number,
): UseMutationResult<Attendance, unknown, AttendancePut> {
  const invalidate = useInvalidateConduct(orgId, access);
  return useMutation({
    mutationFn: (body) => putAttendance(orgId, eventId, body),
    onSettled: invalidate,
  });
}
