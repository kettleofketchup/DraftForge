import { zodResolver } from '@hookform/resolvers/zod';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';

import { updateOrganization } from '~/components/api/api';
import { Button } from '~/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
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
import { DIALOG_CSS } from '~/components/reusable/modal';
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

  const form = useForm<EditOrganizationInput>({
    resolver: zodResolver(EditOrganizationSchema),
    defaultValues: {
      name: organization.name || '',
      description: organization.description || '',
      logo: organization.logo || '',
      discord_link: organization.discord_link || '',
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
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={DIALOG_CSS} data-testid="edit-organization-modal">
        <DialogHeader>
          <DialogTitle>Edit Organization</DialogTitle>
          <DialogDescription>
            Update organization information and settings.
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
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

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={isSubmitting}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={isSubmitting}
                data-testid="org-submit-button"
              >
                {isSubmitting ? 'Saving...' : 'Save Changes'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
