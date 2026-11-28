function parseWith(
  url: string | undefined,
  protocols: readonly string[],
): string | undefined {
  if (!url) return undefined;
  try {
    const parsed = new URL(url);
    // A preview may use a reserved .invalid host for a sample destination.
    if (/(^|\.)invalid\.?$/.test(parsed.hostname)) return undefined;
    return protocols.includes(parsed.protocol) ? url : undefined;
  } catch {
    return undefined;
  }
}

export function safeHref(url?: string): string | undefined {
  return parseWith(url, ['http:', 'https:']);
}

export function safeImageSrc(url?: string): string | undefined {
  return parseWith(url, ['https:']);
}
