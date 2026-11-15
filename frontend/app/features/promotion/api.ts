import { z } from 'zod';
import api from '~/components/api/axios';
import {
  CandidatesResponseSchema,
  PromoEventSchema,
  PromoSendResultSchema,
  PromoTemplateSchema,
  RenderResponseSchema,
  type CandidateFilters,
  type CandidatesResponse,
  type PromoEvent,
  type PromoSendInput,
  type PromoSendResult,
  type PromoTemplate,
  type PromoTemplateForm,
  type RenderRequest,
  type RenderResponse,
} from './schemas';

const base = (orgId: number): string => `/organizations/${orgId}/promotion`;

export async function getPromoTemplates(
  orgId: number,
): Promise<PromoTemplate[]> {
  const response = await api.get(`${base(orgId)}/templates/`);
  return z.array(PromoTemplateSchema).parse(response.data);
}

export async function createPromoTemplate(
  orgId: number,
  input: PromoTemplateForm,
): Promise<PromoTemplate> {
  const response = await api.post(`${base(orgId)}/templates/`, input);
  return PromoTemplateSchema.parse(response.data);
}

export async function updatePromoTemplate(
  orgId: number,
  templateId: number,
  input: PromoTemplateForm,
): Promise<PromoTemplate> {
  const response = await api.patch(
    `${base(orgId)}/templates/${templateId}/`,
    input,
  );
  return PromoTemplateSchema.parse(response.data);
}

export async function deletePromoTemplate(
  orgId: number,
  templateId: number,
): Promise<void> {
  await api.delete(`${base(orgId)}/templates/${templateId}/`);
}

export async function getPromoEvents(orgId: number): Promise<PromoEvent[]> {
  const response = await api.get(`${base(orgId)}/events/`);
  return z.array(PromoEventSchema).parse(response.data);
}

export async function getCandidates(
  orgId: number,
  eventId: number,
  filters: CandidateFilters,
): Promise<CandidatesResponse> {
  const response = await api.get(
    `${base(orgId)}/events/${eventId}/candidates/`,
    {
      params: {
        n: filters.n,
        hide_signed_up: filters.hideSignedUp,
        hide_messaged: filters.hideMessaged,
        ...(filters.q ? { q: filters.q } : {}),
      },
    },
  );
  return CandidatesResponseSchema.parse(response.data);
}

export async function renderPromo(
  orgId: number,
  eventId: number,
  body: RenderRequest,
): Promise<RenderResponse> {
  const response = await api.post(
    `${base(orgId)}/events/${eventId}/render/`,
    body,
  );
  return RenderResponseSchema.parse(response.data);
}

export async function sendPromo(
  orgId: number,
  eventId: number,
  body: PromoSendInput,
): Promise<PromoSendResult> {
  const response = await api.post(
    `${base(orgId)}/events/${eventId}/sends/`,
    body,
  );
  return PromoSendResultSchema.parse(response.data);
}

export async function undoPromoSend(
  orgId: number,
  sendId: number,
): Promise<void> {
  await api.delete(`${base(orgId)}/sends/${sendId}/`);
}
