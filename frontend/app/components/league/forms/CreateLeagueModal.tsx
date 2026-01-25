import { zodResolver } from '@hookform/resolvers/zod';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import { createLeague } from '~/components/api/api';
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
import { useUserStore } from '~/store/userStore';
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
  const getLeagues = useUserStore((state) => state.getLeagues);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const form = useForm<CreateLeagueInput>({
    resolver: zodResolver(CreateLeagueSchema),
    defaultValues: {
      organization_ids: [organizationId],
      steam_league_id: undefined as number | undefined,
      name: '',
      description: '',
      rules: '',
    },
  });

  async function onSubmit(data: CreateLeagueInput) {
    if (isSubmitting) return;
    setIsSubmitting(true);
    try {
      await createLeague({ ...data, organization_ids: [organizationId] });
      toast.success('League created successfully');
      getLeagues(organizationId);
      onOpenChange(false);
      form.reset();
    } catch {
      toast.error('Failed to create league');
    } finally {
      setIsSubmitting(false);
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
              <FormLabel>Steam League ID</FormLabel>
              <FormControl>
                <Input
                  type="number"
                  placeholder="12345"
                  {...field}
                  onChange={(e) =>
                    field.onChange(
                      e.target.value ? parseInt(e.target.value, 10) : undefined
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
