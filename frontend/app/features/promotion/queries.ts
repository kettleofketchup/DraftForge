import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';
import {
  invalidateContributionQueries,
  promotionKeys,
  type OrgFeatureAccess,
} from '~/features/org-features';
import {
  createPromoTemplate,
  deletePromoTemplate,
  getCandidates,
  getPromoEvents,
  getPromoTemplates,
  renderPromo,
  resolveDiscordMember,
  sendPromo,
  undoPromoSend,
  updatePromoTemplate,
} from './api';
import type {
  CandidateFilters,
  CandidateRow,
  CandidatesResponse,
  PromoEvent,
  PromoSendInput,
  PromoSendResult,
  PromoTemplate,
  PromoTemplateForm,
  PromoUndoResult,
  RenderResponse,
} from './schemas';

/** How often an open candidate list refetches when SFG contacts are imported. */
export const CANDIDATE_POLL_MS = 30_000;

function canUse(access: OrgFeatureAccess): boolean {
  return access.settled && access.canUsePromotion;
}

export function usePromoTemplates(
  orgId: number,
  access: OrgFeatureAccess,
): UseQueryResult<PromoTemplate[]> {
  return useQuery({
    queryKey: promotionKeys.templates(orgId, access.viewerPk),
    queryFn: () => getPromoTemplates(orgId),
    enabled: canUse(access),
  });
}

export function usePromoEvents(
  orgId: number,
  access: OrgFeatureAccess,
): UseQueryResult<PromoEvent[]> {
  return useQuery({
    queryKey: promotionKeys.events(orgId, access.viewerPk),
    queryFn: () => getPromoEvents(orgId),
    enabled: canUse(access),
  });
}

export function useCandidates(
  orgId: number,
  access: OrgFeatureAccess,
  eventId: number | null,
  filters: CandidateFilters,
): UseQueryResult<CandidatesResponse> {
  return useQuery({
    queryKey: promotionKeys.candidates(
      orgId,
      access.viewerPk,
      eventId ?? 0,
      filters,
    ),
    queryFn: () => getCandidates(orgId, eventId!, filters),
    enabled: canUse(access) && eventId != null,
    // SFG contacts are imported out of band, so a configured org's list
    // refreshes while it is on screen. Polling stops while the page is hidden.
    refetchInterval: (query) =>
      query.state.data?.contact_sync.configured ? CANDIDATE_POLL_MS : false,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
    placeholderData: (previous, previousQuery) =>
      previousQuery?.queryKey[1] === orgId &&
      previousQuery.queryKey[2] === access.viewerPk &&
      previousQuery.queryKey[4] === eventId
        ? previous
        : undefined,
  });
}

export function useRenderPromo(
  orgId: number,
  access: OrgFeatureAccess,
  eventId: number,
  templateId: number | null,
  recipientId: number,
): UseQueryResult<RenderResponse> {
  return useQuery({
    queryKey: [
      ...promotionKeys.all(orgId, access.viewerPk),
      'render',
      eventId,
      templateId,
      recipientId,
    ],
    queryFn: () =>
      renderPromo(orgId, eventId, {
        template_id: templateId!,
        recipient_id: recipientId,
      }),
    enabled: canUse(access) && templateId != null,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    retry: false,
  });
}

function useInvalidatePromotion(
  orgId: number,
  access: OrgFeatureAccess,
): () => Promise<void> {
  const queryClient = useQueryClient();
  return () =>
    queryClient.invalidateQueries({
      queryKey: promotionKeys.all(orgId, access.viewerPk),
    });
}

function useInvalidatePromoLedger(
  orgId: number,
  access: OrgFeatureAccess,
): () => Promise<void> {
  const queryClient = useQueryClient();
  return async () => {
    await Promise.all([
      queryClient.invalidateQueries({
        queryKey: promotionKeys.all(orgId, access.viewerPk),
      }),
      invalidateContributionQueries(queryClient, orgId, access.viewerPk),
    ]);
  };
}

export function useSendPromo(
  orgId: number,
  access: OrgFeatureAccess,
  eventId: number,
): UseMutationResult<PromoSendResult, unknown, PromoSendInput> {
  const invalidate = useInvalidatePromoLedger(orgId, access);
  return useMutation({
    mutationFn: (input) => sendPromo(orgId, eventId, input),
    onSettled: invalidate,
  });
}

export function useResolveDiscordMember(
  orgId: number,
  access: OrgFeatureAccess,
  eventId: number,
): UseMutationResult<CandidateRow, unknown, string> {
  const invalidate = useInvalidatePromotion(orgId, access);
  return useMutation({
    mutationFn: (discordId) => resolveDiscordMember(orgId, eventId, discordId),
    onSettled: invalidate,
  });
}

export function useUndoPromoSend(
  orgId: number,
  access: OrgFeatureAccess,
): UseMutationResult<PromoUndoResult, unknown, number> {
  const invalidate = useInvalidatePromoLedger(orgId, access);
  return useMutation({
    mutationFn: (sendId) => undoPromoSend(orgId, sendId),
    onSettled: invalidate,
  });
}

export function useSavePromoTemplate(
  orgId: number,
  access: OrgFeatureAccess,
): UseMutationResult<
  PromoTemplate,
  unknown,
  { id: number | null; input: PromoTemplateForm }
> {
  const invalidate = useInvalidatePromotion(orgId, access);
  return useMutation({
    mutationFn: ({ id, input }) =>
      id == null
        ? createPromoTemplate(orgId, input)
        : updatePromoTemplate(orgId, id, input),
    onSettled: invalidate,
  });
}

export function useDeletePromoTemplate(
  orgId: number,
  access: OrgFeatureAccess,
): UseMutationResult<void, unknown, number> {
  const invalidate = useInvalidatePromotion(orgId, access);
  return useMutation({
    mutationFn: (templateId) => deletePromoTemplate(orgId, templateId),
    onSettled: invalidate,
  });
}
