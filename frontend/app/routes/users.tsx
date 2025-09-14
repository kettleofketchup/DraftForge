import { UsersPage } from '../pages/users/users';
import type { Route } from './+types/home';

export function meta({}: Route.MetaArgs) {
  return [
    { title: 'Users' },
    { name: 'description', content: 'User Management' },
  ];
}

export default function Home() {
  return <UsersPage />;
}
