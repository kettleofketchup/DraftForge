/**
 * Test Constants
 *
 * Shared constants for Playwright tests.
 */

export const DOCKER_HOST = process.env.DOCKER_HOST || 'nginx';
export const BASE_URL = `https://${DOCKER_HOST}`;
export const API_URL = `${BASE_URL}/api`;
