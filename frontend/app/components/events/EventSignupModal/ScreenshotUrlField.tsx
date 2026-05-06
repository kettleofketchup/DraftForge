'use client';
import { type Control } from 'react-hook-form';
import { FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage } from '~/components/ui/form';
import { Input } from '~/components/ui/input';

type Props = {
  control: Control;
  name?: 'rank_screenshot' | 'battlecup_screenshot';
  label?: string;
};

export function ScreenshotUrlField({
  control,
  name = 'rank_screenshot',
  label = 'MMR Screenshot URL',
}: Props) {
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <FormControl>
            <Input
              {...field}
              type="url"
              inputMode="url"
              data-testid="signup-screenshot-url"
              placeholder="https://i.imgur.com/your-screenshot.png"
            />
          </FormControl>
          <FormDescription>
            Upload your screenshot to imgur.com and paste the link here.
          </FormDescription>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
