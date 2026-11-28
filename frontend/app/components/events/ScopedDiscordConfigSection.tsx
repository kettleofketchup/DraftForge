import type { FieldValues } from 'react-hook-form';
import { useOrganization } from '~/components/organization';
import { useIsOrganizationStaff } from '~/hooks/usePermissions';
import {
  DiscordConfigSection,
  type DiscordConfigSectionProps,
  type DiscordFields,
} from './DiscordConfigSection';

export function ScopedDiscordConfigSection<
  T extends FieldValues & DiscordFields,
>({
  eventId,
  canManageEvent = false,
  ...props
}: Omit<
  DiscordConfigSectionProps<T>,
  'permissionScope' | 'canCheckPermissions'
> & {
  eventId?: number;
  canManageEvent?: boolean;
}) {
  const { organization } = useOrganization(props.organizationId || undefined);
  const orgStaff = useIsOrganizationStaff(organization);
  const permissionScope = organization
    ? eventId
      ? {
          kind: 'event' as const,
          eventId,
          guildId: organization.discord_server_id ?? null,
        }
      : {
          kind: 'org' as const,
          orgId: props.organizationId,
          guildId: organization.discord_server_id ?? null,
        }
    : null;
  return (
    <DiscordConfigSection
      {...props}
      permissionScope={permissionScope}
      canCheckPermissions={
        Boolean(organization) && (eventId ? canManageEvent : orgStaff)
      }
    />
  );
}
