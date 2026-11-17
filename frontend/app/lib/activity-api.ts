import api from '~/components/api/axios';
import type {
  ActivityDraftList,
  ActivityViewEvent,
} from '~/lib/activity-types';

export async function fetchActivityDrafts(): Promise<ActivityDraftList> {
  const { data } = await api.get<ActivityDraftList>(
    '/discord/activity/drafts/',
  );
  return data;
}

export function postActivityView(body: ActivityViewEvent): void {
  api
    .post('/discord/activity/views/', body, {
      skipActivityErrorHandling: true,
    })
    .catch(() => {});
}
