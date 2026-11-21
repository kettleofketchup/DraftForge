import api from '~/components/api/axios';
import {
  ConductSettingsSchema,
  MemberConductSchema,
  type ConductSettings,
  type ConductSettingsForm,
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
