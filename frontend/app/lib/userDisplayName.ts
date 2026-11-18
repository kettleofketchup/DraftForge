import { useUserCacheStore } from '~/store/userCacheStore';
import type { UserEntry } from '~/store/userCacheTypes';

export type DiscordMemberLike = {
  nick?: string | null;
  user: { username: string; global_name?: string | null };
};

export type UserRef = {
  pk?: number | null;
  user_id?: number | null;
  user?: unknown;
  id?: unknown;
  username?: string | null;
  discordNickname?: string | null;
  guildNickname?: string | null;
  orgNicknames?: Record<number, string | null>;
  avatar?: string | null;
  avatarUrl?: string | null;
  discordId?: string | null;
};

export type ResolveOptions = {
  orgId?: number | null;
  maxLength?: number;
  /** Cache entry to merge; omit to read it from the user cache. */
  cached?: UserEntry | null;
};

const present = (name: string | null | undefined): name is string =>
  typeof name === 'string' && name.trim() !== '';

const isNum = (v: unknown): v is number =>
  typeof v === 'number' && Number.isFinite(v);

export function isDiscordMember(u: unknown): u is DiscordMemberLike {
  if (typeof u !== 'object' || u === null) return false;
  const inner = (u as { user?: unknown }).user;
  return typeof inner === 'object' && inner !== null && 'username' in inner;
}

export function truncateName(name: string, n: number): string {
  return name.length > n ? `${name.substring(0, n)}…` : name;
}

// pk, then user_id, then a numeric `user`; `id` only on objects carrying user fields, since teams and drafts also have ids.
export function userRefPk(u: unknown): number | undefined {
  if (typeof u !== 'object' || u === null || isDiscordMember(u))
    return undefined;
  const ref = u as UserRef;
  if (isNum(ref.pk)) return ref.pk;
  if (isNum(ref.user_id)) return ref.user_id;
  if (isNum(ref.user)) return ref.user;
  if (
    isNum(ref.id) &&
    ('username' in ref || 'discordNickname' in ref || 'avatar' in ref)
  ) {
    return ref.id;
  }
  return undefined;
}

export function cachedUserFor(u: unknown): UserEntry | undefined {
  const pk = userRefPk(u);
  return pk == null ? undefined : useUserCacheStore.getState().entities[pk];
}

/** Payload fields win when present; the cache entry fills the gaps. */
export function mergeCachedUser<T extends UserRef>(
  payload: T,
  entry: UserEntry | null | undefined,
): T {
  if (!entry) return payload;
  const hasImage = present(payload.avatar) || present(payload.avatarUrl);
  return {
    ...payload,
    pk: entry.pk,
    username: present(payload.username) ? payload.username : entry.username,
    discordNickname: present(payload.discordNickname)
      ? payload.discordNickname
      : entry.discordNickname,
    discordId: present(payload.discordId) ? payload.discordId : entry.discordId,
    avatar: hasImage ? payload.avatar : entry.avatar,
    avatarUrl: hasImage ? payload.avatarUrl : entry.avatarUrl,
    orgNicknames: { ...entry.orgNicknames, ...payload.orgNicknames },
  };
}

function orgNickname(
  user: UserRef,
  entry: UserEntry | null | undefined,
  orgId: number,
): string | null | undefined {
  const own = user.orgNicknames;
  if (own && Object.prototype.hasOwnProperty.call(own, orgId))
    return own[orgId];
  if (user.guildNickname !== undefined) return user.guildNickname;
  return entry?.orgNicknames?.[orgId];
}

function fallbackName(pk: number | undefined): string {
  return pk == null ? '?' : `User ${pk}`;
}

/** Org server nickname (with an org) > global Discord name > username > `User <pk>` > `?`. */
export function resolveDisplayName(
  user: UserRef | DiscordMemberLike | null | undefined,
  opts?: ResolveOptions,
): string {
  if (!user || typeof user !== 'object') return '?';
  let name: string;
  if (isDiscordMember(user)) {
    name =
      [user.nick, user.user.global_name, user.user.username].find(present) ??
      '?';
  } else {
    const pk = userRefPk(user);
    const entry = opts && 'cached' in opts ? opts.cached : cachedUserFor(user);
    const orgId = opts?.orgId;
    const merged = mergeCachedUser(user, entry);
    const chain = [
      isNum(orgId) ? orgNickname(user, entry, orgId) : undefined,
      merged.discordNickname,
      merged.username,
    ];
    name = chain.find(present) ?? fallbackName(pk);
  }
  return opts?.maxLength ? truncateName(name, opts.maxLength) : name;
}
