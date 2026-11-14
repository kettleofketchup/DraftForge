import api from '~/components/api/axios';
import {
  OrgFeatureRowsSchema,
  type OrgFeatureRow,
  type SetOrgFeaturePayload,
} from './schemas';

export async function getOrgFeatures(orgId: number): Promise<OrgFeatureRow[]> {
  const response = await api.get(`/organizations/${orgId}/features/`);
  return OrgFeatureRowsSchema.parse(response.data);
}

export async function setOrgFeature(
  orgId: number,
  payload: SetOrgFeaturePayload,
): Promise<OrgFeatureRow[]> {
  const response = await api.put(`/organizations/${orgId}/features/`, payload);
  return OrgFeatureRowsSchema.parse(response.data);
}
