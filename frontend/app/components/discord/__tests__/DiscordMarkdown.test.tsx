// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { DiscordMarkdown } from '../DiscordMarkdown';
import { formatDiscordTimestamp } from '../timestamps';

const EPOCH = 1794704400;
const OPTS = {
  locale: 'en-US',
  timeZone: 'America/Chicago',
  now: new Date((EPOCH - 3 * 3600) * 1000),
};

describe('DiscordMarkdown', () => {
  it('renders a resolved role pill with its name', () => {
    render(
      <DiscordMarkdown
        text="Hey <@&123456789>"
        resolve={{
          roles: { '123456789': { name: 'Inhouse', color: 0xff0000 } },
        }}
        options={OPTS}
      />,
    );
    const pill = screen.getByText('@Inhouse');
    expect(pill).toHaveAttribute('title', '123456789');
    expect(pill.style.getPropertyValue('--role-color')).toBe('#ff0000');
  });

  it('renders an unresolved role pill with a shortened id and the full id as title', () => {
    render(<DiscordMarkdown text="<@&1234567890123>" options={OPTS} />);
    const pill = screen.getByText('@role:1234…');
    expect(pill).toHaveAttribute('title', '1234567890123');
  });

  it('renders users and channels from the resolver, unknown users with their id', () => {
    render(
      <DiscordMarkdown
        text="<@1> <@2> <#3> <#9999999>"
        resolve={{ users: { '1': 'Alice' }, channels: { '3': 'general' } }}
        options={OPTS}
      />,
    );
    expect(screen.getByText('@Alice')).toBeInTheDocument();
    expect(screen.getByText('@user:2')).toBeInTheDocument();
    expect(screen.getByText('#general')).toBeInTheDocument();
    expect(screen.getByText('#channel:9999…')).toHaveAttribute(
      'title',
      '9999999',
    );
  });

  it('resolved names are plain text, never parsed', () => {
    const { container } = render(
      <DiscordMarkdown
        text="<@1>"
        resolve={{ users: { '1': '__Alice__ <@&1>' } }}
        options={OPTS}
      />,
    );
    expect(screen.getByText('@__Alice__ <@&1>')).toBeInTheDocument();
    expect(container.querySelector('u')).toBeNull();
  });

  it('renders <t:N:F> as a <time> in the given locale and zone', () => {
    const { container } = render(
      <DiscordMarkdown text={`Starts <t:${EPOCH}:F>`} options={OPTS} />,
    );
    const time = container.querySelector('time');
    expect(time).not.toBeNull();
    expect(time).toHaveAttribute(
      'dateTime',
      new Date(EPOCH * 1000).toISOString(),
    );
    expect(time?.textContent).toBe(
      new Intl.DateTimeFormat('en-US', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        timeZone: 'America/Chicago',
      }).format(new Date(EPOCH * 1000)),
    );
    expect(time?.getAttribute('title')).toBe(
      formatDiscordTimestamp(EPOCH, 'F', OPTS),
    );
  });

  it('renders R as relative time', () => {
    render(<DiscordMarkdown text={`<t:${EPOCH}:R>`} options={OPTS} />);
    expect(screen.getByText('in 3 hours')).toBeInTheDocument();
  });

  it('links open safely in a new tab', () => {
    render(
      <DiscordMarkdown text="[Sign up](https://x.test/e/1)" options={OPTS} />,
    );
    const link = screen.getByRole('link', { name: 'Sign up' });
    expect(link).toHaveAttribute('href', 'https://x.test/e/1');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer nofollow');
  });

  it('a javascript: link renders as text', () => {
    render(<DiscordMarkdown text="[x](javascript:alert(1))" options={OPTS} />);
    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.getByText('[x](javascript:alert(1))')).toBeInTheDocument();
  });

  it('never injects HTML', () => {
    const { container } = render(
      <DiscordMarkdown
        text={'<img src=x onerror=alert(1)> Snacks &amp; drinks'}
        options={OPTS}
      />,
    );
    expect(container.innerHTML).not.toContain('<img');
    expect(container.textContent).toContain('Snacks &amp; drinks');
  });

  it('renders formatting elements', () => {
    const { container } = render(
      <DiscordMarkdown
        text={'**b** *i* __u__ ~~s~~ `c`\n> q\n- li\n# H\n-# sub'}
        options={OPTS}
      />,
    );
    expect(container.querySelector('strong')?.textContent).toBe('b');
    expect(container.querySelector('em')?.textContent).toBe('i');
    expect(container.querySelector('u')?.textContent).toBe('u');
    expect(container.querySelector('s')?.textContent).toBe('s');
    expect(container.querySelector('code')?.textContent).toBe('c');
    expect(container.querySelector('blockquote')?.textContent).toBe('q');
    expect(container.querySelector('ul li')?.textContent).toBe('li');
    expect(screen.getByText('H')).toHaveAttribute('data-heading', '1');
    expect(screen.getByText('sub')).toHaveAttribute('data-subtext');
  });

  it('labels spoilers', () => {
    render(<DiscordMarkdown text="||secret||" options={OPTS} />);
    expect(screen.getByText('secret')).toHaveAttribute('title', 'Spoiler');
  });
});
