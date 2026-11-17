// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LazyChangelogPreview } from '../LazyChangelogPreview';

const PAGE_TEXT = 'page';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('../ChangelogPreview', () => {
  throw new Error('chunk gone');
});

describe('LazyChangelogPreview when the chunk fails to load', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('shows the load error with a working full changelog link', async () => {
    const spy = vi.fn();
    render(
      <MemoryRouter>
        <div>
          <span>{PAGE_TEXT}</span>
          <LazyChangelogPreview data-testid="p" onNavigate={spy} />
        </div>
      </MemoryRouter>,
    );
    expect(await screen.findByText('nav.changelog_load_error')).toBeTruthy();
    expect(screen.getByText(PAGE_TEXT)).toBeTruthy();
    expect(screen.getByTestId('p')).toBeTruthy();
    const link = screen.getByRole('link', { name: 'nav.full_changelog' });
    expect(link.getAttribute('href')).toBe('/changelog');
    fireEvent.click(link);
    expect(spy).toHaveBeenCalledTimes(1);
  });
});
