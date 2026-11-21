// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { useForm, type UseFormReturn } from 'react-hook-form';
import { describe, expect, it } from 'vitest';
import type { z } from 'zod';

import { GAME_TYPE } from '~/components/game/constants';
import { Form } from '~/components/ui/form';
import { ApprovalConfigSection } from '../ApprovalConfigSection';
import { DISCORD_CONFIG_DEFAULTS, type discordConfigSchema } from '../schemas';

type ApprovalFields = z.input<typeof discordConfigSchema> & {
  game_type: number;
};

let form: UseFormReturn<ApprovalFields>;

function Harness() {
  form = useForm<ApprovalFields>({
    defaultValues: {
      ...DISCORD_CONFIG_DEFAULTS,
      game_type: GAME_TYPE.DOTA2,
      allow_active_mmr: true,
      allow_previous_rank: true,
    },
  });
  return (
    <Form {...form}>
      <ApprovalConfigSection control={form.control} watch={form.watch} />
    </Form>
  );
}

describe('ApprovalConfigSection rank screenshot', () => {
  it('gives active and previous ranks separate screenshot settings', () => {
    render(<Harness />);

    expect(
      screen.getAllByRole('checkbox', { name: /screenshot/i }),
    ).toHaveLength(3);
    expect(
      screen.getByRole('checkbox', { name: /Require MMR screenshot/ }),
    ).toBeTruthy();
    expect(
      screen.getByRole('checkbox', {
        name: /Require last ranked MMR screenshot/,
      }),
    ).toBeTruthy();
  });

  it.each([
    ['Require MMR screenshot', 'discord_require_rank_screenshot'],
    [
      'Require last ranked MMR screenshot',
      'discord_require_previous_rank_screenshot',
    ],
    ['Require battle cup screenshot', 'discord_require_battlecup_screenshot'],
  ] as const)('ticking %s ticks only its own setting', (label, field) => {
    render(<Harness />);

    fireEvent.click(screen.getByRole('checkbox', { name: new RegExp(label) }));

    expect(form.getValues(field)).toBe(true);
    const checked = screen
      .getAllByRole('checkbox', { name: /screenshot/i })
      .filter((el) => (el as HTMLInputElement).checked);
    expect(checked).toHaveLength(1);
  });
});
