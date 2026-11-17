# BloodLink frontend demo

React pages connect to the Django API and persist real changes to the selected local database. The UI covers donor registration/login/contact/eligibility/withdrawal; coordinator donor search, walk-in registration, editing, donation entry and deletion; inventory recording/filtering/discard; requests, component-specific matching, reservation, cancellation, donor suggestions and per-request activity.

This is a functional demo following the design's workflows, not a pixel-exact recreation of all 70 PDF states. Use synthetic information only.

## Start the isolated classroom demo on Windows

From the project root, with the existing Python 3.12 virtual environment and frontend dependencies installed:

```powershell
cd D:\Courses\SE\GroupProject\bloodlink
powershell.exe -ExecutionPolicy Bypass -File .\start-demo.ps1
```

Open http://127.0.0.1:5174 and keep the terminal open. Ctrl+C stops the backend and the frontend child process. The launcher checks for occupied ports first and will not stop existing services. If the demo is already running, open its URL instead of launching it twice.

The demo explicitly uses `config.demo_settings` and `bloodlink-demo.sqlite3`, independent of `db.sqlite3` and `DATABASE_URL`. Never deploy the demo settings. It creates synthetic accounts, 13 inventory units and three initial requests. Re-running the seed command preserves changes and never resets passwords, withdrawals, reservations or requests. A new calendar day gets a fresh inventory batch; on the same day, use the UI to add new units and requests for another rehearsal.

| Role | Email | Initial password |
|---|---|---|
| Coordinator | coordinator@example.com | abc123456 |
| Donor | donor@example.com | abc123456 |

The donor initially has a recent plasma donation, so the overview can show eligible and not-yet-eligible states together. Additional synthetic donors use `donor1@bloodlink.example` through `donor4@bloodlink.example` with the initial password `BloodlinkDemo2026!`. These are local demonstration credentials only.

For a fresh checkout, install dependencies before starting:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
cd frontend
npm.cmd ci
cd ..
```

## Start the two services manually

Terminal 1, project root:

```powershell
.\.venv\Scripts\python.exe manage.py migrate --settings=config.demo_settings
.\.venv\Scripts\python.exe manage.py seed_demo --settings=config.demo_settings
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8001 --settings=config.demo_settings
```

Terminal 2:

```powershell
cd D:\Courses\SE\GroupProject\bloodlink\frontend
$env:VITE_API_URL = 'http://127.0.0.1:8001'
npm.cmd run dev -- --host 127.0.0.1 --port 5174
```

The ordinary development setup remains `python manage.py runserver` on 8000 and `npm.cmd run dev` on 5173, using existing accounts and `db.sqlite3` or `DATABASE_URL`. `VITE_API_URL` selects the backend. Vite uses strict ports to avoid silently moving to an origin the backend rejects.

## Suggested 8-minute demonstration

1. Coordinator signs in, opens Donor registry and searches for the synthetic donor. Record a whole-blood donation using today's bank date; show the changed next eligible date. Delete that entry with confirmation and show eligibility restored.
2. Record two new RBC units, A+ and O-, with unique codes and recent collection times. Create an A+ RBC request for two units.
3. Find matches, reserve one and show Partially fulfilled. Cancel the request and show that the unit is available again.
4. Create another request and reserve the two units to show Fulfilled. Briefly show plasma/platelet matching using separate requests and matching component inventory.
5. On an open request, show eligible donor suggestions. In inventory, discard a reserved unit: first choose a reason, then confirm the server's warning about its request. Reopen that request to see its reduced reserved quantity.
6. Sign out and sign in as the donor; show history/eligibility, update the phone and reload to demonstrate persistence. For withdrawal, register a disposable synthetic donor rather than deactivating the primary demo account.

All destructive UI actions require confirmation. Reserved-unit discard additionally waits for the backend's conflict warning before sending `confirm: true`. Donor deletion/withdrawal retains donation history. Donation recording and blood-unit inventory recording remain separate workflows, as in the backend design.

## Validation

```powershell
# From project root
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe manage.py test
# From frontend
npm.cmd run lint
npm.cmd test
npm.cmd run build
```

Verified locally: 283 backend tests (282 passed, one PostgreSQL-only concurrency test skipped), 37 frontend tests, lint and build. Browser checks exercised login, registration, donor management, donation creation/deletion and eligibility recalculation, contact persistence, all three component matching/reservation paths, cancellation, reserved-unit discard, donor suggestions, activity and withdrawal/login rejection. Desktop and 390px mobile layouts were inspected. Browser verification uses synthetic demo data, so the demo database contains completed/cancelled requests and a discarded unit afterwards.

Remaining: verify the row-lock concurrency test on PostgreSQL through CI; measure the Sprint 1 requirement of matching 10,000 units within two seconds; review/merge the local changes; deploy to Render only if a shared URL is required. The existing CI already runs frontend lint/tests/build and backend tests with PostgreSQL. US-12 alerts and full US-20 audit filtering/export remain stretch work. Per-request activity here is only a basic event view. Automatic token refresh, exact Figma spacing and richer field-level validation can follow the basic demo; expired sessions currently return to sign-in.

## Donor portal pages

- `/me`: profile identity, recorded-donation and waiting-period counts, eligibility per type, the latest three donations, and first-donation guidance.
- `/me/history`: all donations, donation-type filtering, record IDs and recorder labels; cards replace the desktop table on smaller screens.
- `/me/contact`: read-only name and blood type, email/phone editing with inline client/server validation, cancel-to-last-saved values, and confirmed withdrawal.

`GET /api/donors/me/profile/` returns only the authenticated active donor's `donor_id`, `full_name`, `blood_type`, `status`, `email` and `phone`. It is read-only; profile edits still belong to coordinators, and contact changes still use the existing `PATCH /api/donors/me/contact/` contract. Donors cannot select another profile via an ID parameter.

Donation rows returned by eligibility and donor record operations now include a `recorded_by` display label. It uses the coordinator's recorded first/last name, or `Coordinator #<id>` when no name is stored; staff email and credentials are not exposed. The recorder is loaded with the history query to avoid an extra query per row. These are additive API fields and require no schema migration.

Portal-specific regression checks are in `donors/test_portal.py` and `frontend/src/DonorPortal.test.jsx`. Browser checks use a separate synthetic account so existing demonstration accounts remain untouched.

Registration uses a fixed English MM/DD/YYYY birthday field and converts valid calendar dates to ISO for the API. Confirm password must match before registration is submitted; the confirmation is not stored or sent to the backend.

All application forms use English validation, including required fields, email, phone, numeric values and calendar dates. Native constraint attributes are intentionally replaced by shared validation because browser hover messages follow the operating-system language even with noValidate. Date entry uses MM/DD/YYYY; collection timestamps use MM/DD/YYYY HH:mm (24-hour local time). Displayed timestamps use en-US. Verified login, registration, donor contact, walk-in/edit/donation forms and inventory/request validation in an Edge browser context with zh-CN locale.
