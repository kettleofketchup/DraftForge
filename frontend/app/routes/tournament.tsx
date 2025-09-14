import TournamentDetailPage from '~/pages/tournament/TournamentDetailPage';
import type { Route } from './+types/home';

export function meta({}: Route.MetaArgs) {
  return [
    { title: 'Dota Tournaments' },
    { name: 'description', content: 'Tournament Details' },
  ];
}
export default TournamentDetailPage;
