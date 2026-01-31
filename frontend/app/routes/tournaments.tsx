import TournamentsPage from '~/pages/tournaments/tournaments';
import { generateMeta } from '~/lib/seo';

export function meta() {
  return generateMeta({
    title: 'Tournaments',
    description: 'Browse and manage Dota 2 tournaments',
    url: '/tournaments',
  });
}
export default TournamentsPage;
