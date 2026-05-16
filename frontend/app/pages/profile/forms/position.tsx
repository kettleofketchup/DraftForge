import { type UseFormReturn } from 'react-hook-form';

import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Select, SelectTrigger, SelectValue } from '~/components/ui/select';
import {
  CarrySVG,
  HardSupportSVG,
  MidSVG,
  OfflaneSVG,
  SoftSupportSVG,
} from '~/components/user/positions/icons';
import {
  PositionChoiceEnum,
  positionChoices,
} from '~/components/user/positions/positionEdit';

type PositionFormProps = {
  form: UseFormReturn<any, any, any>;
};

type PositionFieldsProps = {
  form: UseFormReturn<any, any, any>;
  /** Tailwind grid classes for the field grid. Override when embedding in a
   *  smaller container (e.g. the EventSignupModal uses 2 fixed columns). */
  gridClassName?: string;
};

const DEFAULT_GRID_CLASS =
  'sm:grid sm:grid-flow-col grid-rows-1 sm:grid-rows-3 gap-4 w-full align-center items-center justify-center h-auto';

/** Inner-only variant of PositionForm — the 5 per-role priority selects without
 *  the page heading or card-shadow wrapper. Use this inside other modals. */
export const PositionFormFields = ({
  form,
  gridClassName,
}: PositionFieldsProps) => {
  return (
    <div className={gridClassName ?? DEFAULT_GRID_CLASS}>
      <FormField
        control={form.control}
        name="positions.carry"
        render={({ field }) => (
          <div className="flex-1">
            <FormItem>
              <FormLabel>
                Carry <CarrySVG />
              </FormLabel>
              <Select
                onValueChange={(value) => field.onChange(Number(value))}
                defaultValue={field.value?.toString()}
              >
                <FormControl>
                  <SelectTrigger>
                    <SelectValue placeholder={PositionChoiceEnum[field.value]} />
                  </SelectTrigger>
                </FormControl>
                {positionChoices()}
              </Select>
              <FormMessage />
            </FormItem>
          </div>
        )}
      />
      <FormField
        control={form.control}
        name="positions.mid"
        render={({ field }) => (
          <div className="flex-1">
            <FormItem>
              <FormLabel>
                Middle <MidSVG />
              </FormLabel>
              <Select
                onValueChange={(value) => field.onChange(Number(value))}
                defaultValue={field.value?.toString()}
              >
                <FormControl>
                  <SelectTrigger>
                    <SelectValue placeholder={PositionChoiceEnum[field.value]} />
                  </SelectTrigger>
                </FormControl>
                {positionChoices()}
              </Select>
              <FormMessage />
            </FormItem>
          </div>
        )}
      />
      <FormField
        control={form.control}
        name="positions.offlane"
        render={({ field }) => (
          <div className="flex-1">
            <FormItem>
              <FormLabel>
                Offlane <OfflaneSVG />
              </FormLabel>
              <Select
                onValueChange={(value) => field.onChange(Number(value))}
                defaultValue={field.value?.toString()}
              >
                <FormControl>
                  <SelectTrigger>
                    <SelectValue placeholder={PositionChoiceEnum[field.value]} />
                  </SelectTrigger>
                </FormControl>
                {positionChoices()}
              </Select>
              <FormMessage />
            </FormItem>
          </div>
        )}
      />
      <FormField
        control={form.control}
        name="positions.soft_support"
        render={({ field }) => (
          <div className="flex-1">
            <FormItem>
              <FormLabel>
                Soft Support <SoftSupportSVG />
              </FormLabel>
              <Select
                onValueChange={(value) => field.onChange(Number(value))}
                defaultValue={field.value?.toString()}
              >
                <FormControl>
                  <SelectTrigger>
                    <SelectValue placeholder={PositionChoiceEnum[field.value]} />
                  </SelectTrigger>
                </FormControl>
                {positionChoices()}
              </Select>
              <FormMessage />
            </FormItem>
          </div>
        )}
      />
      <FormField
        control={form.control}
        name="positions.hard_support"
        render={({ field }) => (
          <div className="flex-1">
            <FormItem>
              <FormLabel>
                Hard Support <HardSupportSVG />
              </FormLabel>
              <Select
                onValueChange={(value) => field.onChange(Number(value))}
                defaultValue={field.value?.toString()}
              >
                <FormControl>
                  <SelectTrigger>
                    <SelectValue placeholder={PositionChoiceEnum[field.value]} />
                  </SelectTrigger>
                </FormControl>
                {positionChoices()}
              </Select>
              <FormMessage />
            </FormItem>
          </div>
        )}
      />
    </div>
  );
};

export const PositionForm = ({ form }: PositionFormProps) => {
  return (
    <div className="items-center content-center justify-center flex-cols hover:shadow-lg hover:shadow-gray-800/50 p-4 rounded-lg w-full">
      <div className="flex sm:row-span w-full">
        <h2 className="text-2xl font-bold mb-4 text-center justify-center w-full">
          Edit Positions
        </h2>
      </div>
      <PositionFormFields form={form} />
    </div>
  );
};
