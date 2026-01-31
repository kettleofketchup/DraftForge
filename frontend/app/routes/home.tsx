import HomePage from '~/pages/home/home';
import { generateMeta } from '~/lib/seo';

export function meta() {
  return generateMeta({
    title: 'Home',
    description: 'Manage Dota 2 tournaments, team drafts, and hero drafting',
    url: '/',
  });
}
export default HomePage;
