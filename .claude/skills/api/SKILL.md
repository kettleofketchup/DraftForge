---
name: api
description: DraftForge frontend↔backend API binding: axios client, Zod response schemas, TanStack Query hooks, DRF errors, and generated Zod from pydantic models. Use when adding or changing an endpoint call.
---

# API binding

Every HTTP call from the frontend goes through one client, returns data that a Zod
schema has parsed, and reaches components through a query hook. The Zod schema either
comes from a backend pydantic model (generated) or mirrors a DRF serializer (hand-written).

WebSocket messages (`app/lib/websocket/`) are out of scope.

## Layout

New code lives in a feature folder (`app/features/promotion/` is the reference):

| File | Holds |
|---|---|
| `schemas.ts` | Zod schemas + `z.infer` types, or re-exports from a `*.generated.ts` |
| `api.ts` | one async function per endpoint: call, parse, return |
| `queryKeys.ts` / `queries.ts` | key factories; `useQuery` / `useMutation` hooks |
| `__tests__/` | Vitest for `api.ts` parsing and `queries.ts` invalidation |

Legacy `app/components/api/*API.tsx` use `axios.get<T>()` with no validation. Don't copy
that. When you touch one of those functions, move it to the parse pattern below.

## Client

```ts
import api from '~/components/api/axios';
```

That instance sets the SSR/browser base URL, sends cookies, adds `X-CSRFToken` on
writes and handles Discord Activity auth. Never import `axios` directly for requests,
never use the bare instance in `components/api/utils.tsx`, and never call `fetch`. Paths
are relative to `/api` and keep DRF's trailing slash: `api.get(`/events/${id}/`)`.
Pass query strings via `{ params }`.

## Endpoint functions

```ts
export async function getPromoTemplates(orgId: number): Promise<PromoTemplate[]> {
  const response = await api.get(`${base(orgId)}/templates/`);
  return z.array(PromoTemplateSchema).parse(response.data);
}
```

- Parse every response body with `Schema.parse`. Don't use `api.get<T>()`: the type
  argument is an unchecked cast.
- Keep the wire field names. DRF and pydantic API models send snake_case, so schemas use
  snake_case too. Rename only in a mapping function, never in the schema.
- Type request bodies: generated request type, form schema output, or a local `type`.
- Map "expected" statuses at the edge: `isAxiosError(err) && err.response?.status === 404`
  → return `null` (see `getPasswordInfo` in `app/components/lobby/api.ts`). Let the rest throw.

## Where the schema comes from

1. **The backend has (or should have) a pydantic model for the payload.** Use a
   generated binding; don't hand-write it. Follow `references/pydantic-bindings.md`.
   Good fits: views that `Model.model_validate(request.data)` and return
   `model.model_dump(mode="json")`, new non-model endpoints, and static catalogues.
2. **The endpoint returns a DRF serializer.** Hand-write the Zod schema in `schemas.ts`,
   field for field from the serializer (`fields`, `read_only`, `SerializerMethodField`
   return types, `allow_null` → `.nullable()`, `required=False` → `.optional()`).
   Note the serializer path in a one-line comment above the schema.
   For a payload where drift would hurt, pin it with a fixture both test suites read
   (`backend/org/tests/render_fixture.json` ↔ `frontend/app/features/promotion/__tests__/`,
   compared with `cmp` in the `unit` CI job).

Don't add drf-spectacular/OpenAPI codegen for one endpoint. Raise it with the user first.

## Queries and mutations

- Key factories in `queryKeys.ts`, with scope first and the viewer in the key when the
  response depends on permissions: `promotionKeys.templates(orgId, viewerPk)`
  (`app/features/org-features/queryKeys.ts`).
- `useQuery({ queryKey, queryFn: () => getX(...), enabled })`. Gate on permission flags
  rather than letting the request 403.
- Mutations invalidate or `setQueryData` the affected keys in `onSuccess`; prefix keys
  let you invalidate a whole feature.

## Errors

- User-facing message: `extractApiError(err)` from `~/lib/apiError` (handles DRF
  `error` / `detail` / field-list shapes), then `toast.error(msg ?? fallback)`.
- A `ZodError` from `parse` is a contract bug, not a user error. Don't swallow it. Log it
  via `getLogger` and fix the schema or the backend.
- Field errors on forms: map DRF `{field: [msg]}` onto React Hook Form
  `form.setError(field, { message })`. Form schemas themselves follow the
  `zod-form-validation` skill.

## Tests

- `api.ts`: hoist the mocks and replace the client, as in
  `app/components/api/__tests__/tournamentListApi.test.ts`:
  `const { get } = vi.hoisted(() => ({ get: vi.fn() }));`
  `vi.mock('~/components/api/axios', () => ({ default: { get } }));`
  Return a realistic body and assert the parsed result; also assert that a malformed
  body rejects with a `ZodError`.
- `queries.ts`: mock `../api`, render the hook in a `QueryClientProvider` with
  `retry: false`, assert invalidation (`app/features/promotion/__tests__/queries.test.tsx`).
- Backend: test the view's JSON with `APIClient`; for pydantic payloads also
  `Model.model_validate(response.json())`.

## Checklist

- [ ] Call goes through `~/components/api/axios`, path has a trailing slash
- [ ] Response parsed by a Zod schema; no `get<T>()` casts
- [ ] Schema generated from pydantic, or mirrors the serializer with its path noted
- [ ] Query key factory + hook; mutations invalidate what they change
- [ ] Errors via `extractApiError`; Zod errors not swallowed
- [ ] Vitest for parse + hook; backend view test; `just py::gen-* --check` if generated
