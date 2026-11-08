export const NO_SLOT_MESSAGE = 'No test-stack slot for this worktree. Run "just test::slot".';

const SLOT_FILE_REL = 'docker/.env.slot';
const TRUSTED_SOURCES = new Set(['invoke', 'container']);

export interface ResolveInput {
  env: Record<string, string | undefined>;
  repoRoot: () => string;
  readFile: (path: string) => string | null;
  realpath: (path: string) => string;
}

export function parseSlotFile(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#') || !line.includes('=')) continue;
    const i = line.indexOf('=');
    out[line.slice(0, i).trim()] = line.slice(i + 1);
  }
  return out;
}

function readSlot(input: ResolveInput, root: string): Record<string, string> | null {
  const text = input.readFile(`${root}/${SLOT_FILE_REL}`);
  return text === null ? null : parseSlotFile(text);
}

function slotBaseUrl(input: ResolveInput, root: string, kv: Record<string, string>): string {
  const writtenFor = kv.DF_WORKTREE ?? '';
  if (!writtenFor || input.realpath(writtenFor) !== root) {
    throw new Error(
      `\`.env.slot\` was written for ${writtenFor}, not ${root}; ` +
        `delete ${root}/${SLOT_FILE_REL} and run \`just test::slot\``,
    );
  }
  const n = kv.DF_SLOT ?? '';
  const resText = input.readFile(`${kv.DF_REGISTRY ?? ''}/slot-${n}`);
  if (resText === null) {
    throw new Error(`no reservation for slot ${n}; run \`just test::slot\``);
  }
  const res = parseSlotFile(resText);
  const owner = res.owner ?? '';
  if (!owner || input.realpath(owner) !== root || res.token !== kv.DF_SLOT_TOKEN) {
    throw new Error(`slot ${n} now belongs to ${owner}; run \`just test::slot\` to get a new slot`);
  }
  if (!kv.DF_BASE_URL) throw new Error(`\`.env.slot\` for slot ${n} has no DF_BASE_URL`);
  return kv.DF_BASE_URL;
}

export function resolveBaseUrl(input: ResolveInput): string {
  const { env } = input;
  const fromEnv = env.DF_BASE_URL;
  if (fromEnv) {
    if (TRUSTED_SOURCES.has(env.DF_BASE_URL_SOURCE ?? '')) return fromEnv;
    const kv = readSlot(input, input.realpath(input.repoRoot()));
    if (kv && kv.DF_BASE_URL !== fromEnv) {
      throw new Error(
        `DF_BASE_URL=${fromEnv} in your environment disagrees with this worktree's slot ` +
          `${kv.DF_BASE_URL ?? ''}; unset it`,
      );
    }
    return fromEnv;
  }
  const root = input.realpath(input.repoRoot());
  const kv = readSlot(input, root);
  if (kv) return slotBaseUrl(input, root, kv);
  if (env.GITHUB_ACTIONS === 'true') return 'https://localhost';
  throw new Error(NO_SLOT_MESSAGE);
}
