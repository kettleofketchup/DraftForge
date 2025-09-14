import UserPage from '~/pages/user/user';
import type { Route } from './+types/home';

export function meta({}: Route.MetaArgs) {
  return [{ title: 'User' }, { name: 'description', content: 'User Details!' }];
}
export default UserPage;
