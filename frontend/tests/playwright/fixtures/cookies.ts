// Test stack slot N >= 1 suffixes its cookie names (`csrftoken-s3`). A browser context only talks to one
// slot, so the base name or a slot-suffixed one identifies the cookie.
const slotCookie = (base: string) => new RegExp(`^${base}(-s\\d+)?$`);

export const isCsrfCookie = (name: string): boolean => slotCookie('csrftoken').test(name);
export const isSessionCookie = (name: string): boolean => slotCookie('sessionid').test(name);
