import { generateMeta } from '~/lib/seo';
import { UsersPage } from '../pages/users/users';

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
