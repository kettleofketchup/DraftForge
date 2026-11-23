import {
  expect,
  loginOrgFeatures,
  resetOrgFeatures,
  test,
  type OrgFeaturesTestData,
} from '../../fixtures';
import { API_URL } from '../../fixtures/base-url';

test.describe('Org features: event helper ops notices @cicd', () => {
  let data: OrgFeaturesTestData;

  test.beforeEach(async ({ request }) => {
    data = await resetOrgFeatures(request);
  });

  test('a helper can list ops notices for their event only @cicd', async ({
    context,
  }) => {
    const completed = data.events.completed.pk;
    const upcoming = data.events.upcoming.pk;
    await loginOrgFeatures(context, 'promoter');

    const own = await context.request.get(
      `${API_URL}/events/${completed}/ops-notices/`,
    );
    expect(own.status()).toBe(200);

    const event = await context.request.get(`${API_URL}/events/${completed}/`);
    expect(event.status()).toBe(200);
    const body = (await event.json()) as {
      user_is_event_operator: boolean;
      user_can_manage: boolean;
    };
    expect(body.user_is_event_operator).toBe(true);
    expect(body.user_can_manage).toBe(false);

    const other = await context.request.get(
      `${API_URL}/events/${upcoming}/ops-notices/`,
    );
    expect(other.status()).toBe(403);
  });

  test('a plain member cannot list event ops notices @cicd', async ({
    context,
  }) => {
    await loginOrgFeatures(context, 'member');
    const resp = await context.request.get(
      `${API_URL}/events/${data.events.completed.pk}/ops-notices/`,
    );
    expect(resp.status()).toBe(403);
  });

  test('a helper can view the ready check @cicd', async ({ context }) => {
    await loginOrgFeatures(context, 'promoter');
    const resp = await context.request.get(
      `${API_URL}/events/${data.events.completed.pk}/ready-check/`,
    );
    expect(resp.status()).toBe(200);
    const body = (await resp.json()) as { ready_check: unknown };
    expect(body.ready_check).toBeNull();
  });
});
