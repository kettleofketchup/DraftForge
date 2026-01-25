import { UserProfilePage } from '~/pages/user/UserProfilePage';
import type { Route } from './+types/home';

export function meta({}: Route.MetaArgs) {
  return [{ title: 'User Profile' }, { name: 'description', content: 'User Profile' }];
}
export default UserProfilePage;
