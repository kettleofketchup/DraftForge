import * as React from 'react';
import {
  useFormState,
  type FieldErrors,
  type FieldValues,
  type UseFormReturn,
} from 'react-hook-form';
import { toast } from 'sonner';
import {
  SettingsDialog,
  type SettingsDialogHandle,
} from '~/components/patterns/SettingsDialog';
import { Form } from '~/components/ui/form';
import { EVENT_SECTION_FIELDS } from './settingsFields';
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

/** Full-screen settings dialog shared by the event, series and defaults forms. */
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
  const sections = React.useRef<SettingsDialogHandle<EventFormTabValue>>(null);
  React.useImperativeHandle(
    tabRef,
    () => ({ selectTab: (v) => sections.current?.selectSection(v) }),
    [],
  );

  // Not form.formState: that would re-render the tab contents on error changes.
  const { errors } = useFormState({ control: form.control });
  const errorKeys = Object.keys(errors).filter((k) => k !== 'root');
  const first = tabs[0].value;
  // Where the field renders in this modal, else its registry home, else the first tab.
  const tabFor = (field: string) => {
    const mapped =
      sections.current?.sectionOfField(field) ?? eventTabForField(field);
    return tabs.some((t) => t.value === mapped) ? mapped : first;
  };

  const onInvalid = (errors: FieldErrors<TIn>) => {
    const [key, error] = Object.entries(errors)[0] ?? [];
    if (!key) return;
    sections.current?.selectSection(tabFor(key));
    const message = (error as { message?: unknown } | undefined)?.message;
    toast.error('Please fix the highlighted fields', {
      description: typeof message === 'string' ? message : undefined,
    });
  };

  return (
    <Form {...form}>
      <SettingsDialog
        open={open}
        onOpenChange={onOpenChange}
        title={title}
        description={description}
        submitLabel={submitLabel}
        isSubmitting={isSubmitting}
        // Opening should not pop the search keyboard on phones; / and Ctrl/Cmd+K reach it.
        autoFocus={false}
        onSubmit={form.handleSubmit(onValid, onInvalid)}
        loading={loading}
        sectionRef={sections}
        testIdPrefix={tabTestIdPrefix}
        data-testid={dataTestId}
        sections={tabs.map((t) => ({
          ...t,
          ...EVENT_TAB_META[t.value],
          fields: EVENT_SECTION_FIELDS[t.value],
          invalid: errorKeys.some((k) => tabFor(k) === t.value),
        }))}
      />
    </Form>
  );
}
