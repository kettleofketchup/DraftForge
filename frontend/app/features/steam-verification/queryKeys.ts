export const steamVerificationKeys = {
  all: ['steamVerification'] as const,
  detail: (userPk: number, viewerPk: number | undefined) =>
    [...steamVerificationKeys.all, userPk, viewerPk] as const,
};

/** Query prefixes whose payloads embed a user's Friend ID verification. */
export const STEAM_VERIFICATION_DEPENDENT_KEYS = [
  ['event-signups'],
  ['user-dota-profile'],
  ['dota-profile'],
  ['tournament'],
] as const;
