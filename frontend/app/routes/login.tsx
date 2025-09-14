import HomePage from '~/pages/home/home';
import type { Route } from './+types/home';

export function meta({}: Route.MetaArgs) {
  return [{ title: 'DTX' }, { name: 'description', content: 'Login' }];
}

export default function Home() {
  return <HomePage />;
}
