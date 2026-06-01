export function ProfileSkeleton() {
  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="h-6 w-1/3 animate-pulse rounded bg-base-200" />
      <div className="h-10 w-full animate-pulse rounded bg-base-200" />
      <div className="h-10 w-full animate-pulse rounded bg-base-200" />
    </div>
  );
}
