import type { Route } from './+types/home';
import HomePage from '~/pages/home/home';

export function meta({}: Route.MetaArgs) {
  return [{ title: 'DTX' }, { name: 'description', content: 'DTX' }];
}

export default function Home() {
  return <HomePage />;
}
