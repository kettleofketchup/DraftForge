import { EVENT_SECTION_FIELDS, type SectionFieldMeta } from './settingsFields';
import { eventTabForField, type EventFormTabValue } from './tabs';

export interface FieldPlacement {
  section: EventFormTabValue;
  label?: string;
  description?: string;
}

/** Field name → where it renders in the open modal. */
export type FieldPlacements = ReadonlyMap<string, FieldPlacement>;

export interface SettingsIndexEntry {
  field: string;
  section: EventFormTabValue;
  label: string;
  description?: string;
  keywords: readonly string[];
}

export interface SettingsSearchGroup {
  section: EventFormTabValue;
  entries: SettingsIndexEntry[];
}

const text = (el: Element | null): string | undefined =>
  el?.textContent?.trim() || undefined;

/** Reads every `[data-field]` inside a `[data-section]` panel under `root`. */
export function scanFieldPlacements(root: ParentNode): FieldPlacements {
  const placements = new Map<string, FieldPlacement>();
  root.querySelectorAll<HTMLElement>('[data-field]').forEach((el) => {
    const field = el.dataset.field;
    const section = el.closest<HTMLElement>('[data-section]')?.dataset
      .section as EventFormTabValue | undefined;
    if (!field || !section || placements.has(field)) return;
    placements.set(field, {
      section,
      label: text(el.querySelector('label')),
      description: text(el.querySelector('[id$="-form-item-description"]')),
    });
  });
  return placements;
}

/**
 * The searchable fields of one modal: registry fields rendered in it (at the
 * section they render in), registry fields of lazy sections not mounted yet, and
 * rendered fields the registry does not know, labelled from the DOM.
 */
export function buildSettingsIndex({
  sections,
  placements,
  meta = EVENT_SECTION_FIELDS,
}: {
  sections: { value: EventFormTabValue; mounted: boolean }[];
  placements: FieldPlacements;
  meta?: SectionFieldMeta;
}): SettingsIndexEntry[] {
  const index: SettingsIndexEntry[] = [];
  const seen = new Set<string>();
  const present = new Set(sections.map((s) => s.value));
  const unmounted = new Set(
    sections.filter((s) => !s.mounted).map((s) => s.value),
  );

  for (const [home, fields] of Object.entries(meta) as [
    EventFormTabValue,
    SectionFieldMeta[EventFormTabValue],
  ][]) {
    for (const [field, m] of Object.entries(fields)) {
      const placed = placements.get(field);
      const section = placed?.section ?? (unmounted.has(home) ? home : null);
      if (!section || !present.has(section)) continue;
      seen.add(field);
      index.push({
        field,
        section,
        label: placed?.label ?? m.label,
        description: placed?.description ?? m.description,
        keywords: m.keywords ?? [],
      });
    }
  }
  for (const [field, placed] of placements) {
    if (seen.has(field) || !present.has(placed.section)) continue;
    index.push({
      field,
      section: placed.section,
      label: placed.label ?? field,
      description: placed.description,
      keywords: [],
    });
  }
  return index;
}

function score(entry: SettingsIndexEntry, tokens: string[]): number | null {
  const label = entry.label.toLowerCase();
  const rest = [entry.description ?? '', ...entry.keywords]
    .join(' ')
    .toLowerCase();
  let total = 0;
  for (const token of tokens) {
    if (label.startsWith(token)) total += 3;
    else if (label.includes(token)) total += 2;
    else if (rest.includes(token)) total += 1;
    else return null;
  }
  return total;
}

/**
 * Matches every whitespace-separated token against label, description and
 * keywords. Returns one group per section in `order` (empty groups included so
 * the sidebar can dim them), or no groups for a blank query.
 */
export function searchSettings(
  index: SettingsIndexEntry[],
  order: EventFormTabValue[],
  query: string,
): SettingsSearchGroup[] {
  const tokens = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (tokens.length === 0) return [];
  const scored = index
    .map((entry, i) => ({ entry, i, s: score(entry, tokens) }))
    .filter(
      (x): x is { entry: SettingsIndexEntry; i: number; s: number } =>
        x.s !== null,
    )
    .sort((a, b) => b.s - a.s || a.i - b.i);
  return order.map((section) => ({
    section,
    entries: scored
      .filter((x) => x.entry.section === section)
      .map((x) => x.entry),
  }));
}

/** The section of `available` that shows `field`: where it renders, else its registry home, else the first. */
export function resolveFieldSection(
  field: string,
  placements: FieldPlacements,
  available: EventFormTabValue[],
): EventFormTabValue {
  const placed = placements.get(field)?.section;
  if (placed && available.includes(placed)) return placed;
  const home = eventTabForField(field);
  return available.includes(home) ? home : available[0];
}

export function sectionsWithErrors(
  errorFields: string[],
  placements: FieldPlacements,
  available: EventFormTabValue[],
): Set<EventFormTabValue> {
  return new Set(
    errorFields
      .filter((f) => f !== 'root')
      .map((f) => resolveFieldSection(f, placements, available)),
  );
}
