import HeroDraftPage from '~/pages/herodraft/HeroDraftPage';
import type { Route } from './+types/home';

export function meta({}: Route.MetaArgs) {
  return [
    { title: 'Hero Draft - Captain\'s Mode' },
    { name: 'description', content: 'Dota 2 Captain\'s Mode Hero Draft' },
  ];
}
export default HeroDraftPage;
