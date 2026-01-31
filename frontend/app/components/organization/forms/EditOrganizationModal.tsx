import { zodResolver } from '@hookform/resolvers/zod';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';

import { AdminTeamSection } from '~/components/admin-team';
import { updateOrganization } from '~/components/api/api';
import { FormDialog } from '~/components/ui/dialogs';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import { Textarea } from '~/components/ui/textarea';
import { useIsOrganizationAdmin } from '~/hooks/usePermissions';
import {
  EditOrganizationSchema,
  type EditOrganizationInput,
  type OrganizationType,
} from '../schemas';

interface EditOrganizationModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  organization: OrganizationType;
  onSuccess?: () => void;
}

export function EditOrganizationModal({
  open,
  onOpenChange,
  organization,
  onSuccess,
}: EditOrganizationModalProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const isOrgAdmin = useIsOrganizationAdmin(organization);

  const form = useForm<EditOrganizationInput>({
    resolver: zodResolver(EditOrganizationSchema),
    defaultValues: {
      name: organization.name || '',
      description: organization.description || '',
      logo: organization.logo || '',
      discord_link: organization.discord_link || '',
      discord_server_id: organization.discord_server_id || '',
      rules_template: organization.rules_template || '',
    },
  });

  // Reset form when organization changes or modal opens
  useEffect(() => {
    if (open) {
      form.reset({
        name: organization.name || '',
        description: organization.description || '',
        logo: organization.logo || '',
        discord_link: organization.discord_link || '',
        discord_server_id: organization.discord_server_id || '',
        rules_template: organization.rules_template || '',
      });
    }
  }, [open, organization, form]);

  async function onSubmit(data: EditOrganizationInput) {
    if (isSubmitting || !organization.pk) return;
    setIsSubmitting(true);

    try {
      await updateOrganization(organization.pk, data);
      toast.success('Organization updated successfully');
      onOpenChange(false);
      onSuccess?.();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to update organization';
      toast.error(message);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Edit Organization"
      description="Update organization information and settings."
      submitLabel="Save Changes"
      isSubmitting={isSubmitting}
      onSubmit={form.handleSubmit(onSubmit)}
      size="xl"
      data-testid="edit-organization-modal"
    >
      <Form {...form}>
        <FormField
          control={form.control}
          name="name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Organization Name</FormLabel>
              <FormControl>
                <Input
                  placeholder="Enter organization name"
                  data-testid="org-name-input"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="logo"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Logo URL</FormLabel>
              <FormControl>
                <Input
                  placeholder="https://example.com/logo.png"
                  data-testid="org-logo-input"
                  {...field}
                />
              </FormControl>
              <FormDescription>
                URL to the organization's logo image
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="discord_link"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Discord Server Link</FormLabel>
              <FormControl>
                <Input
                  placeholder="https://discord.gg/your-server"
                  data-testid="org-discord-input"
                  {...field}
                />
              </FormControl>
              <FormDescription>
                Invite link to your Discord server
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="discord_server_id"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Discord Server ID</FormLabel>
              <FormControl>
                <Input
                  placeholder="123456789012345678"
                  data-testid="org-discord-server-id-input"
                  {...field}
                  value={field.value || ''}
                />
              </FormControl>
              <FormDescription>
                Discord server (guild) ID for fetching members
              </FormDescription>
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
                  placeholder="Describe your organization..."
                  rows={4}
                  data-testid="org-description-input"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="rules_template"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Rules Template</FormLabel>
              <FormControl>
                <Textarea
                  placeholder="Default rules for leagues and tournaments..."
                  rows={6}
                  data-testid="org-rules-input"
                  {...field}
                />
              </FormControl>
              <FormDescription>
                These rules will be used as defaults for new leagues
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        {/* Admin Team Section */}
        {isOrgAdmin && (
          <AdminTeamSection
            organization={organization}
            onUpdate={onSuccess}
          />
        )}
      </Form>
    </FormDialog>
  );
}
