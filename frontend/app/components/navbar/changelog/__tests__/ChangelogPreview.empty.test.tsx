// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LazyChangelogPreview } from '../LazyChangelogPreview';

const { EMPTY } = vi.hoisted(() => ({
  EMPTY: '# Changelog\n\n## [Unreleased]\n',
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('~/data/CHANGELOG.md?raw', () => ({ default: EMPTY }));

describe('LazyChangelogPreview with no releases', () => {
  afterEach(cleanup);

  it('shows the empty message and no release sections', async () => {
    const { container } = render(
      <MemoryRouter>
        <LazyChangelogPreview data-testid="p" />
      </MemoryRouter>,
    );
    expect(await screen.findByText('nav.changelog_empty')).toBeTruthy();
    expect(container.querySelector('section')).toBeNull();
  });
});
