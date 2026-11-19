import { zodResolver } from '@hookform/resolvers/zod';
import { useQueryClient } from '@tanstack/react-query';
import { Building2, ScrollText, Users, type LucideIcon } from 'lucide-react';
import { useEffect, useState, type ReactNode, type RefObject } from 'react';
import { useForm, type FieldErrors } from 'react-hook-form';
import { toast } from 'sonner';
import type { z } from 'zod';

import { updateOrganization } from '~/components/api/api';
import { DiscordIcon } from '~/components/events/DiscordConfigSection';
import { organizationQueryKey } from '~/components/organization/hooks/useOrganization';
import {
  EditOrganizationSchema,
  type EditOrganizationInput,
  type OrganizationType,
} from '~/components/organization/schemas';
import type {
  SettingsDialogHandle,
  SettingsSection,
} from '~/components/patterns/SettingsDialog';
import { COMMON_TIMEZONES } from '~/components/tournament/schemas';
import { CancelButton, SubmitButton } from '~/components/ui/buttons';
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';
import { Switch } from '~/components/ui/switch';
import { Textarea } from '~/components/ui/textarea';

export type OrgProfileSection = 'general' | 'discord' | 'members' | 'rules';

const META: Record<
  OrgProfileSection,
  { label: string; icon: LucideIcon; keywords: string[] }
> = {
  general: {
    label: 'General',
    icon: Building2,
    keywords: ['name', 'logo', 'description', 'timezone'],
  },
  discord: {
    label: 'Discord',
    icon: DiscordIcon as LucideIcon,
    keywords: ['server', 'guild', 'invite'],
  },
  members: {
    label: 'Members',
    icon: Users,
    keywords: ['privacy', 'private', 'member list'],
  },
  rules: { label: 'Rules', icon: ScrollText, keywords: ['template', 'league'] },
};

function valuesFrom(
  organization: OrganizationType,
): z.input<typeof EditOrganizationSchema> {
  return {
    name: organization.name || '',
    description: organization.description || '',
    logo: organization.logo || '',
    discord_link: organization.discord_link || '',
    discord_server_id: organization.discord_server_id || '',
    rules_template: organization.rules_template || '',
    timezone: organization.timezone || 'America/New_York',
    members_private: organization.members_private ?? false,
  };
}

/**
 * The organization's own fields (formerly the Edit Organization dialog) as
 * settings sections sharing one form, plus a save bar for unsaved changes.
 */
export function useOrgProfileSections(
  organization: OrganizationType,
  sectionsRef: RefObject<SettingsDialogHandle<string> | null>,
): { sections: SettingsSection<OrgProfileSection>[]; saveBar: ReactNode } {
  const queryClient = useQueryClient();
  const [isSubmitting, setIsSubmitting] = useState(false);

  // 3-generic useForm to align TFieldValues=z.input and TTransformedValues=z.output
  // — zodResolver returns Resolver<z.input<S>, _, z.output<S>> under zod 4.
  const form = useForm<
    z.input<typeof EditOrganizationSchema>,
    unknown,
    EditOrganizationInput
  >({
    resolver: zodResolver(EditOrganizationSchema),
    defaultValues: valuesFrom(organization),
  });

  // Adopt refetched values while there are no local edits.
  useEffect(() => {
    if (!form.formState.isDirty) form.reset(valuesFrom(organization));
  }, [organization, form]);

  const sectionFor = (field: string): string =>
    sectionsRef.current?.sectionOfField(field) ?? 'general';

  async function onSubmit(data: EditOrganizationInput) {
    if (isSubmitting || !organization.pk) return;
    setIsSubmitting(true);
    try {
      await updateOrganization(organization.pk, data);
      toast.success('Organization updated successfully');
      form.reset(data);
      queryClient.invalidateQueries({
        queryKey: organizationQueryKey(organization.pk),
      });
      queryClient.invalidateQueries({
        queryKey: ['discordBotStatus', organization.pk],
      });
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : 'Failed to update organization',
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  function onInvalid(errors: FieldErrors<EditOrganizationInput>) {
    const [key, error] = Object.entries(errors)[0] ?? [];
    if (!key) return;
    sectionsRef.current?.selectSection(sectionFor(key));
    toast.error('Please fix the highlighted fields', {
      description:
        typeof error?.message === 'string' ? error.message : undefined,
    });
  }

  const save = form.handleSubmit(onSubmit, onInvalid);
  const wrap = (children: ReactNode) => (
    <Form {...form}>
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        {children}
      </form>
    </Form>
  );

  const content: Record<OrgProfileSection, ReactNode> = {
    general: wrap(
      <>
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
          name="timezone"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Default Timezone</FormLabel>
              <Select onValueChange={field.onChange} value={field.value}>
                <FormControl>
                  <SelectTrigger
                    className="w-full"
                    data-testid="org-timezone-select"
                  >
                    <SelectValue placeholder="Select timezone" />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {COMMON_TIMEZONES.map((tz) => (
                    <SelectItem key={tz} value={tz}>
                      {tz}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormDescription>
                Default timezone for events and tournaments
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
      </>,
    ),
    discord: wrap(
      <>
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
      </>,
    ),
    members: wrap(
      <>
        <FormField
          control={form.control}
          name="members_private"
          render={({ field }) => (
            <FormItem className="flex items-center justify-between gap-4 rounded-md border border-border p-3">
              <div className="space-y-0.5">
                <FormLabel>Private members list</FormLabel>
                <FormDescription>
                  When on, only staff and admins can see the member list. When
                  off, every member can.
                </FormDescription>
              </div>
              <FormControl>
                <Switch
                  checked={field.value ?? false}
                  onCheckedChange={field.onChange}
                  data-testid="org-members-private-switch"
                />
              </FormControl>
            </FormItem>
          )}
        />
      </>,
    ),
    rules: wrap(
      <>
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
      </>,
    ),
  };

  const errorKeys = Object.keys(form.formState.errors).filter(
    (k) => k !== 'root',
  );
  const sections = (Object.keys(content) as OrgProfileSection[]).map(
    (value) => ({
      value,
      ...META[value],
      content: content[value],
      invalid: errorKeys.some((k) => sectionFor(k) === value),
    }),
  );

  const saveBar = form.formState.isDirty ? (
    <div
      className="sticky bottom-4 mx-auto mt-6 flex w-full max-w-4xl items-center justify-end gap-2 rounded-lg border border-border bg-background/95 p-3 shadow-lg backdrop-blur"
      data-testid="org-profile-save-bar"
    >
      <span className="mr-auto text-sm text-muted-foreground">
        Unsaved changes
      </span>
      <CancelButton
        type="button"
        disabled={isSubmitting}
        onClick={() => form.reset(valuesFrom(organization))}
        data-testid="org-profile-discard"
      >
        Discard
      </CancelButton>
      <SubmitButton
        loading={isSubmitting}
        onClick={() => void save()}
        data-testid="org-profile-save"
      >
        Save changes
      </SubmitButton>
    </div>
  ) : null;

  return { sections, saveBar };
}
