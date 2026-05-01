import {
  expect,
  loginEventLeagueStaff,
  resetEventsData,
  test,
  visitAndWaitForHydration,
} from '../../fixtures';

// Tournament pk=100 ("Draft Test Tournament") is created by populate_events
// (backend/tests/populate/events.py) under league pk=7 (Events Test League).
// It uses update_or_create(pk=100, ...) so the PK is stable across runs.
// state=in_progress with 2 teams but NO generated bracket — so the toolbar
// renders generateBracketButton (not saveBracketButton). Either button only
// appears inside BracketToolbar, which only renders when canEdit is true,
// so asserting on generateBracketButton verifies the same permission gate.
const TOURNAMENT_PK = 100;

// Use /games (not /bracket) — it's the convention used by existing bracket
// specs (see frontend/tests/playwright/e2e/09-bracket/02-bracket-match-linking.spec.ts).
const TOURNAMENT_ROUTE = `/tournament/${TOURNAMENT_PK}/games`;

test.describe('Bracket toolbar league-staff permission @cicd', () => {
  test.beforeEach(async ({ context }) => {
    await resetEventsData(context);
    // Ensure no carryover auth between tests in the file.
    await context.clearCookies();
  });

  test('event_league_staff sees the bracket toolbar (generate/save button)', async ({
    page,
    context,
  }) => {
    // event_league_staff is staff of league pk=7 only — never an org admin.
    // useCanEditTournament now delegates to useIsLeagueStaff (Task 10b/10c)
    // so this user must see BracketToolbar via the league-staff branch.
    await loginEventLeagueStaff(context);

    await visitAndWaitForHydration(page, TOURNAMENT_ROUTE);

    // Wait for the games tab to mount before asserting on toolbar buttons.
    await expect(page.locator('[data-testid="bracketTab"]')).toBeVisible({
      timeout: 10000,
    });

    // Tournament 100 has no generated bracket, so generateBracketButton is
    // expected; if a future fixture change generates a bracket, saveBracketButton
    // would appear instead. Either proves canEdit === true.
    const generateButton = page.getByTestId('generateBracketButton');
    const saveButton = page.getByTestId('saveBracketButton');

    await expect(generateButton.or(saveButton).first()).toBeVisible({
      timeout: 10000,
    });
  });

  test('anonymous user does not see the bracket toolbar', async ({
    page,
    context,
  }) => {
    // No login — beforeEach already cleared cookies. Anonymous user must
    // not see the toolbar, since useCanEditTournament returns false when
    // there is no logged-in user.
    await context.clearCookies();

    await visitAndWaitForHydration(page, TOURNAMENT_ROUTE);

    // Wait for the games tab to mount so we know the page rendered before
    // we assert the toolbar is absent (avoids a false-negative due to
    // pre-render timing).
    await expect(page.locator('[data-testid="bracketTab"]')).toBeVisible({
      timeout: 10000,
    });

    await expect(page.getByTestId('generateBracketButton')).toHaveCount(0);
    await expect(page.getByTestId('saveBracketButton')).toHaveCount(0);
  });
});
