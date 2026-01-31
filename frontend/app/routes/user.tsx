import { UserProfilePage } from '~/pages/user/UserProfilePage';
import { generateMeta } from '~/lib/seo';
import { fetchUser } from '~/components/api/api';
import type { Route } from './+types/user';

export async function loader({ params }: Route.LoaderArgs) {
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
    const mmrText = user.mmr ? ` - ${user.mmr} MMR` : '';
    return generateMeta({
      title: displayName,
      description: `${displayName}${mmrText} - Dota 2 player profile and match history`,
      url: `/user/${user.pk}`,
    });
  }

  return generateMeta({
    title: 'Player Profile',
    description: 'Player stats and match history',
  });
}

export default UserProfilePage;
