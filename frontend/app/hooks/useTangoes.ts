import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import { toast } from 'sonner';
import { z } from 'zod';
import api from '~/components/api/axios';

const TangoesResponseSchema = z.object({
  tangoes_purchased: z.number(),
});

const BuyTangoResponseSchema = z.object({
  tangoes_purchased: z.number(),
  message: z.string(),
});

interface UseTangoesReturn {
  tangoes: number;
  isLoading: boolean;
  buyTango: () => void;
  isBuying: boolean;
  error: Error | null;
}

async function fetchTangoes(): Promise<number> {
  const response = await api.get('/jokes/tangoes/');
  const parsed = TangoesResponseSchema.parse(response.data);
  return parsed.tangoes_purchased;
}

async function buyTangoRequest(): Promise<{ tangoes: number; message: string }> {
  const response = await api.post('/jokes/tangoes/buy/');
  const parsed = BuyTangoResponseSchema.parse(response.data);
  return { tangoes: parsed.tangoes_purchased, message: parsed.message };
}

export function useTangoes(enabled: boolean = true): UseTangoesReturn {
  const queryClient = useQueryClient();

  const tangoesQuery = useQuery({
    queryKey: ['tangoes'],
    queryFn: fetchTangoes,
    enabled,
  });

  const buyTangoMutation = useMutation({
    mutationFn: buyTangoRequest,
    onSuccess: (data) => {
      queryClient.setQueryData(['tangoes'], data.tangoes);
      toast.success(data.message);
    },
    onError: (error: Error) => {
      let message = 'Failed to buy tango';
      if (error instanceof AxiosError && error.response?.data?.detail) {
        message = error.response.data.detail;
      } else if (error.message) {
        message = error.message;
      }
      toast.error(message);
    },
  });

  return {
    tangoes: tangoesQuery.data ?? 0,
    isLoading: tangoesQuery.isLoading,
    buyTango: () => buyTangoMutation.mutate(),
    isBuying: buyTangoMutation.isPending,
    error: tangoesQuery.error,
  };
}
