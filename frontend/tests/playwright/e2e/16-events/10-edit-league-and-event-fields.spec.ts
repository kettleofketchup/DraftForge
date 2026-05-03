import {
  expect,
  getEventsTestData,
  loginAdmin,
  loginEventAdmin,
  patchWithCsrf,
  resetEventsData,
  test,
  visitAndWaitForHydration,
} from '../../fixtures';

// Wrap in describe.serial — Tests 1 and 5 both mutate League pk=7's
// steam_league_id. Under parallel workers (CI sharding, --workers=N), they
// would race on the same row. Serial ordering eliminates that risk and is
// also necessary because afterEach revert assumes the test that ran just
// before knew which value to put back.
//
// Login choice:
// - UI tests (1, 2, 3) use loginAdmin (site superuser). The events admin
//   user (pk=5000) is on org.admins but the embedded league.organization
//   sub-serializer omits admin info, so useIsLeagueAdmin can't see it and
//   the Edit button stays hidden. Org-admin API authorization is already
//   covered by backend tests in Task 4/5; here we only validate the UI flow.
// - API-only tests (4, 5) keep loginEventAdmin so they exercise the real
//   org-admin authorization path the feature targets.
test.describe.serial('Edit league + event fields @cicd', () => {
  // Track League.steam_league_id mutations so we can revert them after each test.
  // resetEventsData does NOT restore League fields; we must do it ourselves to
  // keep the events league at its canonical 17935 value for subsequent runs.
  const ORIGINAL_EVENTS_LEAGUE_STEAM_ID = 17935;

  test.beforeEach(async ({ context }) => {
    await resetEventsData(context);
  });

  test.afterEach(async ({ context }) => {
    // Revert any steam_league_id mutation on the events league.
    // Playwright resets cookies per-test, so re-login is required.
    const eventInfo = await getEventsTestData(context);
    await loginAdmin(context);
    try {
      const resp = await patchWithCsrf(
        context,
        `/api/leagues/${eventInfo.eventsLeaguePk}/`,
        { steam_league_id: ORIGINAL_EVENTS_LEAGUE_STEAM_ID },
      );
      // Don't fail the test on a no-op revert (test never mutated), but surface
      // genuine errors so they don't silently break later runs.
      if (!resp.ok() && resp.status() !== 400) {
        console.warn(`[afterEach] revert PATCH returned ${resp.status()}`);
      }
    } catch (err) {
      console.warn('[afterEach] revert PATCH failed:', err);
    }
  });

  test('edit league steam_league_id happy path', async ({ page, context }) => {
    const eventInfo = await getEventsTestData(context);
    await loginAdmin(context);

    await visitAndWaitForHydration(page, `/leagues/${eventInfo.eventsLeaguePk}`);
    await expect(page.getByTestId('edit-league-button')).toBeVisible({ timeout: 15000 });
    await page.getByTestId('edit-league-button').click();

    // Change steam_league_id to a fresh unused value.
    // Note: .fill() replaces the entire field value and triggers a single
    // input event — works correctly with the Controller + parseInt onChange.
    const newId = '99999';
    await page.getByTestId('edit-league-steam-id').fill(newId);
    await page.getByTestId('edit-league-modal').getByTestId('form-dialog-submit').click();

    // Toast confirms success (sonner: [data-sonner-toast][data-type="success"]).
    await expect(page.locator('[data-sonner-toast][data-type="success"]').filter({ hasText: /updated successfully/i })).toBeVisible();

    // Reload and assert the badge reflects the new ID.
    await page.reload();
    await expect(page.getByText(`Steam ID: ${newId}`).first()).toBeVisible();
  });

  test('edit league steam_league_id can be cleared (null is valid)', async ({ page, context }) => {
    const eventInfo = await getEventsTestData(context);
    await loginAdmin(context);

    await visitAndWaitForHydration(page, `/leagues/${eventInfo.eventsLeaguePk}`);
    await expect(page.getByTestId('edit-league-button')).toBeVisible({ timeout: 15000 });
    await page.getByTestId('edit-league-button').click();

    // Empty the input — Controller onChange emits null, schema accepts it,
    // backend validator returns the value through, DB stores NULL (which the
    // partial unique constraint ignores).
    await page.getByTestId('edit-league-steam-id').fill('');
    await page.getByTestId('edit-league-modal').getByTestId('form-dialog-submit').click();

    await expect(
      page
        .locator('[data-sonner-toast][data-type="success"]')
        .filter({ hasText: /updated successfully/i }),
    ).toBeVisible();
  });

  test('edit league steam_league_id collision', async ({ page, context }) => {
    const eventInfo = await getEventsTestData(context);
    await loginAdmin(context);

    await visitAndWaitForHydration(page, `/leagues/${eventInfo.eventsLeaguePk}`);
    await expect(page.getByTestId('edit-league-button')).toBeVisible({ timeout: 15000 });
    await page.getByTestId('edit-league-button').click();

    // Change to DTX_LEAGUE.steam_league_id (17929) — already in use.
    await page.getByTestId('edit-league-steam-id').fill('17929');
    await page.getByTestId('edit-league-modal').getByTestId('form-dialog-submit').click();

    // Toast surfaces the colliding-league error from extractApiError → DRF field-level shape.
    // The custom validator on LeagueSerializer must fire (not the auto-UniqueValidator),
    // producing the named-collision message.
    await expect(
      page
        .locator('[data-sonner-toast][data-type="error"]')
        .filter({ hasText: /already in use by/i }),
    ).toBeVisible();
  });

  test('edit event tournament_league happy path', async ({ page, context }) => {
    const eventInfo = await getEventsTestData(context);
    await loginAdmin(context);

    await visitAndWaitForHydration(page, `/events/${eventInfo.pk}`);
    await expect(page.getByTestId('event-edit-btn')).toBeVisible({ timeout: 15000 });
    await page.getByTestId('event-edit-btn').click();

    // Pick the alt league from the same org via per-option testid.
    await page.getByTestId('edit-event-tournament-league').click();
    await page.getByTestId(`league-option-${eventInfo.altLeaguePk}`).click();

    // Wait for the trigger to reflect the new selection so submit has the latest form state.
    await expect(page.getByTestId('edit-event-tournament-league')).toContainText(
      eventInfo.altLeagueName,
    );

    await page.getByTestId('edit-event-modal').getByTestId('form-dialog-submit').click();

    // Wait for the modal to close — confirms the PATCH completed and onSuccess fired.
    await expect(page.getByTestId('edit-event-modal')).not.toBeVisible({ timeout: 10000 });

    // Confirm the league has changed via API (the detail page does not surface
    // the league name in a stable testable element).
    const eventResp = await context.request.get(`/api/events/${eventInfo.pk}/`);
    expect(eventResp.status()).toBe(200);
    const body = await eventResp.json();
    expect(body.tournament_league).toBe(eventInfo.altLeaguePk);

    // Revert: PATCH back to the events league so other tests in the suite see the canonical state.
    await patchWithCsrf(context, `/api/events/${eventInfo.pk}/`, {
      tournament_league: eventInfo.eventsLeaguePk,
    });
  });

  test('edit event tournament_league: clear via combobox', async ({ page, context }) => {
    const eventInfo = await getEventsTestData(context);
    await loginAdmin(context);

    await visitAndWaitForHydration(page, `/events/${eventInfo.pk}`);
    await expect(page.getByTestId('event-edit-btn')).toBeVisible({ timeout: 15000 });
    await page.getByTestId('event-edit-btn').click();

    // Open combobox and pick Clear
    await page.getByTestId('edit-event-tournament-league').click();
    await page.getByTestId('edit-event-league-clear').click();

    // Trigger shows the placeholder
    await expect(page.getByTestId('edit-event-tournament-league')).toContainText(/select/i);

    // Save (the modal uses form-dialog-submit, scoped to the edit-event-modal)
    await page.getByTestId('edit-event-modal').getByTestId('form-dialog-submit').click();

    // Wait for the modal to close — confirms the PATCH completed
    await expect(page.getByTestId('edit-event-modal')).not.toBeVisible({ timeout: 10000 });

    // API sanity-check
    const apiResp = await context.request.get(`/api/events/${eventInfo.pk}/`);
    expect(apiResp.status()).toBe(200);
    const body = await apiResp.json();
    expect(body.tournament_league).toBeNull();

    // Revert so subsequent tests in the suite see the canonical league
    await patchWithCsrf(context, `/api/events/${eventInfo.pk}/`, {
      tournament_league: eventInfo.eventsLeaguePk,
    });
  });

  test('edit event tournament_league org-scope guard (API-level)', async ({
    context,
  }) => {
    const eventInfo = await getEventsTestData(context);
    await loginEventAdmin(context);

    // DTX_LEAGUE pk=1 is in a different organization.
    const resp = await patchWithCsrf(
      context,
      `/api/events/${eventInfo.pk}/`,
      { tournament_league: 1 },
    );
    expect(resp.status()).toBe(400);
    const body = await resp.json();
    expect(JSON.stringify(body)).toMatch(/must belong to the event's organization/i);
  });

  test('cache-correctness: PATCH then GET returns new steam_league_id', async ({
    context,
  }) => {
    const eventInfo = await getEventsTestData(context);
    await loginEventAdmin(context);

    // Prime the cache with a GET first (uses BrowserContext cookies set by login).
    const beforeResp = await context.request.get(
      `/api/leagues/${eventInfo.eventsLeaguePk}/`,
    );
    expect(beforeResp.status()).toBe(200);

    // Mutate via CSRF-aware PATCH.
    const patchResp = await patchWithCsrf(
      context,
      `/api/leagues/${eventInfo.eventsLeaguePk}/`,
      { steam_league_id: 99998 },
    );
    expect(patchResp.status()).toBe(200);

    // Read through cache — should return the new value.
    const afterResp = await context.request.get(
      `/api/leagues/${eventInfo.eventsLeaguePk}/`,
    );
    expect(afterResp.status()).toBe(200);
    const body = await afterResp.json();
    expect(body.steam_league_id).toBe(99998);
  });
});
