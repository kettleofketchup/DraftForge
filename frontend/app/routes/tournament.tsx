import TournamentDetailPage from '~/pages/tournament/TournamentDetailPage';
import { generateMeta } from '~/lib/seo';
import { fetchTournament } from '~/components/api/api';
import type { Route } from './+types/tournament';

export async function loader({ params }: Route.LoaderArgs) {
  const pk = params.pk ? parseInt(params.pk, 10) : null;
  if (!pk) return { tournament: null };

  try {
    const tournament = await fetchTournament(pk);
    return { tournament };
  } catch {
    return { tournament: null };
  }
}

export function meta({ data }: Route.MetaArgs) {
  const tournament = data?.tournament;

  if (tournament?.name) {
    const teamCount = tournament.teams?.length || 0;
    return generateMeta({
      title: tournament.name,
      description: `${tournament.name} - ${teamCount} teams competing in Dota 2 tournament`,
      image: '/assets/site_snapshots/tournament.png',
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
