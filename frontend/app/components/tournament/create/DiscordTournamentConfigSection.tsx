import type { Control } from 'react-hook-form';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
} from '~/components/ui/form';
import { DiscordIcon } from '~/components/events/DiscordConfigSection';
import type { CreateTournamentInput } from '../schemas';

interface Props {
  control: Control<CreateTournamentInput>;
}

export function DiscordTournamentConfigSection({ control }: Props) {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 mb-2">
        <DiscordIcon className="h-5 w-5 text-[#5865F2]" />
        <h3 className="text-sm font-semibold">Discord Notifications</h3>
      </div>
      <p className="text-muted-foreground text-xs mb-4">
        All Discord notifications are disabled by default.
      </p>
      <div className="rounded-md border border-border p-3 space-y-3">
        <FormField
          control={control}
          name="discord_send_draft_link"
          render={({ field }) => (
            <FormItem className="flex items-center gap-3">
              <FormControl>
                <input
                  type="checkbox"
                  data-testid="discord-discord_send_draft_link"
                  checked={field.value}
                  onChange={field.onChange}
                  className="h-4 w-4 rounded border-border accent-primary"
                />
              </FormControl>
              <div>
                <FormLabel className="text-sm font-medium cursor-pointer">
                  Send draft link on team draft start
                </FormLabel>
                <FormDescription>
                  DM captains and participants their draft link when the team draft begins
                </FormDescription>
              </div>
            </FormItem>
          )}
        />
      </div>
      <div className="rounded-md border border-border p-3 space-y-3">
        <FormField
          control={control}
          name="discord_send_herodraft_link"
          render={({ field }) => (
            <FormItem className="flex items-center gap-3">
              <FormControl>
                <input
                  type="checkbox"
                  data-testid="discord-discord_send_herodraft_link"
                  checked={field.value}
                  onChange={field.onChange}
                  className="h-4 w-4 rounded border-border accent-primary"
                />
              </FormControl>
              <div>
                <FormLabel className="text-sm font-medium cursor-pointer">
                  Send hero draft link on creation
                </FormLabel>
                <FormDescription>
                  DM team members their hero draft link when a hero draft is created for their match
                </FormDescription>
              </div>
            </FormItem>
          )}
        />
      </div>
    </div>
  );
}
