import { UserProfilePage } from '~/pages/user/UserProfilePage';
import { generateMeta } from '~/lib/seo';
import { fetchUser } from '~/components/api/api';
import type { Route } from './+types/user';
import type { UserSSR } from '~/lib/ssr-types';

export async function loader({ params }: Route.LoaderArgs) {
  const { fetchSSR } = await import('~/lib/ssr.server');
  const user = await fetchSSR<UserSSR>(`/users/${params.pk}/ssr/`);
  return { user };
}

export async function clientLoader({ params }: Route.ClientLoaderArgs) {
  const pk = params.pk ? parseInt(params.pk, 10) : null;
  if (!pk) return { user: null };

  try {
    const user = await fetchUser(pk);
    return { user };
  } catch {
    return { user: null };
  }
}

export function meta({ data }: Route.MetaArgs) {
  const user = data?.user;

  if (user) {
    const displayName = user.nickname || user.username || 'Player';
    return generateMeta({
      title: displayName,
      description: `${displayName} — Dota 2 player profile on DraftForge`,
      url: `/user/${user.pk}`,
    });
  }

  return generateMeta({
    title: 'Player Profile',
    description: 'Player stats and match history',
  });
}

export default UserProfilePage;
