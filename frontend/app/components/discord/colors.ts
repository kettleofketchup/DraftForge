export function discordColorHex(
  color: number | null | undefined,
): string | undefined {
  if (!color) return undefined;
  return `#${color.toString(16).padStart(6, '0')}`;
}
