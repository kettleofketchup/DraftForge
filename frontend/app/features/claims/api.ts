import { z } from 'zod';
import api from '~/components/api/axios';
import {
  ProfileClaimRequestSchema,
  type ClaimStatus,
  type ProfileClaimRequest,
} from './schemas';

export async function getClaimRequests(options: {
  organizationId: number;
  status?: ClaimStatus;
}): Promise<ProfileClaimRequest[]> {
  const response = await api.get('/claim-requests/', {
    params: { organization: options.organizationId, status: options.status },
  });
  return z.array(ProfileClaimRequestSchema).parse(response.data);
}

const ClaimActionResponseSchema = z.object({ message: z.string() });

export async function approveClaimRequest(claimId: number): Promise<string> {
  const response = await api.post(`/claim-requests/${claimId}/approve/`);
  return ClaimActionResponseSchema.parse(response.data).message;
}
