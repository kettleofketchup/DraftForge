// frontend/app/hooks/useMatchStats.ts
import { useQuery } from '@tanstack/react-query';
import { MatchDetailSchema, type MatchDetail } from '~/lib/dota/schemas';

async function fetchMatch(matchId: number): Promise<MatchDetail> {
  const response = await fetch(`/api/steam/matches/${matchId}/`);
  if (!response.ok) {
    throw new Error(`Failed to fetch match: ${response.status}`);
  }
  const data = await response.json();
  return MatchDetailSchema.parse(data);
}

export function useMatchStats(matchId: number | null) {
  return useQuery({
    queryKey: ['match', matchId],
    queryFn: () => fetchMatch(matchId!),
    enabled: matchId !== null,
  });
}
