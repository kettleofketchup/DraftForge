// @vitest-environment jsdom
import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ChangelogPage } from '../changelog';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('~/data/CHANGELOG.md?raw', async () => ({
  default: (await import('~/lib/__tests__/changelog-fixture'))
    .CHANGELOG_FIXTURE,
}));

afterEach(cleanup);

describe('ChangelogPage', () => {
  it('renders the page heading', () => {
    render(<ChangelogPage />);
    expect(
      screen.getByRole('heading', { level: 1, name: 'nav.changelog' }),
    ).toBeTruthy();
  });

  it('renders one section per release, oldest included', () => {
    render(<ChangelogPage />);
    const sections = screen.getAllByTestId('changelog-release');
    expect(sections).toHaveLength(3);
    expect(
      screen.getByRole('heading', { level: 2, name: /1\.0\.0/ }),
    ).toBeTruthy();
  });

  it('renders release body headings as h3', () => {
    render(<ChangelogPage />);
    const [latest] = screen.getAllByTestId('changelog-release');
    expect(
      within(latest).getByRole('heading', { level: 3, name: 'Fixed' }),
    ).toBeTruthy();
  });
});
