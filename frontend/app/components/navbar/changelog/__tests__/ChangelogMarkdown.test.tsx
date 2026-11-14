// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { ChangelogMarkdown } from '../ChangelogMarkdown';

describe('ChangelogMarkdown', () => {
  afterEach(cleanup);

  it('drops HTML comments and raw HTML', () => {
    const { container } = render(
      <ChangelogMarkdown
        markdown={'<!-- hidden -->\n\nhi <b>bold</b>'}
        headingOffset={0}
      />,
    );
    expect(container.innerHTML).not.toContain('<!--');
    expect(container.innerHTML).not.toContain('<b>');
    expect(container.textContent).not.toContain('hidden');
  });

  it('opens absolute http(s) links in a new tab', () => {
    render(
      <ChangelogMarkdown markdown="[a](https://x.test)" headingOffset={0} />,
    );
    const link = screen.getByRole('link', { name: 'a' });
    expect(link.getAttribute('target')).toBe('_blank');
    expect(link.getAttribute('rel')).toBe('noopener noreferrer');
  });

  it('keeps relative and anchor links in the same tab', () => {
    render(
      <ChangelogMarkdown
        markdown="[r](/changelog) [h](#top)"
        headingOffset={0}
      />,
    );
    for (const name of ['r', 'h']) {
      const link = screen.getByRole('link', { name });
      expect(link.hasAttribute('target')).toBe(false);
      expect(link.hasAttribute('rel')).toBe(false);
    }
  });

  it('neutralises javascript: hrefs', () => {
    const { container } = render(
      <ChangelogMarkdown
        markdown="[x](javascript:alert(1))"
        headingOffset={0}
      />,
    );
    const hrefs = Array.from(container.querySelectorAll('[href]')).map(
      (el) => el.getAttribute('href') ?? '',
    );
    expect(
      hrefs.some((h) => h.trim().toLowerCase().startsWith('javascript:')),
    ).toBe(false);
  });

  it('shifts heading levels by headingOffset', () => {
    render(<ChangelogMarkdown markdown="### Fixed" headingOffset={1} />);
    expect(
      screen.getByRole('heading', { level: 4, name: 'Fixed' }),
    ).toBeTruthy();
    cleanup();
    render(<ChangelogMarkdown markdown="### Fixed" headingOffset={0} />);
    expect(
      screen.getByRole('heading', { level: 3, name: 'Fixed' }),
    ).toBeTruthy();
  });

  it('caps shifted headings at h6', () => {
    render(<ChangelogMarkdown markdown="##### Deep" headingOffset={3} />);
    expect(
      screen.getByRole('heading', { level: 6, name: 'Deep' }),
    ).toBeTruthy();
  });

  it('lets long inline code wrap', () => {
    const { container } = render(
      <ChangelogMarkdown
        markdown={'`127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16`'}
        headingOffset={0}
      />,
    );
    expect(container.querySelector('code')?.className).toContain('break-all');
  });
});
