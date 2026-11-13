// Slot N >= 1 stacks suffix their cookie names (`csrftoken-s3`), as do ephemeral `test::run` stacks
// (`csrftoken-run-1a2b3c4d`). A browser context only talks to one stack, so the base name or a suffixed one
// identifies the cookie.
const slotCookie = (base: string) => new RegExp(`^${base}(-s\\d+|-run-[0-9a-f]+)?$`);

export const isCsrfCookie = (name: string): boolean => slotCookie('csrftoken').test(name);
export const isSessionCookie = (name: string): boolean => slotCookie('sessionid').test(name);
