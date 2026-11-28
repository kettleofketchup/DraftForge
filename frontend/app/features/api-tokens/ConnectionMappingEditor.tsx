import { useFieldArray, type UseFormReturn } from 'react-hook-form';

import {
  BrandSelect,
  BrandSelectContent,
  BrandSelectItem,
  BrandSelectTrigger,
  SelectValue,
} from '~/components/ui/brand-select';
import { SecondaryButton } from '~/components/ui/buttons';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import type { ConnectionForm } from './connectionSchemas';
import {
  MAPPING_PATH_HELP,
  PAGINATION_LABELS,
  PLACEHOLDERS,
  PLAYER_ID_TYPE_LABELS,
  TEMPLATE_KINDS,
  TEMPLATE_KIND_LABELS,
  placeholderLabel,
  type PullForm,
  type TemplateKind,
} from './connectionSyncSchemas';

type Form = UseFormReturn<ConnectionForm>;
type RowsName = 'push.query' | 'pull.query' | 'pull.body';

export interface TemplateFieldsEditorProps {
  form: Form;
  name: RowsName;
  legend: string;
  description: string;
  readOnly: boolean;
  /** Placeholder scopes offered as chips; others stay selectable per row. */
  scopes?: readonly string[];
}

/** Labeled key/value rows; values are literals or named variables, never code. */
export function TemplateFieldsEditor({
  form,
  name,
  legend,
  description,
  readOnly,
  scopes = ['any', 'batch', 'member', 'page', 'cursor'],
}: TemplateFieldsEditorProps) {
  const rows = useFieldArray({ control: form.control, name });
  const testId = `api-connection-${name.replace('.', '-')}`;
  const kinds = TEMPLATE_KINDS.filter((kind) => kind !== 'json');
  return (
    <fieldset className="flex flex-col gap-3" data-testid={testId}>
      <legend className="mb-1 text-sm font-semibold">{legend}</legend>
      <p className="text-xs text-muted-foreground">{description}</p>
      {rows.fields.length === 0 && (
        <p className="text-xs text-muted-foreground">No fields.</p>
      )}
      <ul className="flex flex-col gap-3">
        {rows.fields.map((row, index) => (
          <li
            key={row.id}
            className="grid grid-cols-1 gap-2 rounded-md border border-border p-2 sm:grid-cols-[1fr_9rem_1fr_auto] sm:items-start"
            data-testid={`${testId}-row-${index}`}
          >
            <FormField
              control={form.control}
              name={`${name}.${index}.key`}
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="text-xs">Field name</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      autoComplete="off"
                      disabled={readOnly}
                      data-testid={`${testId}-key-${index}`}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name={`${name}.${index}.kind`}
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="text-xs">Type</FormLabel>
                  <BrandSelect
                    value={field.value}
                    onValueChange={(next) => {
                      field.onChange(next as TemplateKind);
                      form.setValue(
                        `${name}.${index}.value`,
                        next === 'boolean'
                          ? 'true'
                          : next === 'variable'
                            ? PLACEHOLDERS[0].value
                            : '',
                        { shouldDirty: true },
                      );
                    }}
                    disabled={readOnly || field.value === 'json'}
                  >
                    <FormControl>
                      <BrandSelectTrigger
                        data-testid={`${testId}-kind-${index}`}
                      >
                        <SelectValue />
                      </BrandSelectTrigger>
                    </FormControl>
                    <BrandSelectContent>
                      {(field.value === 'json' ? TEMPLATE_KINDS : kinds).map(
                        (kind) => (
                          <BrandSelectItem key={kind} value={kind}>
                            {TEMPLATE_KIND_LABELS[kind]}
                          </BrandSelectItem>
                        ),
                      )}
                    </BrandSelectContent>
                  </BrandSelect>
                </FormItem>
              )}
            />
            <TemplateValueField
              form={form}
              name={name}
              index={index}
              readOnly={readOnly}
              testId={testId}
            />
            {!readOnly && (
              <SecondaryButton
                type="button"
                size="sm"
                color="red"
                className="min-h-11 self-end sm:min-h-8"
                onClick={() => rows.remove(index)}
                aria-label={`Remove field ${index + 1}`}
                data-testid={`${testId}-remove-${index}`}
              >
                Remove
              </SecondaryButton>
            )}
          </li>
        ))}
      </ul>
      {!readOnly && (
        <div className="flex flex-col gap-2">
          <span className="text-xs text-muted-foreground">
            Add a variable field:
          </span>
          <div
            className="flex flex-wrap gap-2"
            role="group"
            aria-label={`${legend} variables`}
          >
            {PLACEHOLDERS.filter((p) => scopes.includes(p.scope)).map((p) => (
              <SecondaryButton
                key={p.value}
                type="button"
                size="sm"
                className="min-h-11 sm:min-h-8"
                onClick={() =>
                  rows.append({
                    key: p.field,
                    kind: 'variable',
                    value: p.value,
                  })
                }
                data-testid={`${testId}-chip-${p.field}`}
              >
                {p.label}
              </SecondaryButton>
            ))}
            <SecondaryButton
              type="button"
              size="sm"
              className="min-h-11 sm:min-h-8"
              onClick={() => rows.append({ key: '', kind: 'text', value: '' })}
              data-testid={`${testId}-add`}
            >
              Add plain field
            </SecondaryButton>
          </div>
        </div>
      )}
    </fieldset>
  );
}

function TemplateValueField({
  form,
  name,
  index,
  readOnly,
  testId,
}: {
  form: Form;
  name: RowsName;
  index: number;
  readOnly: boolean;
  testId: string;
}) {
  const kind = form.watch(`${name}.${index}.kind`);
  return (
    <FormField
      control={form.control}
      name={`${name}.${index}.value`}
      render={({ field }) => (
        <FormItem>
          <FormLabel className="text-xs">Value</FormLabel>
          {kind === 'variable' || kind === 'boolean' ? (
            <BrandSelect
              value={field.value}
              onValueChange={field.onChange}
              disabled={readOnly}
            >
              <FormControl>
                <BrandSelectTrigger data-testid={`${testId}-value-${index}`}>
                  <SelectValue
                    placeholder={kind === 'variable' ? 'Choose' : undefined}
                  >
                    {kind === 'variable'
                      ? placeholderLabel(field.value)
                      : field.value}
                  </SelectValue>
                </BrandSelectTrigger>
              </FormControl>
              <BrandSelectContent>
                {kind === 'variable'
                  ? PLACEHOLDERS.map((p) => (
                      <BrandSelectItem key={p.value} value={p.value}>
                        {p.label}
                      </BrandSelectItem>
                    ))
                  : ['true', 'false'].map((v) => (
                      <BrandSelectItem key={v} value={v}>
                        {v}
                      </BrandSelectItem>
                    ))}
              </BrandSelectContent>
            </BrandSelect>
          ) : (
            <FormControl>
              <Input
                {...field}
                inputMode={kind === 'number' ? 'decimal' : undefined}
                autoComplete="off"
                readOnly={kind === 'json'}
                disabled={readOnly}
                className={kind === 'json' ? 'font-mono text-xs' : undefined}
                data-testid={`${testId}-value-${index}`}
              />
            </FormControl>
          )}
          <FormMessage />
        </FormItem>
      )}
    />
  );
}

const PULL_TEXT_FIELDS: {
  name: 'pull.list_path' | 'pull.player_id_path' | 'pull.mmr_path';
  label: string;
  placeholder: string;
  help: string;
}[] = [
  {
    name: 'pull.list_path',
    label: 'Path to the player list',
    placeholder: 'data.players',
    help: 'Leave empty when the response itself is the list.',
  },
  {
    name: 'pull.player_id_path',
    label: 'Player ID field',
    placeholder: 'steam_id',
    help: 'Inside each list item.',
  },
  {
    name: 'pull.mmr_path',
    label: 'MMR field',
    placeholder: 'rating',
    help: 'A whole number, or null for no rating.',
  },
];

export interface ConnectionMappingEditorProps {
  form: Form;
  readOnly: boolean;
}

/** Where the player list, IDs, MMRs and next page are in each response. */
export function ConnectionMappingEditor({
  form,
  readOnly,
}: ConnectionMappingEditorProps) {
  const pagination = form.watch('pull.pagination_kind');
  return (
    <div className="flex flex-col gap-6" data-testid="api-connection-mapping">
      <fieldset className="flex flex-col gap-4">
        <legend className="mb-1 text-sm font-semibold">Response mapping</legend>
        <p className="text-xs text-muted-foreground">{MAPPING_PATH_HELP}</p>
        {PULL_TEXT_FIELDS.map((item) => (
          <FormField
            key={item.name}
            control={form.control}
            name={item.name}
            render={({ field }) => (
              <FormItem>
                <FormLabel>{item.label}</FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    placeholder={item.placeholder}
                    autoComplete="off"
                    spellCheck={false}
                    disabled={readOnly}
                    className="font-mono"
                    data-testid={`api-connection-${item.name.replace('.', '-')}`}
                  />
                </FormControl>
                <FormDescription>{item.help}</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        ))}
        <FormField
          control={form.control}
          name="pull.player_id_type"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Player ID type</FormLabel>
              <BrandSelect
                value={field.value}
                onValueChange={(v) =>
                  field.onChange(v as PullForm['player_id_type'])
                }
                disabled={readOnly}
              >
                <FormControl>
                  <BrandSelectTrigger data-testid="api-connection-pull-id-type">
                    <SelectValue />
                  </BrandSelectTrigger>
                </FormControl>
                <BrandSelectContent>
                  {Object.entries(PLAYER_ID_TYPE_LABELS).map(([v, label]) => (
                    <BrandSelectItem key={v} value={v}>
                      {label}
                    </BrandSelectItem>
                  ))}
                </BrandSelectContent>
              </BrandSelect>
              <FormDescription>
                Players are matched to members of this organization. Unmatched
                players are reported, never added.
              </FormDescription>
            </FormItem>
          )}
        />
      </fieldset>

      <fieldset className="flex flex-col gap-4">
        <legend className="mb-1 text-sm font-semibold">Pagination</legend>
        <FormField
          control={form.control}
          name="pull.pagination_kind"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Paging</FormLabel>
              <BrandSelect
                value={field.value}
                onValueChange={(v) =>
                  field.onChange(v as PullForm['pagination_kind'])
                }
                disabled={readOnly}
              >
                <FormControl>
                  <BrandSelectTrigger data-testid="api-connection-pull-pagination">
                    <SelectValue />
                  </BrandSelectTrigger>
                </FormControl>
                <BrandSelectContent>
                  {Object.entries(PAGINATION_LABELS).map(([v, label]) => (
                    <BrandSelectItem key={v} value={v}>
                      {label}
                    </BrandSelectItem>
                  ))}
                </BrandSelectContent>
              </BrandSelect>
              <FormMessage />
            </FormItem>
          )}
        />
        {pagination === 'page' && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormField
              control={form.control}
              name="pull.pagination_start"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>First page</FormLabel>
                  <BrandSelect
                    value={`${field.value}`}
                    onValueChange={(v) => field.onChange(Number(v))}
                    disabled={readOnly}
                  >
                    <FormControl>
                      <BrandSelectTrigger data-testid="api-connection-pull-page-start">
                        <SelectValue />
                      </BrandSelectTrigger>
                    </FormControl>
                    <BrandSelectContent>
                      <BrandSelectItem value="0">0</BrandSelectItem>
                      <BrandSelectItem value="1">1</BrandSelectItem>
                    </BrandSelectContent>
                  </BrandSelect>
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="pull.page_size"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Page size</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      inputMode="numeric"
                      min={1}
                      max={500}
                      name={field.name}
                      ref={field.ref}
                      onBlur={field.onBlur}
                      value={Number.isNaN(field.value) ? '' : field.value}
                      onChange={(e) => field.onChange(e.target.valueAsNumber)}
                      disabled={readOnly}
                      data-testid="api-connection-pull-page-size"
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="pull.has_more_path"
              render={({ field }) => (
                <FormItem className="sm:col-span-2">
                  <FormLabel>More-pages flag (optional)</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      placeholder="meta.has_more"
                      autoComplete="off"
                      className="font-mono"
                      disabled={readOnly}
                      data-testid="api-connection-pull-has-more"
                    />
                  </FormControl>
                  <FormDescription>
                    Without it, paging stops at an empty or short page.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>
        )}
        {pagination === 'cursor' && (
          <FormField
            control={form.control}
            name="pull.next_cursor_path"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Next cursor field</FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    placeholder="meta.next"
                    autoComplete="off"
                    className="font-mono"
                    disabled={readOnly}
                    data-testid="api-connection-pull-next-cursor"
                  />
                </FormControl>
                <FormDescription>
                  Sent back through the Cursor variable. A missing or empty
                  cursor ends the run.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        )}
      </fieldset>
    </div>
  );
}
