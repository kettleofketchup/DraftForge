import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
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
import { useCreateLeagueMutation } from '../hooks/useCreateLeagueMutation';
import { CreateLeagueSchema, type CreateLeagueInput } from '../schemas';

interface CreateLeagueModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  organizationId: number;
}

export function CreateLeagueModal({
  open,
  onOpenChange,
  organizationId,
}: CreateLeagueModalProps) {
  const createLeague = useCreateLeagueMutation(organizationId);
  const isSubmitting = createLeague.isPending;

  const form = useForm<CreateLeagueInput>({
    resolver: zodResolver(CreateLeagueSchema),
    defaultValues: {
      organization_id: organizationId,
      steam_league_id: null as number | null,
      name: '',
      description: '',
      rules: '',
    },
  });

  async function onSubmit(data: CreateLeagueInput) {
    if (isSubmitting) return;
    try {
      await createLeague.mutateAsync(data);
      toast.success('League created successfully');
      onOpenChange(false);
      form.reset();
    } catch {
      toast.error('Failed to create league');
    }
  }

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Create League"
      submitLabel="Create"
      isSubmitting={isSubmitting}
      onSubmit={form.handleSubmit(onSubmit)}
      size="md"
    >
      <Form {...form}>
        <FormField
          control={form.control}
          name="steam_league_id"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Steam League ID (optional)</FormLabel>
              <FormControl>
                <Input
                  type="number"
                  placeholder="Leave blank if this league has no Steam ID"
                  {...field}
                  value={field.value ?? ''}
                  onChange={(e) =>
                    field.onChange(
                      e.target.value ? parseInt(e.target.value, 10) : null,
                    )
                  }
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Name</FormLabel>
              <FormControl>
                <Input placeholder="League name" {...field} />
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
                  placeholder="League description"
                  rows={3}
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
                  placeholder="League rules and guidelines"
                  rows={4}
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      </Form>
    </FormDialog>
  );
}
