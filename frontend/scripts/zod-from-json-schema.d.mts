export interface ZodBundle {
  version: number;
  source: string;
  regen: string;
  schema: Record<string, unknown>;
  data?: { name: string; type: string; value: unknown };
}

export function schemaName(name: string): string;
export function sortDefs(defs: Record<string, unknown>): string[];
export function renderModule(bundle: ZodBundle): string;
export function formatModule(text: string, outPath: string): Promise<string>;
export function staleReport(
  path: string,
  current: string,
  expected: string,
  regen: string,
): string;
export function main(argv?: string[]): Promise<number>;
