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
import { getLogger } from '~/lib/logger';
const log = getLogger('Position Edit');

type PositionFormProps = {
  form: UseFormReturn<any, any, any>;
};
export const PositionForm = ({ form }: PositionFormProps) => {
  return (
    <div className="bg-gray-00 hover:shadow-lg hover:shadow-gray-800/50 p-4 rounded-lg">
      <div className="flex-1 sm:row-span w-full">
        <h2 className="text-2xl font-bold mb-4 text-center justify-center w-full">
          Edit Positions
        </h2>
      </div>
      <div className="grid grid-flow-col grid-rows-3 gap-4 w-full align-center items-center justify-center h-auto">
        <FormField
          control={form.control}
          name="positions.carry"
          render={({ field }) => (
            <div className="flex-1 ">
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
                      <SelectValue
                        placeholder={PositionChoiceEnum[field.value]}
                      />
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
            <div className="flex-1 ">
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
                      <SelectValue
                        placeholder={PositionChoiceEnum[field.value]}
                      />
                    </SelectTrigger>
                  </FormControl>
                  {positionChoices()}
                </Select>
                <FormMessage />
              </FormItem>
            </div>
          )}
        />
        <div className="flex-1  ">
          <FormField
            control={form.control}
            name="positions.offlane"
            render={({ field }) => (
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
                      <SelectValue
                        placeholder={PositionChoiceEnum[field.value]}
                      />
                    </SelectTrigger>
                  </FormControl>
                  {positionChoices()}
                </Select>

                <FormMessage />
              </FormItem>
            )}
          />
        </div>
        <div className="flex-1 ">
          <FormField
            control={form.control}
            name="positions.soft_support"
            render={({ field }) => (
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
                      <SelectValue
                        placeholder={PositionChoiceEnum[field.value]}
                      />
                    </SelectTrigger>
                  </FormControl>
                  {positionChoices()}
                </Select>

                <FormMessage />
              </FormItem>
            )}
          />
        </div>
        <div className="flex-1 ">
          <FormField
            control={form.control}
            name="positions.hard_support"
            render={({ field }) => (
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
                      <SelectValue
                        placeholder={PositionChoiceEnum[field.value]}
                      />
                    </SelectTrigger>
                  </FormControl>
                  {positionChoices()}
                </Select>
              </FormItem>
            )}
          />
        </div>
      </div>
    </div>
  );
};
