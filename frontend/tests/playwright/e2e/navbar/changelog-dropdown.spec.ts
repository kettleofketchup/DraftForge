import { DOCS_URL } from '../../../../app/components/navbar/links';
import { expect, test, visitAndWaitForHydration } from '../../fixtures';
import { latestChangelogVersions } from '../../helpers/changelog';

test.use({ viewport: { width: 1280, height: 800 } });

test.describe('Docs dropdown changelog (@cicd)', () => {
  test.beforeEach(async ({ page }) => {
    await visitAndWaitForHydration(page, '/');
  });

  test('opens with the documentation link and the latest two releases', async ({
    page,
  }) => {
    const [latest, previous] = latestChangelogVersions(2);
    await page.getByTestId('nav-docs-trigger').click();

    const panel = page.getByTestId('nav-docs-panel');
    await expect(panel).toBeVisible();
    await expect(panel).toContainText(latest);
    await expect(panel).toContainText(previous);

    const docsLink = page.getByTestId('nav-docs-documentation-link');
    await expect(docsLink).toHaveAttribute('href', DOCS_URL);
    await expect(docsLink).toHaveAttribute('target', '_blank');
  });

  test('release notes do not clip sideways', async ({ page }) => {
    await page.getByTestId('nav-docs-trigger').click();
    await expect(page.getByTestId('nav-changelog-preview')).toBeVisible();

    const viewport = page
      .getByTestId('nav-docs-panel')
      .locator('[data-slot=scroll-area-viewport]');
    const { scrollWidth, clientWidth } = await viewport.evaluate((el) => ({
      scrollWidth: el.scrollWidth,
      clientWidth: el.clientWidth,
    }));
    expect(
      scrollWidth,
      'panel scroll viewport scrolls sideways',
    ).toBeLessThanOrEqual(clientWidth);

    const previewWidth = await page
      .getByTestId('nav-changelog-preview')
      .evaluate((el) => el.getBoundingClientRect().width);
    expect(previewWidth, 'preview wider than its viewport').toBeLessThanOrEqual(
      clientWidth,
    );
  });

  test('a long wrappable word wraps instead of widening the panel', async ({
    page,
  }) => {
    await page.getByTestId('nav-docs-trigger').click();
    const preview = page.getByTestId('nav-changelog-preview');
    await expect(preview).toBeVisible();
    await preview.evaluate((el) => {
      const probe = document.createElement('p');
      probe.style.overflowWrap = 'break-word';
      probe.textContent = 'x'.repeat(400);
      el.appendChild(probe);
    });

    const viewport = page
      .getByTestId('nav-docs-panel')
      .locator('[data-slot=scroll-area-viewport]');
    const { scrollWidth, clientWidth } = await viewport.evaluate((el) => ({
      scrollWidth: el.scrollWidth,
      clientWidth: el.clientWidth,
    }));
    expect(
      scrollWidth,
      'panel scroll viewport scrolls sideways',
    ).toBeLessThanOrEqual(clientWidth);
  });

  test('Escape closes the panel and returns focus to the trigger', async ({
    page,
  }) => {
    const trigger = page.getByTestId('nav-docs-trigger');
    await trigger.click();
    await expect(page.getByTestId('nav-docs-panel')).toBeVisible();

    await page.keyboard.press('Escape');
    await expect(page.getByTestId('nav-docs-panel')).toBeHidden();
    await expect(trigger).toBeFocused();
  });

  test('Enter and Space open the panel from the keyboard', async ({ page }) => {
    const trigger = page.getByTestId('nav-docs-trigger');
    const panel = page.getByTestId('nav-docs-panel');

    await trigger.focus();
    await page.keyboard.press('Enter');
    await expect(panel).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(panel).toBeHidden();
    await expect(trigger).toBeFocused();

    await page.keyboard.press('Space');
    await expect(panel).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(panel).toBeHidden();
  });

  test('the release notes region scrolls from the keyboard', async ({
    page,
  }) => {
    const trigger = page.getByTestId('nav-docs-trigger');
    await trigger.focus();
    await page.keyboard.press('Enter');
    const region = page
      .getByTestId('nav-docs-panel')
      .getByRole('region', { name: /what's new|novedades/i });
    await expect(region).toBeVisible();
    await expect(
      page.getByTestId('nav-changelog-preview').getByRole('heading').first(),
    ).toBeVisible();

    const { scrollHeight, clientHeight } = await region.evaluate((el) => ({
      scrollHeight: el.scrollHeight,
      clientHeight: el.clientHeight,
    }));
    expect(scrollHeight, 'preview should overflow its region').toBeGreaterThan(
      clientHeight,
    );

    await region.focus();
    await expect(region).toBeFocused();
    await page.keyboard.press('PageDown');
    await expect
      .poll(() => region.evaluate((el) => el.scrollTop))
      .toBeGreaterThan(0);
  });

  test('Full changelog link opens the /changelog page', async ({ page }) => {
    await page.getByTestId('nav-docs-trigger').click();
    await page.getByTestId('nav-changelog-full-link').click();

    await expect(page).toHaveURL(/\/changelog$/);
    await expect(page.getByTestId('nav-docs-panel')).toBeHidden();
    await expect(
      page.getByTestId('changelog-page').locator('h1'),
    ).toBeVisible();
    expect(
      await page.getByTestId('changelog-release').count(),
    ).toBeGreaterThanOrEqual(2);
  });

  test('closes when the route changes while open', async ({ page }) => {
    const startPath = new URL(page.url()).pathname;
    await page.getByTestId('nav-docs-trigger').click();
    await page.getByTestId('nav-changelog-full-link').click();
    await expect(page).toHaveURL(/\/changelog$/);

    await page.getByTestId('nav-docs-trigger').click();
    await expect(page.getByTestId('nav-docs-panel')).toBeVisible();

    await page.goBack();
    await expect.poll(() => new URL(page.url()).pathname).toBe(startPath);
    await expect(page.getByTestId('nav-docs-panel')).toBeHidden();
  });
});
