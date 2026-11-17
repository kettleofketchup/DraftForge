import * as React from 'react';
import type { FieldErrors, FieldValues, UseFormReturn } from 'react-hook-form';
import { toast } from 'sonner';
import { FormDialog } from '~/components/ui/dialogs';
import { Form } from '~/components/ui/form';
import { Tabs, TabsContent } from '~/components/ui/tabs';
import { FormTabsList } from './FormTabsList';
import {
  EVENT_TAB_META,
  eventTabForField,
  type EventFormTabValue,
} from './tabs';

export interface EventFormTab {
  value: EventFormTabValue;
  content: React.ReactNode;
  /** Mount on first visit, then stay mounted. */
  lazy?: boolean;
}

export interface EventFormDialogHandle {
  selectTab: (value: EventFormTabValue) => void;
}

export interface EventFormDialogProps<
  TIn extends FieldValues,
  TOut extends FieldValues,
> {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  submitLabel: string;
  form: UseFormReturn<TIn, unknown, TOut>;
  onValid: (data: TOut) => void | Promise<void>;
  isSubmitting: boolean;
  tabs: EventFormTab[];
  /** Triggers get `${tabTestIdPrefix}-tab-${value}`. */
  tabTestIdPrefix: string;
  /** Rendered instead of the tabs when set. */
  loading?: React.ReactNode;
  tabRef?: React.Ref<EventFormDialogHandle>;
  'data-testid'?: string;
}

/** Full-screen tabbed dialog shared by the event, series and defaults forms. */
export function EventFormDialog<
  TIn extends FieldValues,
  TOut extends FieldValues,
>({
  open,
  onOpenChange,
  title,
  description,
  submitLabel,
  form,
  onValid,
  isSubmitting,
  tabs,
  tabTestIdPrefix,
  loading,
  tabRef,
  'data-testid': dataTestId,
}: EventFormDialogProps<TIn, TOut>) {
  const first = tabs[0].value;
  const [tab, setTab] = React.useState<EventFormTabValue>(first);
  const [visited, setVisited] = React.useState<Set<EventFormTabValue>>(
    () => new Set([first]),
  );
  const [wasOpen, setWasOpen] = React.useState(open);
  if (open !== wasOpen) {
    setWasOpen(open);
    if (open) {
      setTab(first);
      setVisited(new Set([first]));
    }
  }

  const selectTab = React.useCallback((value: EventFormTabValue) => {
    setTab(value);
    setVisited((prev) => (prev.has(value) ? prev : new Set(prev).add(value)));
  }, []);
  React.useImperativeHandle(tabRef, () => ({ selectTab }), [selectTab]);

  const onInvalid = (errors: FieldErrors<TIn>) => {
    const [key, error] = Object.entries(errors)[0] ?? [];
    if (!key) return;
    const mapped = eventTabForField(key);
    selectTab(tabs.some((t) => t.value === mapped) ? mapped : first);
    const message = (error as { message?: unknown } | undefined)?.message;
    toast.error('Please fix the highlighted fields', {
      description: typeof message === 'string' ? message : undefined,
    });
  };

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description={description}
      submitLabel={submitLabel}
      isSubmitting={isSubmitting}
      onSubmit={form.handleSubmit(onValid, onInvalid)}
      size="screen"
      data-testid={dataTestId}
    >
      {loading ?? (
        <Form {...form}>
          <Tabs
            value={tab}
            onValueChange={(v) => selectTab(v as EventFormTabValue)}
            className="gap-4"
          >
            <FormTabsList
              className="sticky top-0 z-10 bg-background"
              tabs={tabs.map((t) => ({
                value: t.value,
                ...EVENT_TAB_META[t.value],
              }))}
              testIdPrefix={tabTestIdPrefix}
            />
            {tabs.map((t) => (
              <TabsContent
                key={t.value}
                value={t.value}
                forceMount={!t.lazy || visited.has(t.value) ? true : undefined}
                // Radix leaves force-mounted panels visible; hide inactive ones.
                hidden={tab !== t.value}
                className="mx-auto flex w-full max-w-4xl flex-col gap-4"
              >
                {t.content}
              </TabsContent>
            ))}
          </Tabs>
        </Form>
      )}
    </FormDialog>
  );
}
