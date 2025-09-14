import TournamentsPage from '~/pages/tournaments/tournaments';
import type { Route } from './+types/home';

export function meta({}: Route.MetaArgs) {
  return [
    { title: 'Dota Tournaments' },
    { name: 'description', content: 'All the Tournaments!' },
  ];
}
export default TournamentsPage;
