'use client';
import { type Control } from 'react-hook-form';
import { GAME_TYPE } from '~/components/game/constants';
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';

type Props = { control: Control; gameType: number };

const DOTA_COPY = {
  label: 'Dota 2 Friend ID',
  placeholder: 'Your Friend ID (number from your Dotabuff URL)',
};

const STEAM_COPY = {
  label: 'Steam Friend ID',
  placeholder: 'Your Steam Friend Code (Friends > Add a Friend)',
};

export function FriendIdField({ control, gameType }: Props) {
  const copy = gameType === GAME_TYPE.DOTA2 ? DOTA_COPY : STEAM_COPY;
  return (
    <FormField
      control={control}
      name="unverified_friend_id"
      render={({ field }) => (
        <FormItem>
          <FormLabel>{copy.label}</FormLabel>
          <FormControl>
            <Input
              {...field}
              data-testid="signup-friend-id"
              inputMode="numeric"
              pattern="[0-9]*"
              placeholder={copy.placeholder}
            />
          </FormControl>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
