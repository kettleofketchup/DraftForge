// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { OrganizationHeaderTitle } from '../OrganizationHeaderTitle';

afterEach(cleanup);

function classesOf(el: Element): string[] {
  return el.className.split(/\s+/);
}

describe('OrganizationHeaderTitle', () => {
  it('stacks the name above the action below sm and puts them in a row from sm up', () => {
    render(
      <OrganizationHeaderTitle
        name="Features Test Org"
        action={<button type="button">Org Settings</button>}
      />,
    );

    const row = screen.getByTestId('org-header-title');
    expect(classesOf(row)).toEqual(
      expect.arrayContaining([
        'flex',
        'flex-col',
        'items-start',
        'sm:flex-row',
        'sm:justify-between',
        'sm:gap-0',
      ]),
    );

    const heading = screen.getByRole('heading', {
      level: 1,
      name: 'Features Test Org',
    });
    expect(row.firstElementChild).toBe(heading);
    expect(row.lastElementChild).toBe(
      screen.getByRole('button', { name: 'Org Settings' }),
    );
  });

  it('lets the name take the full width on mobile and wrap at word boundaries', () => {
    render(<OrganizationHeaderTitle name="Features Test Org" />);

    const classes = classesOf(screen.getByRole('heading', { level: 1 }));
    expect(classes).toEqual(
      expect.arrayContaining(['w-full', 'sm:w-auto', 'min-w-0', 'break-words']),
    );
    expect(classes).not.toContain('wrap-anywhere');
    expect(classes).not.toContain('break-all');
  });

  it('renders only the name when there is no action', () => {
    render(<OrganizationHeaderTitle name="Features Test Org" />);

    expect(screen.getByTestId('org-header-title').children).toHaveLength(1);
  });
});
