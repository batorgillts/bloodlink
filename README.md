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
| Shuaiyu Chen | US-04: check donation eligibility (backend); US-05: withdraw donor registration (backend) | @CSY-Eason |

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
into `develop` or `main`.

## API

| Method | Endpoint | Purpose | Who |
|---|---|---|---|
| GET | `/api/health/` | Check the server is up | Anyone |
| POST | `/api/auth/register/` (`full_name`, `email`, `password`, `date_of_birth`, `blood_type`, `phone`) | Register as a donor and sign in; returns `access` and `refresh` tokens (US-01). 400 for invalid input, 409 if the email is taken | Anyone |
| POST | `/api/auth/token/` (`email`, `password`) | Sign in, returns `access` and `refresh` tokens | Anyone |
| POST | `/api/auth/token/refresh/` (`refresh`) | Get a new access token | Anyone |
| GET / PATCH | `/api/donors/me/contact/` (`email` and/or `phone` for PATCH) | View or update own contact information (US-03) | Signed-in active donor |
| GET / PATCH | `/api/donors/<donor_id>/contact/` | Same operation by donor profile ID; any other ID returns 403 | Owning active donor only |
| GET | `/api/donors/?name=&email=&blood_type=` | Search donor records (US-08) | Coordinator |
| GET / PATCH / DELETE | `/api/donors/<donor_id>/` | View/edit donor records (US-08); delete with `confirm: true`, retaining history (US-10) | Coordinator |
| POST | `/api/donors/` (`full_name`, `email`, `password`, `date_of_birth`, `blood_type`, `phone`) | Create a donor account and profile for a walk-in donor (US-08); returns the profile, not login tokens | Coordinator |
| POST | `/api/donors/me/withdraw/` (`confirm: true`) | Withdraw own registration: set donor status to `withdrawn`, deactivate sign-in, and keep donation history (US-05). 400 if confirmation is missing | Signed-in active donor |
| POST | `/api/donors/<donor_id>/withdraw/` (`confirm: true`) | Same withdrawal by donor profile ID; any other ID returns 403 | Owning active donor only |
| POST | `/api/donors/<donor_id>/donations/` (`donation_type`, `donation_date`, `blood_type`, `volume_ml`) | Record a donation entry (US-09); returns the entry with recalculated history and eligibility. 400 if invalid or not yet eligible, 409 if the donor is not active | Coordinator |
| GET | `/api/requests/` | List all blood requests (US-11) | Coordinator |
| POST | `/api/requests/` (`blood_type`, `component`, `quantity`) | Log a new blood request with `pending` status, coordinator and timestamp (US-11) | Coordinator |
| POST | `/api/units/` (`unit_code`, `blood_type`, `component`, `collected_at`) | Record a blood unit; expiry is calculated from the component's shelf life (US-07). 400 for invalid input or a future collection time, 409 for a duplicate unit ID | Coordinator |
| GET | `/api/units/?blood_type=&component=&status=` | View inventory, earliest expiry first; `status=available` excludes expired units (US-07) | Coordinator |
| GET | `/api/units/<unit_id>/` | View one unit, including discard details and `can_discard` (false once discarded) | Coordinator |
| POST | `/api/units/<unit_id>/discard/` (`reason`, `confirm`) | Discard a unit with reason `expired`, `damaged`, `failed_testing` or `other` (US-17). 400 if the reason is missing, or not `expired` for an expired unit; 409 if already discarded; 409 with `confirm_required` and the request ID if the unit is reserved, until sent again with `confirm: true`. Releases the reservation and sets the request to partially fulfilled (or pending if none left) | Coordinator |
| GET | `/api/requests/<request_id>/matches/` | Match available, unexpired units for one request. Red blood cells use ABO/Rh rules (US-13); plasma uses reversed ABO and ignores Rh (US-14). An empty match returns `No compatible units available` | Coordinator |
| GET | `/api/requests/<request_id>/donor-suggestions/` | List active donors whose blood type is compatible under the component's rules and who are eligible today for the matching donation type (red cells: whole blood, plasma: plasma, platelets: platelets). Shows name, blood type, last donation date, email and phone, identical type first. Empty list returns `No eligible donors found.`; 409 for a fulfilled or cancelled request (US-18) | Coordinator |
| POST | `/api/requests/<request_id>/cancel/` (`confirm: true`) | Cancel a pending or partially fulfilled request and release its reserved units (US-19); expired units remain expired | Coordinator |
| GET | `/api/requests/<request_id>/history/` | View a request's event history, including cancellation time and coordinator (US-19) | Coordinator |
| POST | `/api/requests/<id>/reserve/` (`unit_ids`) | Reserve selected compatible units in one transaction; request becomes `partially_fulfilled` or `fulfilled` (US-16). 400 if too many or incompatible units, 409 if a unit is no longer available or the request is closed, 404 if not found | Coordinator |

Protected endpoints require `Authorization: Bearer <access token>`.
Without it they return 401. A signed-in donor calling a coordinator-only endpoint gets 403.

US-03 returns 400 for invalid contact input, 403 for non-owner/coordinator access,
404 when the signed-in donor has no profile, and 409 for an email already in use.
The email is the account's sign-in email; changing it changes the email used for future sign-ins.
Only email and phone can be updated. See [US-03 implementation and demo](docs/US-03.md)
for the API contract, acceptance tests, dependency on US-01, and frontend handoff.

## US-10: coordinator deletion

- `DELETE /api/donors/<donor_id>/donations/<donation_id>/`: remove one donation and
  return recalculated eligibility and history.
- `DELETE /api/donors/<donor_id>/`: mark a donor deleted and disable sign-in,
  retaining linked donation history.
- Both require a coordinator token and JSON `{"confirm": true}`. See
  [US-10 API, tests and demo](docs/US-10.md) for errors and integration requirements.
- US-08 search uses active donor filters and is tested with deletion. Matching
  and React UI still need integration before the full story is Done.


US-08 donor search, walk-in registration, profile updates, and coordinator-only
record access are covered by `donors/test_records.py`.

US-05 withdraws the signed-in donor's own registration. The donor row stays, with
status `withdrawn` and `User.is_active` set to false, so the same email and password
can no longer sign in. Donation rows are not removed. Coordinator search already
returns only `active` donors, so a withdrawn donor is left out of those results.
A coordinator can still open that donor's record and donation history by id.
See [US-05 implementation and demo](docs/US-05.md). Missing confirmation is 400.
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
