import type { ConsolaInstance } from 'consola/browser';
import { consola } from 'consola/browser';

export function getLogger(loggerName: string): ConsolaInstance {
  const log = consola.withTag(loggerName);
  if (process.env.NODE_ENV === 'development') log.level = 5;
  else log.level = 1;
  return log;
}
