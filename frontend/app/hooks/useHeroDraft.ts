import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getLogger } from '~/lib/logger';
import {
  createHeroDraft,
  getHeroDraft,
  setReady,
  triggerRoll,
  submitChoice,
  submitPick,
  resetDraft,
  type CreateHeroDraftOptions,
} from '~/components/herodraft/api';
import type { HeroDraft } from '~/components/herodraft/types';

const log = getLogger('useHeroDraft');

export function useHeroDraft(draftId: number | null) {
  return useQuery({
    queryKey: ['herodraft', draftId],
    queryFn: () => {
      if (!draftId) throw new Error('No draft ID');
      return getHeroDraft(draftId);
    },
    enabled: !!draftId,
  });
}

export function useCreateHeroDraft() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      gameId,
      options,
    }: {
      gameId: number;
      options?: CreateHeroDraftOptions;
    }) => createHeroDraft(gameId, options),
    onSuccess: (data) => {
      queryClient.setQueryData(['herodraft', data.id], data);
      log.debug('Created hero draft', data.id);
    },
  });
}

export function useSetReady() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: setReady,
    onSuccess: (data) => {
      queryClient.setQueryData(['herodraft', data.id], data);
    },
  });
}

export function useTriggerRoll() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: triggerRoll,
    onSuccess: (data) => {
      queryClient.setQueryData(['herodraft', data.id], data);
    },
  });
}

export function useSubmitChoice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      draftId,
      choiceType,
      value,
    }: {
      draftId: number;
      choiceType: 'pick_order' | 'side';
      value: 'first' | 'second' | 'radiant' | 'dire';
    }) => submitChoice(draftId, choiceType, value),
    onSuccess: (data) => {
      queryClient.setQueryData(['herodraft', data.id], data);
    },
  });
}

export function useSubmitPick() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ draftId, heroId }: { draftId: number; heroId: number }) =>
      submitPick(draftId, heroId),
    onSuccess: (data) => {
      queryClient.setQueryData(['herodraft', data.id], data);
    },
  });
}

export function useResetHeroDraft() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (draftId: number) => resetDraft(draftId),
    onSuccess: (data) => {
      queryClient.setQueryData(['herodraft', data.id], data);
      log.debug('Reset hero draft', data.id);
    },
  });
}

// Helper to update draft state from WebSocket events
export function useUpdateHeroDraftFromWebSocket() {
  const queryClient = useQueryClient();
  return (draft: HeroDraft) => {
    queryClient.setQueryData(['herodraft', draft.id], draft);
  };
}
