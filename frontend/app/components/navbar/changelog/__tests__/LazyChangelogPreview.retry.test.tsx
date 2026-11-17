// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LazyChangelogPreview } from '../LazyChangelogPreview';

const loads = vi.hoisted(() => ({ count: 0 }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('../ChangelogPreview', () => {
  loads.count += 1;
  if (loads.count === 1) throw new Error('chunk gone');
  return { default: () => <p>loaded preview</p> };
});

describe('LazyChangelogPreview after a failed chunk load', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('retries the import on the next mount', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const view = () => (
      <MemoryRouter>
        <LazyChangelogPreview data-testid="p" />
      </MemoryRouter>
    );
    const first = render(view());
    expect(await screen.findByText('nav.changelog_load_error')).toBeTruthy();
    first.unmount();

    render(view());
    expect(await screen.findByText('loaded preview')).toBeTruthy();
  });
});
