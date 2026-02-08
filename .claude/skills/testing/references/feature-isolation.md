# Feature-Isolated Test Data

Each feature's E2E tests MUST use dedicated test data. Never reuse another feature's org/league/tournament.

## Why

- Parallel test execution can corrupt shared state
- Adding/modifying data for one feature can break another's assertions
- Debugging failures is harder when test data is entangled

## Pattern (4 Steps)

### Step 1: Data Definitions (`backend/tests/data/`)

Create entities with unique PKs and identifiers:

```python
# organizations.py
CSV_ORG: TestOrganization = TestOrganization(
    pk=3,                          # Unique PK (check existing: DTX=1, Test=2)
    name="CSV Import Org",         # Unique name
    description="Isolated organization for CSV import E2E tests.",
    timezone="America/New_York",
)
CSV_ORG_NAME = CSV_ORG.name

# leagues.py
CSV_LEAGUE: TestLeague = TestLeague(
    pk=3,                          # Unique PK
    name="CSV Import League",
    steam_league_id=17931,         # Unique (DTX=17929, Test=17930)
    organization_names=["CSV Import Org"],
)

# tournaments.py
CSV_IMPORT_TOURNAMENT: TestTournament = TestTournament(
    name="CSV Import Tournament",
    league_name="CSV Import League",
    teams=[],                      # Empty if feature populates its own
)

# users.py (if needed)
CSV_IMPORT_USERS: list[TestUser] = [
    TestUser(pk=1040, ...),        # Unique PK range (check existing ranges)
]
```

Export all from `backend/tests/data/__init__.py`.

### Step 2: Populate Function (`backend/tests/populate/`)

Create `populate_{feature}.py`:

```python
def populate_{feature}_data(force=False):
    # 1. Create org
    org, _ = Organization.objects.update_or_create(name=FEATURE_ORG.name, defaults={...})

    # 2. Create league
    league, _ = League.objects.update_or_create(steam_league_id=FEATURE_LEAGUE.steam_league_id, defaults={...})

    # 3. Create tournament (if needed)
    tournament, _ = Tournament.objects.update_or_create(name=FEATURE_TOURNAMENT.name, defaults={...})

    # 4. Grant admin access (so E2E tests can log in)
    admin = CustomUser.objects.filter(pk=ADMIN_USER.pk).first()
    if admin and admin not in org.admins.all():
        org.admins.add(admin)

    # 5. Create feature-specific users (if needed)
    # 6. Generate fixture files (if needed, with PermissionError guard for Docker)
```

Wire into `populate_all()` in `__init__.py` (imports + function call + `__all__`).

### Step 3: Fixture Files (Optional)

For static test data (CSVs, images, etc.):
- Commit to `frontend/tests/playwright/fixtures/{feature}/`
- Populate function can regenerate but must handle Docker gracefully:

```python
try:
    os.makedirs(fixture_dir, exist_ok=True)
    # write files...
except PermissionError:
    print("Skipping fixture generation (Docker container can't write to frontend volume)")
    return
```

### Step 4: E2E Tests Look Up by Name

Never hardcode PKs. Find entities by name via API:

```typescript
// GOOD
const orgsResp = await context.request.get(`${API_URL}/organizations/`);
const csvOrg = orgs.find((o: { name: string }) => o.name === 'CSV Import Org');
await visitAndWait(page, `/organizations/${csvOrg.pk}/`);

// BAD
await visitAndWait(page, '/organizations/3/');  // Fragile!
```

## Current PK Allocations

| Entity | PK Range | Feature |
|--------|----------|---------|
| Org | 1 | DTX (main) |
| Org | 2 | Test (basic E2E) |
| Org | 3 | CSV Import |
| League | 1 (steam=17929) | DTX |
| League | 2 (steam=17930) | Test |
| League | 3 (steam=17931) | CSV Import |
| Users | 1001-1003 | Site-level (admin/staff/regular) |
| Users | 1010-1011 | Claim profile |
| Users | 1020-1021 | Org roles |
| Users | 1030-1031 | League roles |
| Users | 1040-1044 | CSV Import |

When adding new features, pick the next available PK range.
