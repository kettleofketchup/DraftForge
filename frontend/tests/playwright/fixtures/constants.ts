/**
 * Test Constants
 *
 * Shared constants for Playwright tests.
 */

// Use localhost by default (matches playwright.config.ts baseURL)
// Can be overridden with DOCKER_HOST for running inside Docker containers
export const DOCKER_HOST = process.env.DOCKER_HOST || 'localhost';
export const BASE_URL = `https://${DOCKER_HOST}`;
export const API_URL = `${BASE_URL}/api`;
