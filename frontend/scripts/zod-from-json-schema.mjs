#!/usr/bin/env node
// Pydantic -> Zod binding: the TypeScript half. Reads a bundle written by
// backend/common/zod_export.py and writes Zod schemas, inferred types and,
// optionally, the bundled data as a typed constant.
//
//   <exporter> | node frontend/scripts/zod-from-json-schema.mjs --out <ts> [--check]
//
// See docs/development/pydantic-zod.md.
import { jsonSchemaToZod } from 'json-schema-to-zod';
import { Buffer } from 'node:buffer';
import { readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import process from 'node:process';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import * as prettier from 'prettier';

const BUNDLE_VERSION = 1;
const DEF_PREFIX = '#/$defs/';
const REF_SIBLINGS = new Set(['$ref', 'title', 'description']);

export const schemaName = (name) => `${name}Schema`;

function defName(ref) {
  if (typeof ref !== 'string' || !ref.startsWith(DEF_PREFIX)) {
    throw new Error(`unsupported $ref ${JSON.stringify(ref)}`);
  }
  return ref.slice(DEF_PREFIX.length);
}

function refsIn(node, found = new Set()) {
  if (Array.isArray(node)) {
    for (const item of node) refsIn(item, found);
  } else if (node && typeof node === 'object') {
    if ('$ref' in node) found.add(defName(node.$ref));
    for (const value of Object.values(node)) refsIn(value, found);
  }
  return found;
}

// Dependencies first; otherwise keeps pydantic's order. Zod consts cannot
// reference a later const, so a cycle is an error.
export function sortDefs(defs) {
  const deps = new Map(
    Object.entries(defs).map(([name, def]) => [name, refsIn(def)]),
  );
  for (const [name, refs] of deps) {
    for (const ref of refs) {
      if (!deps.has(ref)) throw new Error(`${name}: unknown $ref ${ref}`);
    }
  }
  const done = new Set();
  const order = [];
  while (order.length < deps.size) {
    const ready = [...deps.keys()].find(
      (name) =>
        !done.has(name) && [...deps.get(name)].every((d) => done.has(d)),
    );
    if (ready === undefined) {
      const left = [...deps.keys()].filter((n) => !done.has(n));
      throw new Error(
        `recursive schemas are not supported: ${left.join(', ')}`,
      );
    }
    done.add(ready);
    order.push(ready);
  }
  return order;
}

function parserOverride(schema) {
  if (!('$ref' in schema)) return undefined;
  const extra = Object.keys(schema).filter((k) => !REF_SIBLINGS.has(k));
  if (extra.length) {
    throw new Error(`$ref with sibling keywords ${extra.join(', ')}`);
  }
  return schemaName(defName(schema.$ref));
}

function toZod(schema) {
  return jsonSchemaToZod(schema, {
    module: 'none',
    noImport: true,
    withoutDefaults: true,
    parserOverride,
  });
}

function exportSchema(name, schema) {
  const zodName = schemaName(name);
  return (
    `export const ${zodName} = ${toZod(schema)};\n` +
    `export type ${name} = z.infer<typeof ${zodName}>;\n`
  );
}

export function renderModule(bundle) {
  if (bundle.version !== BUNDLE_VERSION) {
    throw new Error(`bundle version ${bundle.version}, want ${BUNDLE_VERSION}`);
  }
  const { $defs: defs = {}, ...root } = bundle.schema;
  if (!root.title) throw new Error('root schema needs a title');
  if (root.title in defs) {
    throw new Error(`root title ${root.title} clashes with a $def`);
  }
  for (const name of refsIn(root)) {
    if (!(name in defs)) throw new Error(`root: unknown $ref ${name}`);
  }
  const parts = [
    '// GENERATED FILE - DO NOT EDIT.\n' +
      `// Source: ${bundle.source}\n` +
      `// Regenerate with: ${bundle.regen}\n` +
      "import { z } from 'zod';\n",
    ...sortDefs(defs).map((name) => exportSchema(name, defs[name])),
    exportSchema(root.title, root),
  ];
  if (bundle.data) {
    const { name, type, value } = bundle.data;
    if (type !== root.title) {
      throw new Error(`data type ${type} is not the root schema ${root.title}`);
    }
    parts.push(`export const ${name}: ${type} = ${JSON.stringify(value)};\n`);
  }
  return parts.join('\n');
}

export async function formatModule(text, outPath) {
  const configFile = await prettier.resolveConfigFile(outPath);
  const config = (await prettier.resolveConfig(outPath)) ?? {};
  // Prettier resolves plugin names from the cwd; pin them to the config.
  const require = createRequire(configFile ?? outPath);
  const plugins = (config.plugins ?? []).map((p) =>
    typeof p === 'string' ? require.resolve(p) : p,
  );
  return prettier.format(text, { ...config, plugins, filepath: outPath });
}

function readOrEmpty(path) {
  try {
    return readFileSync(path, 'utf8');
  } catch (err) {
    if (err.code === 'ENOENT') return '';
    throw err;
  }
}

export function staleReport(path, current, expected, regen) {
  const a = current.split('\n');
  const b = expected.split('\n');
  let i = 0;
  while (i < a.length && i < b.length && a[i] === b[i]) i += 1;
  return (
    `${path} is stale; run \`${regen}\`.\n` +
    `first difference at line ${i + 1}:\n` +
    `- ${a[i] ?? '<end of file>'}\n` +
    `+ ${b[i] ?? '<end of file>'}\n`
  );
}

async function readStdin() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  return Buffer.concat(chunks).toString('utf8');
}

export async function main(argv = process.argv.slice(2)) {
  const { values } = parseArgs({
    args: argv,
    options: {
      in: { type: 'string' },
      out: { type: 'string' },
      check: { type: 'boolean', default: false },
    },
  });
  if (!values.out) throw new Error('--out is required');
  const raw = values.in ? readFileSync(values.in, 'utf8') : await readStdin();
  const bundle = JSON.parse(raw);
  const expected = await formatModule(renderModule(bundle), values.out);
  if (!values.check) {
    writeFileSync(values.out, expected);
    return 0;
  }
  const current = readOrEmpty(values.out);
  if (current === expected) return 0;
  process.stderr.write(
    staleReport(values.out, current, expected, bundle.regen),
  );
  return 1;
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  main().then(
    (code) => process.exit(code),
    (err) => {
      process.stderr.write(`zod-from-json-schema: ${err.message}\n`);
      process.exit(2);
    },
  );
}
