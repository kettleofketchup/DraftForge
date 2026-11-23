import api from '~/components/api/axios';
import {
  ApiLimitsSchema,
  ApiTokenSchema,
  ApiTokensSchema,
  ApiUsageSchema,
  CreatedApiTokenSchema,
  type ApiLimits,
  type ApiToken,
  type ApiUsage,
  type CreatedApiToken,
} from './schemas';

const base = (orgId: number): string => `/organizations/${orgId}`;

export async function listApiTokens(orgId: number): Promise<ApiToken[]> {
  const response = await api.get(`${base(orgId)}/api-tokens/`);
  return ApiTokensSchema.parse(response.data);
}

export async function createApiToken(
  orgId: number,
  name: string,
): Promise<CreatedApiToken> {
  const response = await api.post(`${base(orgId)}/api-tokens/`, { name });
  return CreatedApiTokenSchema.parse(response.data);
}

export async function revokeApiToken(
  orgId: number,
  tokenId: number,
): Promise<ApiToken> {
  const response = await api.delete(`${base(orgId)}/api-tokens/${tokenId}/`);
  return ApiTokenSchema.parse(response.data);
}

export async function getApiUsage(
  orgId: number,
  days: number,
): Promise<ApiUsage> {
  const response = await api.get(`${base(orgId)}/api-tokens/usage/`, {
    params: { days },
  });
  return ApiUsageSchema.parse(response.data);
}

export async function getApiLimits(orgId: number): Promise<ApiLimits> {
  const response = await api.get(`${base(orgId)}/api-limits/`);
  return ApiLimitsSchema.parse(response.data);
}

export async function putApiLimits(
  orgId: number,
  limits: ApiLimits,
): Promise<ApiLimits> {
  const response = await api.put(`${base(orgId)}/api-limits/`, limits);
  return ApiLimitsSchema.parse(response.data);
}
