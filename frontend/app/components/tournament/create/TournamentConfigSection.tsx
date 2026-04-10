import type { Control } from 'react-hook-form';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
} from '~/components/ui/form';
import type { CreateTournamentInput } from '../schemas';

interface Props {
  control: Control<CreateTournamentInput>;
}

export function TournamentConfigSection({ control }: Props) {
  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold">Tournament Automation</h3>
      <div className="rounded-md border border-border p-3 space-y-3">
        <FormField
          control={control}
          name="auto_create_hero_drafts"
          render={({ field }) => (
            <FormItem className="flex items-center gap-3">
              <FormControl>
                <input
                  type="checkbox"
                  data-testid="config-auto-create-herodrafts"
                  checked={field.value}
                  onChange={field.onChange}
                  className="h-4 w-4 rounded border-border accent-primary"
                />
              </FormControl>
              <div>
                <FormLabel className="text-sm font-medium cursor-pointer">
                  Auto-create hero drafts
                </FormLabel>
                <FormDescription>
                  Automatically create hero drafts for matches when both teams are assigned
                </FormDescription>
              </div>
            </FormItem>
          )}
        />
      </div>
    </div>
  );
}
