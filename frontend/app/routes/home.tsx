import { Navigate, useLocation } from 'react-router';
import { activityEntryPath } from '~/lib/activity-entry';
import { generateMeta } from '~/lib/seo';
import HomePage from '~/pages/home/home';

export function meta() {
  return generateMeta({
    title: 'Home',
    description: 'Manage Dota 2 tournaments, team drafts, and hero drafting',
    url: '/',
  });
}
export default function HomeRoute() {
  const { pathname, search } = useLocation();
  const activityPath = activityEntryPath(pathname, search);
  return activityPath ? <Navigate to={activityPath} replace /> : <HomePage />;
}
