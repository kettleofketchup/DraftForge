// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { useForm, type UseFormReturn } from 'react-hook-form';
import { describe, expect, it } from 'vitest';
import type { z } from 'zod';

import { Form } from '~/components/ui/form';
import { ApprovalConfigSection } from '../ApprovalConfigSection';
import { DISCORD_CONFIG_DEFAULTS, type discordConfigSchema } from '../schemas';

type ApprovalFields = z.input<typeof discordConfigSchema>;

let form: UseFormReturn<ApprovalFields>;

function Harness() {
  form = useForm<ApprovalFields>({
    defaultValues: {
      ...DISCORD_CONFIG_DEFAULTS,
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
  it('offers the rank screenshot requirement only under Active MMR', () => {
    render(<Harness />);

    expect(
      screen.getAllByRole('checkbox', { name: /screenshot/i }),
    ).toHaveLength(2);
    expect(
      screen.getByRole('checkbox', { name: /Require MMR screenshot/ }),
    ).toBeTruthy();
    expect(
      screen.queryByRole('checkbox', { name: /Require rank screenshot/ }),
    ).toBeNull();
  });

  it('ticking Require MMR screenshot leaves no other box checked', () => {
    render(<Harness />);

    fireEvent.click(
      screen.getByRole('checkbox', { name: /Require MMR screenshot/ }),
    );

    expect(form.getValues('discord_require_rank_screenshot')).toBe(true);
    const checked = screen
      .getAllByRole('checkbox', { name: /screenshot/i })
      .filter((el) => (el as HTMLInputElement).checked);
    expect(checked).toHaveLength(1);
  });
});
