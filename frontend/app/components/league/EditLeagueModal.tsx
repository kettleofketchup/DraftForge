import { zodResolver } from '@hookform/resolvers/zod';
import { useEffect, useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { toast } from 'sonner';

import { AdminTeamSection } from '~/components/admin-team';
import { useUpdateLeagueMutation } from '~/components/league/hooks/useUpdateLeagueMutation';
import { FormDialog } from '~/components/ui/dialogs';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import { Textarea } from '~/components/ui/textarea';
import { useIsLeagueAdmin } from '~/hooks/usePermissions';
import { extractApiError } from '~/lib/apiError';
import { EditLeagueSchema, type EditLeagueInput, type LeagueType } from './schemas';

interface EditLeagueModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  league: LeagueType;
  onSuccess?: () => void;
}

export function EditLeagueModal({
  open,
  onOpenChange,
  league,
  onSuccess,
}: EditLeagueModalProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const isLeagueAdmin = useIsLeagueAdmin(league);

  const form = useForm<EditLeagueInput>({
    resolver: zodResolver(EditLeagueSchema),
    defaultValues: {
      steam_league_id: league.steam_league_id,
      name: league.name || '',
      description: league.description || '',
      rules: league.rules || '',
      prize_pool: league.prize_pool || '',
    },
  });

  // Reset form when league changes or modal opens
  useEffect(() => {
    if (open) {
      form.reset({
        steam_league_id: league.steam_league_id,
        name: league.name || '',
        description: league.description || '',
        rules: league.rules || '',
        prize_pool: league.prize_pool || '',
      });
    }
  }, [open, league, form]);

  const updateMutation = useUpdateLeagueMutation(league.pk ?? 0);

  async function onSubmit(data: EditLeagueInput) {
    if (isSubmitting || !league.pk) return;
    setIsSubmitting(true);

    try {
      await updateMutation.mutateAsync(data);
      toast.success('League updated successfully');
      onOpenChange(false);
      onSuccess?.();
    } catch (err) {
      const message =
        extractApiError(err) ??
        (err instanceof Error ? err.message : 'Failed to update league');
      toast.error(message);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Edit League"
      description="Update league information."
      submitLabel="Save Changes"
      isSubmitting={isSubmitting}
      onSubmit={form.handleSubmit(onSubmit)}
      size="xl"
      data-testid="edit-league-modal"
      titleTestId="edit-league-modal-heading"
    >
      <Form {...form}>
        <Controller
          control={form.control}
          name="steam_league_id"
          render={({ field, fieldState }) => (
            <FormItem>
              <FormLabel>Steam League ID (optional)</FormLabel>
              <FormControl>
                <Input
                  type="number"
                  placeholder="Leave blank if this league has no Steam ID"
                  data-testid="edit-league-steam-id"
                  value={field.value ?? ''}
                  onChange={(e) =>
                    field.onChange(
                      e.target.value ? parseInt(e.target.value, 10) : null,
                    )
                  }
                />
              </FormControl>
              {fieldState.error && (
                <FormMessage>{fieldState.error.message}</FormMessage>
              )}
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>League Name</FormLabel>
              <FormControl>
                <Input
                  placeholder="Enter league name"
                  data-testid="league-name-input"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="prize_pool"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Prize Pool</FormLabel>
              <FormControl>
                <Input
                  placeholder="e.g., $1,000"
                  data-testid="league-prize-input"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="description"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Description</FormLabel>
              <FormControl>
                <Textarea
                  placeholder="League description..."
                  rows={4}
                  data-testid="league-description-input"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="rules"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Rules</FormLabel>
              <FormControl>
                <Textarea
                  placeholder="League rules..."
                  rows={6}
                  data-testid="league-rules-input"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

      </Form>

      {/* Admin Team Section - outside Form to prevent button clicks from submitting the league edit form */}
      {isLeagueAdmin && (
        <AdminTeamSection
          league={league}
          onUpdate={onSuccess}
        />
      )}
    </FormDialog>
  );
}
