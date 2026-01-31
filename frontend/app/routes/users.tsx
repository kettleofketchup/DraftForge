import { UsersPage } from '../pages/users/users';
import { generateMeta } from '~/lib/seo';

export function meta() {
  return generateMeta({
    title: 'Players',
    description: 'Player directory',
    url: '/users',
  });
}

export default function Home() {
  return <UsersPage />;
}
