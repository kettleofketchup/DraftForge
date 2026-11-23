/**
 * Tests for Admin Claims Approval Flow
 *
 * Verifies that organization admins can approve or reject profile claim requests.
 *
 * Test flow:
 * 1. Create a pending claim request via test endpoint
 * 2. Login as org admin
 * 3. Navigate to organization claims tab
 * 4. Approve or reject the claim
 * 5. Verify the claim moved to the appropriate status tab
 */

import { expect, test } from '../../fixtures';
import { API_URL } from '../../fixtures/auth';

interface ClaimRequest {
  id: number;
  claimer: number;
  claimer_username: string;
  target_user: number;
  target_nickname: string;
  target_steamid: number;
  organization: number;
  organization_name: string;
  status: string;
}

interface CreateClaimResponse {
  success: boolean;
  claim_request: ClaimRequest;
}

async function createClaimRequest(context: {
  request: {
    post: (url: string) => Promise<{
      ok: () => boolean;
      json: () => Promise<unknown>;
      text: () => Promise<string>;
    }>;
  };
}): Promise<ClaimRequest> {
  const response = await context.request.post(
    `${API_URL}/tests/create-claim-request/`,
  );
  if (!response.ok()) {
    const body = await response.text();
    throw new Error(`Failed to create claim request: ${body}`);
  }
  const data = (await response.json()) as CreateClaimResponse;
  return data.claim_request;
}

test.describe('Admin Claims Approval', () => {
  test('org admin can approve a pending claim', async ({
    page,
    context,
    loginOrgAdmin,
  }) => {
    const claim = await createClaimRequest(context);
    console.log(
      `Created claim ${claim.id} for org ${claim.organization} (${claim.organization_name})`,
    );

    await loginOrgAdmin();

    await page.goto(`/organizations/${claim.organization}`);
    await page.waitForLoadState('networkidle');
    await page.getByTestId('org-tab-claims').click();

    await expect(page.getByTestId('claims-tab-pending')).toBeVisible();
    await page.waitForSelector('[data-testid="claims-list"]', {
      timeout: 10000,
    });
    await expect(page.getByTestId(`claim-card-${claim.id}`)).toBeVisible();

    await page.getByTestId(`approve-claim-btn-${claim.id}`).click();

    await page.getByTestId('confirm-approve-claim').click();

    // Leaving pending means the approval persisted and the list refetched
    await expect(page.getByTestId(`claim-card-${claim.id}`)).not.toBeVisible({
      timeout: 10000,
    });

    await page.getByTestId('claims-tab-approved').click();

    // Wait for either claims-list or claims-empty to appear (tab content loaded)
    await page.waitForSelector(
      '[data-testid="claims-list"], [data-testid="claims-empty"]',
      { timeout: 10000 },
    );

    await expect(page.getByTestId(`claim-card-${claim.id}`)).toBeVisible({
      timeout: 10000,
    });
    await expect(
      page
        .getByTestId(`claim-card-${claim.id}`)
        .getByTestId('claim-target-merged'),
    ).toHaveText(`Merged into ${claim.claimer_username}`);
  });

  test('org admin can reject a claim with reason', async ({
    page,
    context,
    loginOrgAdmin,
  }) => {
    const claim = await createClaimRequest(context);
    console.log(
      `Created claim ${claim.id} for org ${claim.organization} (${claim.organization_name})`,
    );

    await loginOrgAdmin();

    await page.goto(`/organizations/${claim.organization}`);
    await page.waitForLoadState('networkidle');
    await page.getByTestId('org-tab-claims').click();

    await page.waitForSelector('[data-testid="claims-list"]', {
      timeout: 10000,
    });

    await page.getByTestId(`reject-claim-btn-${claim.id}`).click();

    await page
      .getByTestId('rejection-reason-input')
      .fill('Profile already claimed by another user');

    await page.getByTestId('confirm-reject-claim').click();

    // Leaving pending means the rejection persisted and the list refetched
    await expect(page.getByTestId(`claim-card-${claim.id}`)).not.toBeVisible({
      timeout: 10000,
    });

    await page.getByTestId('claims-tab-rejected').click();

    // Wait for either claims-list or claims-empty to appear (tab content loaded)
    await page.waitForSelector(
      '[data-testid="claims-list"], [data-testid="claims-empty"]',
      { timeout: 10000 },
    );

    await expect(page.getByTestId(`claim-card-${claim.id}`)).toBeVisible({
      timeout: 10000,
    });
  });
});
