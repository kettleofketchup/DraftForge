/**
 * Edit User MMR from the Tournament Players tab.
 *
 * Regression: the players-tab edit pencil couldn't edit OrgUser MMR — the modal
 * opened in global scope with the MMR field hidden (the field is gated on a
 * scope-aware mode, which requires the player's OrgUser link). The fix resolves
 * the link from the hydrated user's flat orgUserPk. Asserting the MMR field is
 * visible is the literal regression signal.
 *
 * Uses the dedicated, MMR-linked, non-admin fixture user edit_user_tourn_mmr.
 */
import {
  test, expect, openEditModal, readEditField, fillEditField, saveEditModal, restoreUserField,
} from '../../fixtures';

const API_URL = 'https://localhost/api';
const USER_EDIT_LEAGUE_NAME = 'User Edit League';
const USER_EDIT_TOURNAMENT_NAME = 'User Edit Tournament';
const TARGET_USERNAME = 'edit_user_tourn_mmr';

let tournamentPk: number;

test.describe('Edit User MMR from Tournament Players tab (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });

    const leaguesResp = await context.request.get(`${API_URL}/leagues/`);
    const leagues = await leaguesResp.json();
    const leagueList = Array.isArray(leagues) ? leagues : leagues.results ?? [];
    const editLeague = leagueList.find((l: { name: string }) => l.name === USER_EDIT_LEAGUE_NAME);
    if (!editLeague) throw new Error(`League "${USER_EDIT_LEAGUE_NAME}" not found. Run just db::populate::all`);

    // Load-bearing: league-scope PATCH + league-admin permission need the parent org.
    const leagueDetailResp = await context.request.get(`${API_URL}/leagues/${editLeague.pk}/`);
    const leagueDetail = await leagueDetailResp.json();
    expect(leagueDetail.organization?.pk, 'User Edit League must carry its parent org').toBeTruthy();

    const tournamentsResp = await context.request.get(`${API_URL}/tournaments/?league=${editLeague.pk}`);
    const tournaments = await tournamentsResp.json();
    const tournamentList = Array.isArray(tournaments) ? tournaments : tournaments.results ?? [];
    const editTournament = tournamentList.find((t: { name: string }) => t.name === USER_EDIT_TOURNAMENT_NAME);
    if (!editTournament) throw new Error(`Tournament "${USER_EDIT_TOURNAMENT_NAME}" not found. Run just db::populate::all`);
    tournamentPk = editTournament.pk;

    await context.close();
  });

  test.beforeEach(async ({ loginAdmin }) => {
    await loginAdmin();
  });

  test('edit pencil on a tournament player card can edit org MMR', async ({ page }) => {
    await page.goto(`/tournament/${tournamentPk}`);
    await page.waitForLoadState('networkidle');
    await expect(page.locator('[data-testid="tournamentDetailPage"]')).toBeVisible({ timeout: 15000 });

    // Players is the default tab; click only if a tab nav is present.
    const playersTab = page.locator('[data-testid="playersTab"]');
    if (await playersTab.isVisible()) await playersTab.click();

    // Filter the virtualized grid to the target (HeadlessUI combobox — fill +
    // debounce settle; the options overlay unmounts, no data-state wait).
    const search = page.getByTestId('userSearchInput');
    await expect(search).toBeVisible({ timeout: 10000 });
    await search.fill(TARGET_USERNAME);
    await page.waitForTimeout(800);
    // HeadlessUI combobox stays open after fill; dismiss it so the dropdown
    // does not intercept pointer events on the card below.
    await page.keyboard.press('Escape');

    const targetCard = page.locator(`[data-testid="usercard-${TARGET_USERNAME}"]`);
    await expect(targetCard).toBeVisible({ timeout: 10000 });

    await openEditModal(page, targetCard);

    // THE regression signal: scope-aware edit must show the MMR field.
    await expect(page.locator('[data-testid="edit-user-mmr"]')).toBeVisible({ timeout: 5000 });

    const originalMmr = await readEditField(page, 'mmr');
    const newMmr = originalMmr === '9999' ? '8888' : '9999'; // guaranteed != current so save fires
    await fillEditField(page, 'mmr', newMmr);
    await saveEditModal(page);

    await expect(targetCard.getByText(newMmr).first()).toBeVisible({ timeout: 10000 });

    await restoreUserField(page, targetCard, 'mmr', originalMmr);
  });
});
