import TournamentDetailPage from '~/pages/tournament/TournamentDetailPage';
import { generateMeta } from '~/lib/seo';
import { fetchTournament } from '~/components/api/api';
import { queryClient } from '~/root';
import type { Route } from './+types/tournament';
import { fetchSSR } from '~/lib/ssr.server';
import type { TournamentSSR } from '~/lib/ssr-types';

export async function loader({ params }: Route.LoaderArgs) {
  const tournament = await fetchSSR<TournamentSSR>(`/tournaments/${params.pk}/ssr/`);
  return { tournament };
}

export async function clientLoader({ params }: Route.ClientLoaderArgs) {
  const pk = params.pk ? parseInt(params.pk, 10) : null;
  if (!pk) return { tournament: null };

  try {
    const tournament = await fetchTournament(pk);
    // Seed TanStack Query cache so useTournament() doesn't re-fetch
    queryClient.setQueryData(['tournament', pk], tournament);
    return { tournament };
  } catch {
    return { tournament: null };
  }
}

export function meta({ data }: Route.MetaArgs) {
  const tournament = data?.tournament as TournamentSSR | null;

  if (tournament?.name) {
    const orgText = tournament.org_name ? ` presented by ${tournament.org_name}` : '';
    return generateMeta({
      title: tournament.name,
      description: `${tournament.name}${orgText} — DraftForge tournament management, drafts, and team organization`,
      image: tournament.org_logo || '/assets/site_snapshots/tournament.png',
      url: `/tournament/${tournament.pk}`,
    });
  }

  return generateMeta({
    title: 'Tournament',
    description: 'Tournament brackets and team matchups',
    image: '/assets/site_snapshots/tournament.png',
  });
}

export default TournamentDetailPage;
