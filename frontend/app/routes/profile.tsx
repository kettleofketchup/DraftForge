import { ProfilePage } from '~/pages/profile/profile';
import type { Route } from './+types/home';

export function meta({}: Route.MetaArgs) {
  return [
    { title: 'Profile' },
    { name: 'description', content: 'Edit your profile!' },
  ];
}
export default ProfilePage;
