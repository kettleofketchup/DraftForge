import type { Route } from './+types/home';
import { UsersPage } from '../pages/users/users';

export function meta({}: Route.MetaArgs) {
  return [{ title: 'DTX' }, { name: 'description', content: 'DTX' }];
}

export default function Home() {
  return <UsersPage />;
}
