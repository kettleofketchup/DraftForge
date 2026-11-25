// @vitest-environment jsdom
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { DiscordMessagePreview } from '../DiscordMessagePreview';
import { DiscordScheduledEventCard } from '../DiscordScheduledEventCard';
import type { DiscordMessageInput } from '../messageInput';
import { formatDiscordTimestamp } from '../timestamps';

const EPOCH = 1794704400;
const OPTS = {
  locale: 'en-US',
  timeZone: 'America/Chicago',
  now: new Date((EPOCH - 3 * 3600) * 1000),
};

function renderMessages(
  messages: DiscordMessageInput[],
  extra: Partial<Parameters<typeof DiscordMessagePreview>[0]> = {},
) {
  return render(
    <DiscordMessagePreview messages={messages} options={OPTS} {...extra} />,
  );
}

describe('DiscordMessagePreview: header', () => {
  it('renders content with no header when author is omitted', () => {
    const { container } = renderMessages([{ content: 'x' }]);
    expect(screen.getByText('x')).toBeInTheDocument();
    expect(
      container.querySelector('[data-testid="discord-message-author"]'),
    ).toBeNull();
    expect(screen.queryByText('APP')).toBeNull();
  });

  it('renders name and avatar slots without APP for a non-bot author', () => {
    renderMessages([{ content: 'x' }], {
      author: {
        name: <span>Alice</span>,
        avatar: <span data-testid="avatar-slot" />,
        bot: false,
      },
    });
    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByTestId('avatar-slot')).toBeInTheDocument();
    expect(screen.queryByText('APP')).toBeNull();
  });

  it('shows the APP tag for a bot author', () => {
    renderMessages([{ content: 'x' }], {
      author: { name: 'DraftForge', bot: true },
    });
    expect(screen.getByText('APP')).toBeInTheDocument();
  });

  it('renders the reply reference label', () => {
    renderMessages([{ content: 'x' }], { replyTo: 'Signup post' });
    expect(screen.getByTestId('discord-reply')).toHaveTextContent(
      'Signup post',
    );
  });
});

describe('DiscordMessagePreview: unsafe urls', () => {
  it('renders javascript:/data: urls as plain text, not anchors', () => {
    const { container } = renderMessages([
      {
        embeds: [
          {
            title: 'Evil title',
            url: 'javascript:alert(1)',
            author: { name: 'Evil author', url: 'data:text/html,x' },
          },
        ],
        components: [
          {
            type: 1,
            components: [
              { type: 2, style: 5, label: 'Evil link', url: 'javascript:x' },
            ],
          },
        ],
      },
    ]);
    expect(container.querySelectorAll('a')).toHaveLength(0);
    expect(screen.getByText('Evil title')).toBeInTheDocument();
    expect(screen.getByText('Evil author')).toBeInTheDocument();
    expect(screen.getByText('Evil link')).toBeInTheDocument();
  });

  it('links safe embed title and author urls', () => {
    renderMessages([
      {
        embeds: [
          {
            title: 'Event',
            url: 'https://example.com/e',
            author: { name: 'Org', url: 'https://example.com/o' },
          },
        ],
      },
    ]);
    expect(screen.getByText('Event').closest('a')).toHaveAttribute(
      'href',
      'https://example.com/e',
    );
    expect(screen.getByText('Org').closest('a')).toHaveAttribute(
      'href',
      'https://example.com/o',
    );
  });
});

describe('DiscordMessagePreview: embeds', () => {
  it('groups up to three inline fields per row and breaks on a non-inline field', () => {
    renderMessages([
      {
        embeds: [
          {
            fields: [
              { name: 'A', value: '1', inline: true },
              { name: 'B', value: '2', inline: true },
              { name: 'C', value: '3', inline: true },
              { name: 'D', value: '4', inline: true },
              { name: 'E', value: '5', inline: false },
              { name: 'F', value: '6', inline: true },
            ],
          },
        ],
      },
    ]);
    const rows = screen.getAllByTestId('discord-embed-field-row');
    expect(rows.map((r) => r.children.length)).toEqual([3, 1, 1, 1]);
    expect(within(rows[0]).getByText('A')).toBeInTheDocument();
    expect(within(rows[2]).getByText('E')).toBeInTheDocument();
  });

  it('sets --embed-color from the embed colour', () => {
    renderMessages([{ embeds: [{ title: 't', color: 0x5865f2 }] }]);
    const embed = screen.getByTestId('discord-embed');
    expect(embed.style.getPropertyValue('--embed-color')).toBe('#5865f2');
  });

  it('omits --embed-color when there is no colour', () => {
    renderMessages([{ embeds: [{ title: 't' }] }]);
    const embed = screen.getByTestId('discord-embed');
    expect(embed.style.getPropertyValue('--embed-color')).toBe('');
  });

  it('renders author, footer with safe icon, timestamp and thumbnail', () => {
    const { container } = renderMessages([
      {
        embeds: [
          {
            author: { name: 'Org', icon_url: 'https://cdn.test/a.png' },
            description: '**Bold** text',
            footer: { text: 'Footer', icon_url: 'http://cdn.test/f.png' },
            timestamp: new Date(EPOCH * 1000).toISOString(),
            thumbnail: { url: 'https://cdn.test/t.png' },
            image: { url: 'javascript:alert(1)' },
          },
        ],
      },
    ]);
    expect(screen.getByText('Org')).toBeInTheDocument();
    expect(screen.getByText('Bold').tagName).toBe('STRONG');
    const footer = screen.getByTestId('discord-embed-footer');
    expect(footer).toHaveTextContent('Footer');
    expect(footer).toHaveTextContent(formatDiscordTimestamp(EPOCH, 'f', OPTS));
    const srcs = Array.from(container.querySelectorAll('img')).map((i) =>
      i.getAttribute('src'),
    );
    expect(srcs).toEqual(['https://cdn.test/a.png', 'https://cdn.test/t.png']);
    const thumb = screen.getByTestId('discord-embed-thumbnail');
    expect(thumb).toHaveAttribute('referrerpolicy', 'no-referrer');
    expect(thumb).toHaveAttribute('loading', 'lazy');
  });
});

describe('DiscordMessagePreview: components', () => {
  const row: DiscordMessageInput = {
    components: [
      {
        type: 1,
        components: [
          { type: 2, style: 1, label: 'Primary', custom_id: 'p' },
          { type: 2, style: 2, label: 'Secondary', custom_id: 's' },
          { type: 2, style: 3, label: 'Success', custom_id: 'ok' },
          { type: 2, style: 4, label: 'Danger', custom_id: 'd' },
          { type: 2, style: 5, label: 'Link', url: 'https://example.com' },
          { type: 2, style: 6, label: 'Premium' },
        ],
      },
    ],
  };

  it('renders button styles 1-5 and hides premium', () => {
    renderMessages([row]);
    const style = (label: string) =>
      screen.getByText(label).closest('[data-style]');
    expect(style('Primary')).toHaveAttribute('data-style', '1');
    expect(style('Primary')?.className).toContain('bg-discord');
    expect(style('Secondary')?.className).toContain('bg-base-700');
    expect(style('Success')?.className).toContain('bg-success');
    expect(style('Danger')?.className).toContain('bg-destructive');
    expect(screen.queryByText('Premium')).toBeNull();
  });

  it('renders the link button as a non-interactive external anchor', () => {
    renderMessages([row]);
    const link = screen.getByText('Link').closest('a');
    expect(link).toHaveAttribute('href', 'https://example.com');
    expect(link).toHaveAttribute('aria-disabled', 'true');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer nofollow');
    expect(
      link?.querySelector('[data-testid="discord-external-icon"]'),
    ).not.toBeNull();
    const click = new MouseEvent('click', { bubbles: true, cancelable: true });
    link?.dispatchEvent(click);
    expect(click.defaultPrevented).toBe(true);
  });

  it('marks non-link buttons disabled and inert', () => {
    renderMessages([row]);
    const primary = screen.getByRole('button', { name: 'Primary' });
    expect(primary).toHaveAttribute('aria-disabled', 'true');
  });

  it('renders a disabled select menu with its placeholder', () => {
    renderMessages([
      {
        components: [
          {
            type: 1,
            components: [
              {
                type: 3,
                custom_id: 'pick',
                placeholder: 'Pick a role',
                options: [{ label: 'A', value: 'a' }],
              },
            ],
          },
        ],
      },
    ]);
    const select = screen.getByRole('combobox');
    expect(select).toHaveAttribute('aria-disabled', 'true');
    expect(select).toHaveTextContent('Pick a role');
  });

  it('renders a V2 container with accent, section thumbnail and text display', () => {
    const { container } = renderMessages([
      {
        flags: 1 << 15,
        components: [
          {
            type: 17,
            accent_color: 0x00ff00,
            components: [
              {
                type: 9,
                components: [{ type: 10, content: '## Friday Inhouse' }],
                accessory: {
                  type: 11,
                  media: { url: 'https://cdn.test/logo.png' },
                },
              },
              { type: 14, divider: true },
              { type: 10, content: 'Signed **up**' },
              {
                type: 1,
                components: [
                  { type: 2, style: 3, label: 'Sign Up', custom_id: 'su' },
                ],
              },
            ],
          },
        ],
      },
    ]);
    const box = screen.getByTestId('discord-container');
    expect(box.style.getPropertyValue('--accent-color')).toBe('#00ff00');
    expect(within(box).getByText('Friday Inhouse')).toHaveAttribute(
      'data-heading',
      '2',
    );
    expect(within(box).getByText('up').tagName).toBe('STRONG');
    expect(within(box).getByRole('button', { name: 'Sign Up' })).toBeVisible();
    expect(container.querySelector('img')).toHaveAttribute(
      'src',
      'https://cdn.test/logo.png',
    );
    expect(within(box).getByRole('separator')).toBeInTheDocument();
  });
});

describe('DiscordMessagePreview: mentions and timestamps', () => {
  it('renders resolved and unresolved mention pills', () => {
    renderMessages([{ content: '<@&11> <@&99999999> <#21> <@9>' }], {
      resolve: {
        roles: { '11': { name: 'Inhouse' } },
        channels: { '21': 'general' },
        users: { '9': 'Alice' },
      },
    });
    expect(screen.getByText('@Inhouse')).toBeInTheDocument();
    expect(screen.getByText('@role:9999…')).toHaveAttribute(
      'title',
      '99999999',
    );
    expect(screen.getByText('#general')).toBeInTheDocument();
    expect(screen.getByText('@Alice')).toBeInTheDocument();
  });

  it('renders a user name with markdown and mention syntax literally', () => {
    const { container } = renderMessages([{ content: 'Go <@9>' }], {
      resolve: { users: { '9': '__Alice__ <@&1>' } },
    });
    expect(screen.getByText('@__Alice__ <@&1>')).toBeInTheDocument();
    expect(container.querySelector('u')).toBeNull();
  });

  it('formats timestamps in the given locale and time zone', () => {
    renderMessages([{ content: `Starts <t:${EPOCH}:F> (<t:${EPOCH}:R>)` }]);
    expect(
      screen.getByText(formatDiscordTimestamp(EPOCH, 'F', OPTS)),
    ).toBeInTheDocument();
    expect(screen.getByText('in 3 hours')).toBeInTheDocument();
  });
});

describe('DiscordScheduledEventCard', () => {
  it('renders name, markdown description, location and start time', () => {
    render(
      <DiscordScheduledEventCard
        options={OPTS}
        event={{
          name: 'Friday Inhouse',
          description: 'Snacks &amp; **drinks**',
          scheduled_start_time: new Date(EPOCH * 1000).toISOString(),
          scheduled_end_time: null,
          entity_metadata: { location: 'https://example.com/events/1' },
        }}
      />,
    );
    expect(screen.getByText('Friday Inhouse')).toBeInTheDocument();
    expect(screen.getByText('drinks').tagName).toBe('STRONG');
    expect(screen.getByText(/Snacks &amp;/)).toBeInTheDocument();
    expect(
      screen.getByText('https://example.com/events/1', { exact: false }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(formatDiscordTimestamp(EPOCH, 'F', OPTS)),
    ).toBeInTheDocument();
  });
});
