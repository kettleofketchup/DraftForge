import HomePage from '~/pages/home/home';
import type { Route } from './+types/home';

export function meta({}: Route.MetaArgs) {
  return [
    { title: 'Dota Tournaments' },
    { name: 'description', content: 'Welcome to Dota Tournaments!' },
  ];
}
export default HomePage;
