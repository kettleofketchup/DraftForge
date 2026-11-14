import { BASE_URL } from '../fixtures/base-url';
import { test, expect } from '../fixtures';

// nginx caches SSR HTML. /events reads ?organization= during SSR, so a cache
// key without the query string serves one variant's HTML for the other.
test.describe.configure({ retries: 0 });

const DOCUMENT_HEADERS = {
  Accept: 'text/html',
  'Sec-Fetch-Dest': 'document',
  'Sec-Fetch-Mode': 'navigate',
  'Sec-Fetch-Site': 'none',
  // Without a df-locale cookie the response sets one and nginx skips caching it.
  Cookie: 'df-locale=en',
};
const ORG_FILTER_LABEL = /data-testid="events-org-filter"[^>]*><span class="truncate">([^<]*)</;

test.describe('SSR cache key includes the query string', () => {
  test('a ?organization= render is not served for plain /events', async ({ request }) => {
    const filtered = `${BASE_URL}/events?organization=7`;
    await request.get(filtered, { headers: DOCUMENT_HEADERS });
    const cached = await request.get(filtered, { headers: DOCUMENT_HEADERS });
    expect(cached.headers()['x-cache-status'], 'SSR cache must be active for this check').toBe('HIT');
    expect((await cached.text()).match(ORG_FILTER_LABEL)?.[1]).toBe('Org');

    const plain = await request.get(`${BASE_URL}/events`, { headers: DOCUMENT_HEADERS });
    expect((await plain.text()).match(ORG_FILTER_LABEL)?.[1]).toBe('All');
  });

  test('navigating to /events after a filtered visit hydrates cleanly', async ({ page }) => {
    const hydrationErrors: string[] = [];
    page.on('pageerror', (e) => {
      if (/hydrat/i.test(e.message)) hydrationErrors.push(e.message);
    });
    page.on('console', (m) => {
      if (m.type() === 'error' && /hydrat/i.test(m.text())) hydrationErrors.push(m.text());
    });

    await page.goto('/events?organization=7');
    await page.goto('/events?organization=7');
    const response = await page.goto('/events');
    expect(response?.status()).toBe(200);
    await expect(page.getByTestId('events-org-filter').first()).toContainText('All');
    expect(hydrationErrors).toEqual([]);
  });
});
