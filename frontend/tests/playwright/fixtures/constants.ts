/**
 * Test Constants
 *
 * Shared constants for Playwright tests.
 */

export { API_URL, BASE_URL } from './base-url';

/** Mirrors backend/tests/populate/constants.py (populate_discord_name_sync_users). */
export const NAME_SYNC_USERNAME = 'name_sync_dragonclaw';
export const NAME_SYNC_GLOBAL_ONLY_USERNAME = 'name_sync_globalonly';

/** Mirrors backend/tests/populate/constants.py (populate_steam_verification_data). */
export const STEAM_VERIFY_EVENT_NAME = 'Steam Friend ID Verify Event';
export const STEAM_VERIFY_UNVERIFIED_USERNAME = 'steam_verify_unverified';
export const STEAM_VERIFY_UNVERIFIED_PK = 5101;
export const STEAM_VERIFY_UNVERIFIED_FRIEND_ID = 939924373;
export const STEAM_VERIFY_VERIFIED_USERNAME = 'steam_verify_verified';
export const STEAM_VERIFY_VERIFIED_PK = 5102;
export const STEAM_VERIFY_VERIFIED_FRIEND_ID = 939924374;
