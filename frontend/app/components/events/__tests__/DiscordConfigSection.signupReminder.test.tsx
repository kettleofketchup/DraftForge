// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { useForm } from 'react-hook-form';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import type { z } from 'zod';

import { Form } from '~/components/ui/form';
import { DiscordConfigSection } from '../DiscordConfigSection';
import { EVENT_SECTION_FIELDS } from '../form/settingsFields';
import type { discordConfigSchema } from '../schemas';
import { Wrapper } from './eventModalFixtures';

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  getDiscordChannels: vi.fn().mockResolvedValue([]),
  getDiscordRoles: vi.fn().mockResolvedValue([]),
}));

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
});

type SignupReminderValues = z.input<typeof discordConfigSchema>;

function Harness({ isRepeater }: { isRepeater: boolean }) {
  const form = useForm<SignupReminderValues>({
    defaultValues: {
      discord_signup_reminder: true,
      discord_signup_reminder_hours: 24,
    },
  });
  return (
    <Wrapper>
      <Form {...form}>
        <DiscordConfigSection
          control={form.control}
          isRepeater={isRepeater}
          organizationId={1}
        />
      </Form>
    </Wrapper>
  );
}

const meta = EVENT_SECTION_FIELDS.discord.discord_signup_reminder;

describe('DiscordConfigSection signup reminder', () => {
  it('shows the settings-search description for the signup reminder on a series', () => {
    render(<Harness isRepeater />);
    expect(screen.getByText('Send signup reminder')).toBeInTheDocument();
    expect(screen.getByText(meta.description!)).toBeInTheDocument();
    expect(meta.description).toMatch(/series subscribers/i);
  });

  it('hides the signup reminder when not a repeater', () => {
    render(<Harness isRepeater={false} />);
    expect(screen.queryByText('Send signup reminder')).not.toBeInTheDocument();
  });
});
