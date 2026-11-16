import { useUserCacheStore } from '~/store/userCacheStore';

export type DiscordMemberLike = {
  nick?: string | null;
  user: { username: string; global_name?: string | null };
};

export type NameSource = {
  pk?: number | null;
  username?: string | null;
  discordUsername?: string | null;
  discordNickname?: string | null;
  orgNicknames?: Record<number, string | null>;
};

export type OrgNameRow = {
  user_pk?: number;
  pk?: number;
  username?: string | null;
  discordUsername?: string | null;
  discordNickname?: string | null;
  guildNickname?: string | null;
};

type ResolveOptions = { orgId?: number | null; maxLength?: number };

const present = (name: string | null | undefined): name is string =>
  typeof name === 'string' && name.trim() !== '';

const hasOrg = (orgId: number | null | undefined): orgId is number =>
  typeof orgId === 'number';

export function isDiscordMember(u: unknown): u is DiscordMemberLike {
  if (typeof u !== 'object' || u === null) return false;
  const inner = (u as { user?: unknown }).user;
  return typeof inner === 'object' && inner !== null && 'username' in inner;
}

export function truncateName(name: string, n: number): string {
  return name.length > n ? `${name.substring(0, n)}…` : name;
}

function orgNickname(
  user: NameSource,
  orgId: number,
): string | null | undefined {
  const own = user.orgNicknames;
  if (own && Object.prototype.hasOwnProperty.call(own, orgId))
    return own[orgId];
  if (typeof user.pk !== 'number') return undefined;
  return useUserCacheStore.getState().getById(user.pk)?.orgNicknames?.[orgId];
}

function memberNames(member: DiscordMemberLike): (string | null | undefined)[] {
  return [member.nick, member.user.global_name, member.user.username];
}

function fallbackName(pk: number | null | undefined): string {
  return typeof pk === 'number' ? `User ${pk}` : '?';
}

export function resolveDisplayName(
  user: NameSource | DiscordMemberLike | null | undefined,
  opts?: ResolveOptions,
): string {
  if (!user || typeof user !== 'object') return '?';
  const orgId = opts?.orgId;
  let name: string;
  if (isDiscordMember(user)) {
    name = memberNames(user).find(present) ?? '?';
  } else {
    const chain = [
      hasOrg(orgId) ? orgNickname(user, orgId) : undefined,
      user.discordNickname,
      user.username,
    ];
    name = chain.find(present) ?? fallbackName(user.pk);
  }
  return opts?.maxLength ? truncateName(name, opts.maxLength) : name;
}

export function displayNameById(
  pk: number | null | undefined,
  fallback?: string | null,
  orgId?: number | null,
): string {
  const entry =
    typeof pk === 'number'
      ? useUserCacheStore.getState().getById(pk)
      : undefined;
  if (entry) return resolveDisplayName(entry, { orgId });
  if (present(fallback)) return fallback;
  return fallbackName(pk);
}

export function userNameCandidates(
  user: NameSource | DiscordMemberLike,
  orgId?: number | null,
): string[] {
  const names = isDiscordMember(user)
    ? memberNames(user)
    : [
        hasOrg(orgId) ? orgNickname(user, orgId) : undefined,
        user.discordNickname,
        user.discordUsername,
        user.username,
      ];
  return names.filter(present);
}

export function matchesUserQuery(
  user: NameSource | DiscordMemberLike,
  q: string,
  orgId?: number | null,
): boolean {
  const needle = q.trim().toLowerCase();
  if (!needle) return true;
  return userNameCandidates(user, orgId).some((name) =>
    name.toLowerCase().includes(needle),
  );
}

export function orgRowNameSource(
  row: OrgNameRow,
  orgId: number | null,
): NameSource {
  return {
    pk: row.user_pk ?? row.pk,
    username: row.username,
    discordUsername: row.discordUsername,
    discordNickname: row.discordNickname,
    orgNicknames: hasOrg(orgId) ? { [orgId]: row.guildNickname ?? null } : {},
  };
}

export function orgRowDisplayName(
  row: OrgNameRow,
  orgId: number | null,
  maxLength?: number,
): string {
  return resolveDisplayName(orgRowNameSource(row, orgId), { orgId, maxLength });
}
