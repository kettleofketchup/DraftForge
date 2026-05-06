'use client';
import { type Control } from 'react-hook-form';
import { FormField, FormItem, FormLabel, FormControl, FormMessage } from '~/components/ui/form';
import { Input } from '~/components/ui/input';

type Props = { control: Control };

export function FriendIdField({ control }: Props) {
  return (
    <FormField
      control={control}
      name="unverified_friend_id"
      render={({ field }) => (
        <FormItem>
          <FormLabel>Dota 2 Friend ID</FormLabel>
          <FormControl>
            <Input
              {...field}
              data-testid="signup-friend-id"
              inputMode="numeric"
              pattern="[0-9]*"
              placeholder="Your Friend ID (number from your Dotabuff URL)"
            />
          </FormControl>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
