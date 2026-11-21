'use client';
import { type Control } from 'react-hook-form';
import { GAME_TYPE } from '~/components/game/constants';
import { Badge } from '~/components/ui/badge';
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
      name="steam_account_id"
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

type ReadOnlyProps = { friendId: string; gameType: number };

/** The user's stored Friend ID; a signup cannot change it. */
export function FriendIdReadOnly({ friendId, gameType }: ReadOnlyProps) {
  const copy = gameType === GAME_TYPE.DOTA2 ? DOTA_COPY : STEAM_COPY;
  return (
    <div
      data-testid="signup-prefilled-summary-friend-id"
      className="flex min-h-11 items-center justify-between gap-2 rounded-md border border-border bg-base-200 px-3 py-2"
    >
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground">{copy.label}</span>
        <Badge variant="secondary">{friendId}</Badge>
      </div>
      <span className="text-xs text-muted-foreground">
        Contact an admin to change it
      </span>
    </div>
  );
}
