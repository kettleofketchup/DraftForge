import { Skeleton } from '~/components/ui/skeleton';

export default function Placeholder() {
  return (
    <div className="flex w-52 flex-col gap-4">
      <div className="flex items-center gap-4">
        <Skeleton className="h-4 w-28 bg-base-300" />
        <Skeleton className="h-16 w-16 shrink-0 rounded-full bg-base-300" />
        <div className="flex flex-col gap-4">
          <Skeleton className="h-4 w-28 bg-base-300" />
          <Skeleton className="h-4 w-20 bg-base-300" />
          <Skeleton className="h-4 w-28 bg-base-300" />
        </div>
      </div>
      <Skeleton className="h-32 w-full bg-base-300" />
      <Skeleton className="h-4 w-28 bg-base-300" />
      <Skeleton className="h-4 w-full bg-base-300" />
      <Skeleton className="h-4 w-full bg-base-300" />
      <Skeleton className="h-32 w-full bg-base-300" />
      <div className="flex items-center gap-4">
        <Skeleton className="h-16 w-16 shrink-0 rounded-full bg-base-300" />
        <div className="flex flex-col gap-4">
          <Skeleton className="h-4 w-20 bg-base-300" />
          <Skeleton className="h-4 w-28 bg-base-300" />
        </div>
      </div>
      <Skeleton className="h-32 w-full bg-base-300" />
    </div>
  );
}
