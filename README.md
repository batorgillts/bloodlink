# BloodLink

Blood bank inventory and request-matching system. CS-GY 6063 Software Engineering I, Group I2-7.

Backend: Django + Django REST Framework, PostgreSQL in production. Layered design
(request -> rules -> data) as described in the Sprint 2 design document.

## Run it locally

Use Python 3.12, matching CI. The current Django 5.1 dependency does not support Python 3.14.

## Team

| Name | Role | GitHub |
|---|---|---|
| Bat-Orgil Tsend-Ochir | Backend: auth, inventory, matching, CI | @batorgillts |
| Chenshuo Li | US-03: donor contact information (backend) | @KoharuLee |
| Miaomiao Li |US-08: search and manage Donor Records; US-11: Log in blood requests |@Miaomiao-Li-Jodie |
| Parvathi Krishnan |US-01(Backend: donor registration and donor records) |@parvathikrishnan11 |
| Shuaiyu Chen | US-04: check donation eligibility (backend); US-05: withdraw donor registration (backend); US-13: match red blood cell requests (backend) | @CSY-Eason |

**Course:** CS-GY 6063 Software Engineering I, NYU Tandon, Fall 2026
**Instructor:** Raz Saremi
**Course assistants:** Yuchen Li, Karan Allagh

**Windows (PowerShell)**

```powershell
git clone https://github.com/batorgillts/bloodlink.git
cd bloodlink
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

**macOS / Linux**

```bash
git clone https://github.com/batorgillts/bloodlink.git
cd bloodlink
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

The API is at http://127.0.0.1:8000/api/ and the admin panel at http://127.0.0.1:8000/admin/.

With no `DATABASE_URL` set, the project uses SQLite so it runs with zero setup.
CI and production use PostgreSQL through `DATABASE_URL` (see `.env.example`).

## Run the tests

```bash
ruff check .
python manage.py test
```

GitHub Actions runs the same lint and tests against PostgreSQL on every pull request
into `develop` or `main`. Frontend checks are `npm run lint`, `npm test`, and
`npm run build` from the `frontend` folder.

## Frontend

The React app in `frontend/` uses the Django API. It covers donor registration,
sign-in, contact, eligibility, and withdrawal, plus coordinator donor records,
donation entry and deletion, inventory, requests, component matching, reservation,
cancellation, donor suggestions, and per-request activity. Use synthetic data only.

From the project root, with the Python virtual environment already created:

```powershell
cd frontend
npm ci
cd ..
powershell.exe -ExecutionPolicy Bypass -File .\start-demo.ps1
```

```bash
cd frontend
npm ci
cd ..
```

Open http://127.0.0.1:5174 and leave the terminal open. Ctrl+C stops the demo.
The launcher uses `config.demo_settings` and `bloodlink-demo.sqlite3`, separate from
`db.sqlite3` and `DATABASE_URL`. Do not deploy the demo settings. Re-running the seed
keeps existing passwords, withdrawals, reservations, and requests.

| Role | Email | Initial password |
|---|---|---|
| Coordinator | coordinator@example.com | abc123456 |
| Donor | donor@example.com | abc123456 |

The donor starts with a recent plasma donation. Extra synthetic donors are
`donor1@bloodlink.example` through `donor4@bloodlink.example`, password
`BloodlinkDemo2026!`. These accounts are for local demonstration only.

To start the same demo without the launcher, use two terminals from the project root.

```powershell
.\.venv\Scripts\python.exe manage.py migrate --settings=config.demo_settings
.\.venv\Scripts\python.exe manage.py seed_demo --settings=config.demo_settings
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8001 --settings=config.demo_settings
```

```powershell
cd frontend
$env:VITE_API_URL = 'http://127.0.0.1:8001'
npm run dev -- --host 127.0.0.1 --port 5174
```

Ordinary development stays on port 8000 for Django and port 5173 for `npm run dev`
inside `frontend`. `VITE_API_URL` selects the backend.

A short coordinator-then-donor walk-through:

1. Sign in as the coordinator, search the synthetic donor, record a whole-blood donation dated today, and show the new next eligible date. Delete that entry with confirmation and show eligibility restored.
2. Record two new RBC units, A+ and O-, then create an A+ RBC request for two units.
3. Match, reserve one unit, and show Partially fulfilled. Cancel the request and show the unit available again.
4. Create another request, reserve both units, and show Fulfilled. Open eligible donor suggestions, then discard a reserved unit and confirm the warning.
5. Sign in as the donor and show history, eligibility, and a saved phone change. To show withdrawal, register a disposable donor instead of deactivating the primary demo account.

Inventory can be searched by partial unit code, donor name, or email together with the blood type, component, and status filters. A unit is stored against a source donation: whole blood can supply red cells, plasma, or platelets; red-cell donations supply red cells; plasma and platelet donations supply their own component. Recording a new donation with a unit saves both in one transaction. Editing a unit can correct its component, collection time, or source donation type and recalculates expiry. Reserved and discarded units are not editable.

Donor pages are `/me`, `/me/history`, and `/me/contact`. Registration asks for a birthday as MM/DD/YYYY and requires the password to be entered twice; only the password is sent to the API.
`GET /api/donors/me/profile/` returns only the signed-in active donor's own profile
and cannot be used to edit it. Donation history includes a `recorded_by` name, or
`Coordinator #<id>` when no name is stored. Staff email addresses are not included.

## API

| Method | Endpoint | Purpose | Who |
|---|---|---|---|
| GET | `/api/health/` | Check the server is up | Anyone |
| POST | `/api/auth/register/` (`full_name`, `email`, `password`, `date_of_birth`, `blood_type`, `phone`) | Register as a donor and sign in; returns `access` and `refresh` tokens (US-01). 400 for invalid input, 409 if the email is taken | Anyone |
| POST | `/api/auth/token/` (`email`, `password`) | Sign in (US-02, US-06). Email is case-insensitive. Returns `access`, `refresh`, `email` and `role`. 400 if a field is missing, 401 for wrong credentials or a deactivated account | Anyone |
| POST | `/api/auth/token/refresh/` (`refresh`) | Get a new access token | Anyone |
| GET | `/api/donors/me/profile/` | Read own name, blood type, status, email and phone for the donor portal; read-only | Signed-in active donor |
| GET / PATCH | `/api/donors/me/contact/` (`email` and/or `phone` for PATCH) | View or update own contact information (US-03) | Signed-in active donor |
| GET / PATCH | `/api/donors/<donor_id>/contact/` | Same operation by donor profile ID; any other ID returns 403 | Owning active donor only |
| GET | `/api/donors/?name=&email=&blood_type=` | Search donor records (US-08) | Coordinator |
| GET / PATCH / DELETE | `/api/donors/<donor_id>/` | View/edit donor records (US-08); delete with `confirm: true`, retaining history (US-10) | Coordinator |
| POST | `/api/donors/` (`full_name`, `email`, `password`, `date_of_birth`, `blood_type`, `phone`) | Create a donor account and profile for a walk-in donor (US-08); returns the profile, not login tokens | Coordinator |
| POST | `/api/donors/me/withdraw/` (`confirm: true`) | Withdraw own registration: set donor status to `withdrawn`, deactivate sign-in, and keep donation history (US-05). 400 if confirmation is missing | Signed-in active donor |
| POST | `/api/donors/<donor_id>/withdraw/` (`confirm: true`) | Same withdrawal by donor profile ID; any other ID returns 403 | Owning active donor only |
| POST | `/api/donors/<donor_id>/donations/` (`donation_type`, `donation_date`, `blood_type`, `volume_ml`) | Record a donation entry (US-09); returns the entry with recalculated history and eligibility. 400 if invalid or not yet eligible, 409 if the donor is not active | Coordinator |
| GET | `/api/requests/?status=<value>` | List all blood requests by default; repeat `status` to filter by multiple values, such as `?status=pending&status=fulfilled`. Status values are case-sensitive and must be lowercase: `pending`, `partially_fulfilled`, `fulfilled`, `cancelled`; invalid values return 400 (US-11) | Coordinator |
| POST | `/api/requests/` (`blood_type`, `component`, `quantity`) | Log a new blood request with `pending` status, coordinator and timestamp (US-11) | Coordinator |
| GET | `/api/requests/<request_id>/` | Open one request with `reserved_units`: the units currently held for it (unit id, code, blood type, component, expiry, reserved time). 404 if not found (US-16) | Coordinator |
| POST | `/api/units/` (`unit_code`, `blood_type`, `component`, `collected_at`, `donor_id`, plus `donation_id` OR `donation_type` and `volume_ml`) | Record a unit linked to its source donation. A new donation and unit are saved atomically; an existing donation is reused without changing eligibility. Expiry follows shelf-life rules. 400 for invalid source, blood type/date mismatch or ineligible donation; 409 for duplicate unit code | Coordinator |
| GET | `/api/units/?blood_type=&component=&status=` | View inventory, earliest expiry first; `status=available` excludes expired units (US-07) | Coordinator |
| GET | `/api/inventory/dashboard/` | Inventory dashboard (US-12): low-stock alerts, the expiring-soon report grouped by component, and available stock with the unit closest to expiry for each blood type and component. Only usable units (available, not expired) count | Coordinator |
| GET, PUT | `/api/inventory/thresholds/` | List or set a low-stock threshold per blood type and component (US-12), with an optional `expiring_soon_days` override. 400 if `minimum_units` is not a positive whole number, or the window is not shorter than the component's shelf life | Coordinator |
| GET | `/api/units/<unit_id>/` | View one unit, including discard details and `can_discard` (false once discarded) | Coordinator |
| PATCH | `/api/units/<unit_id>/` (`component`, `collected_at`, optional `donation_type`) | Correct an unreserved, non-discarded unit. Recalculates expiry; calendar-date corrections update the source donation and shift linked units together. Explicit source-type corrections recalculate eligibility and must support every linked component. No extra donation is created | Coordinator |
| POST | `/api/units/<unit_id>/discard/` (`reason`, `confirm`) | Discard a unit with reason `expired`, `damaged`, `failed_testing` or `other` (US-17). 400 if the reason is missing, or not `expired` for an expired unit; 409 if already discarded; 409 with `confirm_required` and the request ID if the unit is reserved, until sent again with `confirm: true`. Releases the reservation and sets the request to partially fulfilled (or pending if none left) | Coordinator |
| GET | `/api/requests/<request_id>/matches/` | Match available, unexpired units for one request. Red blood cells use ABO/Rh rules (US-13); plasma uses reversed ABO and ignores Rh (US-14). An empty match returns `No compatible units available` | Coordinator |
| GET | `/api/requests/<request_id>/donor-suggestions/` | List active donors whose blood type is compatible under the component's rules and who are eligible today for the matching donation type (red cells: whole blood, plasma: plasma, platelets: platelets). Shows name, blood type, last donation date, email and phone, identical type first. Empty list returns `No eligible donors found.`; 409 for a fulfilled or cancelled request (US-18) | Coordinator |
| POST | `/api/requests/<request_id>/cancel/` (`confirm: true`) | Cancel a pending or partially fulfilled request and release its reserved units (US-19); expired units remain expired | Coordinator |
| GET | `/api/requests/<request_id>/history/` | View a request's event history, including cancellation time and coordinator (US-19). Each match, reservation and status change is included (US-20). PUT, PATCH and DELETE are rejected | Coordinator |
| GET | `/api/requests/history/?logged_from=&logged_to=` | Audit log of every request: blood type, component, quantity, logged time, coordinator, and events. Both dates are inclusive (`YYYY-MM-DD`) and must be sent together. An empty range returns `No requests found for this period` (US-20) | Coordinator |
| POST | `/api/requests/<id>/reserve/` (`unit_ids`) | Reserve selected compatible units in one transaction; request becomes `partially_fulfilled` or `fulfilled` (US-16). 400 if too many or incompatible units, 409 if a unit is no longer available or the request is closed, 404 if not found | Coordinator |
| GET | `/api/forecast/weekly/` | Return next week's request-unit forecast and weekly history per blood type/component. Uses up to 12 weeks, minimum 4; canceled requests are excluded. A shorter supported window reports `history_weeks_used`; under 4 weeks predictions are null with `history_status: insufficient_history` | Coordinator |

Protected endpoints require `Authorization: Bearer <access token>`.
Without it they return 401. A signed-in donor calling a coordinator-only endpoint gets 403.

US-03 returns 400 for invalid contact input, 403 for non-owner/coordinator access,
404 when the signed-in donor has no profile, and 409 for an email already in use.
The email is the account's sign-in email; changing it changes the email used for future sign-ins.
Only email and phone can be updated. 

US-10-coordinator deletion:

- `DELETE /api/donors/<donor_id>/donations/<donation_id>/`: remove one donation and
  return recalculated eligibility and history.
- `DELETE /api/donors/<donor_id>/`: mark a donor deleted and disable sign-in,
  retaining linked donation history.
- Both require a coordinator token and JSON `{"confirm": true}`. 
- US-08 search uses active donor filters and is tested with deletion. Matching
  and React UI still need integration before the full story is Done.


US-08 donor search, walk-in registration, profile updates, and coordinator-only
record access are covered by `donors/test_records.py`.

US-05 withdraws the signed-in donor's own registration. The donor row stays, with
status `withdrawn` and `User.is_active` set to false, so the same email and password
can no longer sign in. Donation rows are not removed. Coordinator search already
returns only `active` donors, so a withdrawn donor is left out of those results.
A coordinator can still open that donor's record and donation history by id.
Missing confirmation is 400.
Another donor, a coordinator, or an already withdrawn or deleted profile is 403.
A signed-in donor with no profile is 404. A withdrawn account's later requests,
including sign-in and token refresh, are 401.

US-09 donation recording is covered by `donors/test_donations.py`.

US-11 tests are in `request/test_records.py`.

US-13 matches a Red Blood Cells request at `GET /api/requests/<request_id>/matches/`.
The rules are seeded `CompatibilityRule` rows, not hard-coded in the view. O-negative
units are compatible with every requested type, and an AB-positive request accepts
every blood type. An A-positive request returns A+, A-, O+, and O- units. An
O-negative request returns only O-negative units. Exact type is listed before
compatible substitutes, then earliest expiry. Each unit includes its id, unit code,
blood type, and expiry. Plasma, platelets, expired, reserved, and discarded units
are left out. Matching does not reserve units or change the request. A donor gets
403, a missing token gets 401, and an unknown request gets 404. Tests are in
`request/test_rbc_matching.py`.

US-07 tests are in `inventory/tests.py`.

US-19 tests are in `request/test_cancellation.py`.

US-17 tests are in `inventory/test_discard.py`.

US-18 tests are in `request/test_donor_suggestions.py`.

US-12 tests are in `inventory/test_stock_alerts.py` and `frontend/src/StockAlerts.test.jsx`.

US-20 tests are in `request/test_request_history.py`. Running a match records the
units that were returned, with the coordinator and time. History rows cannot be
updated or deleted. The coordinator page is `/request-history`.

## Project layout

| Folder | Component (Sprint 2 C4 diagram) |
|---|---|
| `accounts/` | Authentication & Access: custom User with role, permissions, donor registration |
| `donors/` | Donor & Donation Management: profile and own-contact API; services and repository for US-03 |
| `request/` | Incoming blood requests (US-11) |
| `inventory/` | Inventory Management: blood units and shelf-life rules (US-07) |
| `config/` | Settings, URLs, shared exceptions, shared choices (blood types and components) |

## Team workflow

- Branch from `develop` as `feature/US-XX-short-name`.
- Open a pull request into `develop`. CI must pass and one teammate must approve.
- No direct or force pushes to `develop` or `main`.
- At the end of a sprint, `develop` is merged into `main` and tagged (`sprint-3`).
