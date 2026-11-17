import type { Control, FieldValues } from 'react-hook-form';
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import { Textarea } from '~/components/ui/textarea';
import type { EventFieldTestIds } from '../testIds';

interface IdentityFields {
  name: string;
  description: string;
}

interface Props<T extends FieldValues & IdentityFields> {
  control: Control<T>;
  testIds: Pick<EventFieldTestIds, 'name' | 'description'>;
  namePlaceholder?: string;
  descriptionPlaceholder?: string;
}

export function EventIdentityFields<T extends FieldValues & IdentityFields>({
  control: parentControl,
  testIds,
  namePlaceholder,
  descriptionPlaceholder,
}: Props<T>) {
  const control = parentControl as unknown as Control<IdentityFields>;
  return (
    <>
      <FormField
        control={control}
        name="name"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Event Name</FormLabel>
            <FormControl>
              <Input
                data-testid={testIds.name}
                placeholder={namePlaceholder}
                {...field}
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
      <FormField
        control={control}
        name="description"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Description</FormLabel>
            <FormControl>
              <Textarea
                data-testid={testIds.description}
                placeholder={descriptionPlaceholder}
                rows={2}
                {...field}
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
    </>
  );
}
