import type { Page } from '@playwright/test';
import {
  expect,
  postWithCsrf,
  test,
  visitAndWaitForHydration,
} from '../../fixtures';
import { API_URL } from '../../fixtures/auth';

interface ClaimRequest {
  id: number;
  claimer: number;
  claimer_username: string;
  target_user: number;
  target_nickname: string;
  organization: number;
}

async function searchMembers(page: Page, query: string): Promise<void> {
  await page.getByTestId('org-tab-users').click();
  const search = page.getByPlaceholder('Search members...');
  if (await search.isVisible()) await search.fill(query);
}

test.describe('Approving a profile claim', () => {
  test('updates the org Users tab without a reload', async ({
    page,
    context,
    loginOrgAdmin,
  }) => {
    const created = await context.request.post(
      `${API_URL}/tests/create-claim-request/`,
    );
    expect(created.ok(), await created.text()).toBe(true);
    const { claim_request: claim } = (await created.json()) as {
      claim_request: ClaimRequest;
    };
    const suffix = claim.claimer_username.replace(/^claimer_/, '');

    await loginOrgAdmin();
    const added = await postWithCsrf(
      context,
      `${API_URL}/organizations/${claim.organization}/members/`,
      { user_id: claim.target_user },
    );
    expect(added.ok(), await added.text()).toBe(true);

    await visitAndWaitForHydration(
      page,
      `/organizations/${claim.organization}`,
    );
    const usersTab = page.getByTestId('org-tab-users');
    const members = page.getByRole('tabpanel');

    await searchMembers(page, suffix);
    await expect(members.getByText(claim.target_nickname)).toBeVisible();
    await expect(
      members.getByTestId(`usercard-${claim.claimer_username}`),
    ).toHaveCount(0);
    const countBefore = await usersTab.textContent();

    await page.getByTestId('org-tab-claims').click();
    await page.getByTestId(`approve-claim-btn-${claim.id}`).click();
    await page.getByTestId('confirm-approve-claim').click();
    await expect(page.getByTestId(`claim-card-${claim.id}`)).toHaveCount(0);

    await searchMembers(page, suffix);
    await expect(
      members.getByTestId(`usercard-${claim.claimer_username}`),
    ).toHaveCount(1);
    await expect(members.getByText(claim.target_nickname)).toHaveCount(0);
    await expect(usersTab).toHaveText(countBefore ?? '');
  });
});
