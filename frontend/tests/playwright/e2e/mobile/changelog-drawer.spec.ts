import { expect, test, visitAndWaitForHydration } from '../../fixtures';
import { latestChangelogVersions } from '../../helpers/changelog';

test.describe('Mobile drawer changelog (@cicd)', () => {
  test('shows the latest release and links to /changelog', async ({ page }) => {
    const [latest] = latestChangelogVersions(1);
    await visitAndWaitForHydration(page, '/');
    await page.getByTestId('mobileNavToggle').click();

    const drawer = page.locator('[role="dialog"]');
    await expect(drawer).toBeVisible();
    await page.getByTestId('mobile-nav-docs-trigger').click();
    await expect(
      page.getByTestId('mobile-nav-changelog-preview'),
    ).toContainText(latest);

    const { scrollWidth, clientWidth } = await drawer
      .locator('[data-slot=scroll-area-viewport]')
      .evaluate((el) => ({
        scrollWidth: el.scrollWidth,
        clientWidth: el.clientWidth,
      }));
    expect(scrollWidth, 'drawer scrolls sideways').toBeLessThanOrEqual(
      clientWidth,
    );

    const reportIssue = page.getByTestId('mobile-nav-report-issue-link');
    await reportIssue.scrollIntoViewIfNeeded();
    await expect(reportIssue).toBeVisible();

    await page.getByTestId('mobile-nav-changelog-full-link').click();
    await expect(page).toHaveURL(/\/changelog$/);
    await expect(drawer).toBeHidden();
  });
});
