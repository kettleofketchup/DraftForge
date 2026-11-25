import { readdirSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
import { expect, it } from 'vitest';

const routes = new URL('../../app/routes/', import.meta.url);
const files = readdirSync(routes).filter((name) => /\.tsx?$/.test(name));

it.each(files)('%s has no duplicate local import bindings', (name) => {
  const path = new URL(name, routes);
  const source = ts.createSourceFile(
    fileURLToPath(path),
    readFileSync(path, 'utf8'),
    ts.ScriptTarget.Latest,
    true,
  );
  const bindings: string[] = [];

  for (const statement of source.statements) {
    if (!ts.isImportDeclaration(statement) || !statement.importClause) continue;
    const { name: defaultName, namedBindings } = statement.importClause;
    if (defaultName) bindings.push(defaultName.text);
    if (namedBindings) {
      if (ts.isNamespaceImport(namedBindings)) {
        bindings.push(namedBindings.name.text);
      } else {
        bindings.push(
          ...namedBindings.elements.map((binding) => binding.name.text),
        );
      }
    }
  }

  const duplicates = bindings.filter(
    (binding, index) => bindings.indexOf(binding) !== index,
  );
  expect(duplicates).toEqual([]);
});
