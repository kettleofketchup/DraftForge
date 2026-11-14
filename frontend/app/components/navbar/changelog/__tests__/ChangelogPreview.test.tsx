// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LazyChangelogPreview } from '../LazyChangelogPreview';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('~/data/CHANGELOG.md?raw', async () => ({
  default: (await import('~/lib/__tests__/changelog-fixture'))
    .CHANGELOG_FIXTURE,
}));

describe('LazyChangelogPreview', () => {
  afterEach(cleanup);

  it('renders the two latest releases with shifted body headings', async () => {
    render(
      <MemoryRouter>
        <LazyChangelogPreview data-testid="p" />
      </MemoryRouter>,
    );
    expect(
      await screen.findByRole('heading', { level: 3, name: /2\.1\.0/ }),
    ).toBeTruthy();
    expect(
      screen.getByRole('heading', { level: 3, name: /2\.0\.0/ }),
    ).toBeTruthy();
    expect(screen.queryByRole('heading', { name: /1\.0\.0/ })).toBeNull();
    expect(
      screen.getByRole('heading', { level: 4, name: 'Fixed' }),
    ).toBeTruthy();
    expect(screen.getByTestId('p').querySelectorAll('section')).toHaveLength(2);
  });
});
