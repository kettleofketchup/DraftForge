import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterAll, afterEach, describe, expect, it, vi } from 'vitest';
import {
  formatModule,
  main,
  renderModule,
  sortDefs,
  type ZodBundle,
} from '../../scripts/zod-from-json-schema.mjs';

const ref = (name: string) => ({ $ref: `#/$defs/${name}` });

const bundle = (
  schema: Record<string, unknown>,
  data?: ZodBundle['data'],
): ZodBundle => ({
  version: 1,
  source: 'backend/x.py',
  regen: 'just x',
  schema,
  ...(data && { data }),
});

const ROOT = {
  title: 'Root',
  type: 'object',
  additionalProperties: false,
  required: ['item'],
  properties: { item: ref('Item') },
  $defs: {
    // Alphabetical, like pydantic: Item must still come after Kind.
    Item: {
      type: 'object',
      required: ['kind'],
      properties: { kind: ref('Kind') },
    },
    Kind: { type: 'string', enum: ['a', 'b'] },
  },
};

describe('sortDefs', () => {
  it('puts dependencies first and otherwise keeps order', () => {
    expect(sortDefs(ROOT.$defs)).toEqual(['Kind', 'Item']);
    expect(sortDefs({ B: {}, A: {} })).toEqual(['B', 'A']);
  });

  it('rejects cycles and unknown refs', () => {
    expect(() => sortDefs({ A: ref('B'), B: ref('A') })).toThrow(/recursive/);
    expect(() => sortDefs({ A: ref('Nope') })).toThrow(/unknown \$ref Nope/);
  });
});

describe('renderModule', () => {
  it('names every $def and references it by name', () => {
    const text = renderModule(bundle(ROOT));
    expect(text).toContain('export const KindSchema = z.enum(["a","b"])');
    expect(text).toContain('"kind": KindSchema');
    expect(text).toContain('"item": ItemSchema');
    expect(text).toContain('export type Root = z.infer<typeof RootSchema>;');
    expect(text.indexOf('KindSchema =')).toBeLessThan(
      text.indexOf('ItemSchema ='),
    );
    expect(text).not.toContain('z.any()');
  });

  it('emits the data typed as the root schema', () => {
    const data = { name: 'ROOT', type: 'Root', value: { item: { kind: 'a' } } };
    expect(renderModule(bundle(ROOT, data))).toContain(
      'export const ROOT: Root = {"item":{"kind":"a"}};',
    );
    expect(() => renderModule(bundle(ROOT, { ...data, type: 'Item' }))).toThrow(
      /not the root schema/,
    );
  });

  it('rejects inputs it cannot render faithfully', () => {
    expect(() => renderModule({ ...bundle(ROOT), version: 2 })).toThrow(
      /version/,
    );
    const { title: _title, ...untitled } = ROOT;
    expect(() => renderModule(bundle(untitled))).toThrow(/title/);
    const sibling = {
      ...ROOT,
      properties: { item: { ...ref('Item'), default: {} } },
    };
    expect(() => renderModule(bundle(sibling))).toThrow(/sibling/);
    const external = {
      title: 'R',
      type: 'object',
      properties: { x: { $ref: 'other.json' } },
    };
    expect(() => renderModule(bundle(external))).toThrow(/unsupported \$ref/);
    const dangling = { ...ROOT, properties: { item: ref('Gone') } };
    expect(() => renderModule(bundle(dangling))).toThrow(/unknown \$ref Gone/);
  });
});

describe('main', () => {
  const dir = mkdtempSync(path.join(tmpdir(), 'zod-gen-'));
  const input = path.join(dir, 'bundle.json');
  const out = path.join(dir, 'out.ts');
  writeFileSync(input, JSON.stringify(bundle(ROOT)));

  afterEach(() => vi.restoreAllMocks());
  afterAll(() => rmSync(dir, { recursive: true, force: true }));

  it('writes formatted output, then --check passes', async () => {
    expect(await main(['--in', input, '--out', out])).toBe(0);
    const written = readFileSync(out, 'utf8');
    expect(written).toBe(await formatModule(renderModule(bundle(ROOT)), out));
    expect(written).toMatch(/^import \{ z \} from ['"]zod['"];$/m);
    expect(await main(['--in', input, '--out', out, '--check'])).toBe(0);
  });

  it('--check fails on a stale file without touching it', async () => {
    writeFileSync(out, 'stale\n');
    const stderr = vi
      .spyOn(process.stderr, 'write')
      .mockImplementation(() => true);
    expect(await main(['--in', input, '--out', out, '--check'])).toBe(1);
    expect(readFileSync(out, 'utf8')).toBe('stale\n');
    expect(String(stderr.mock.calls[0][0])).toMatch(/stale; run `just x`/);
  });
});
