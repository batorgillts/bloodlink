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
| Miaomiao Li | | |
| Parvathi Krishnan |US-01(Backend: donor registration and donor records) |@parvathikrishnan11 |
| Shuaiyu Chen | | |

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
| GET / PATCH | `/api/donors/<donor_id>/` | View donor profile, donation history and eligibility; edit profile fields (US-08) | Coordinator |
| POST | `/api/donors/` (`full_name`, `email`, `password`, `date_of_birth`, `blood_type`, `phone`) | Create a donor account and profile for a walk-in donor (US-08); returns the profile, not login tokens | Coordinator |

Protected endpoints require `Authorization: Bearer <access token>`.
Without it they return 401. A signed-in donor calling a coordinator-only endpoint gets 403.

US-03 returns 400 for invalid contact input, 403 for non-owner/coordinator access,
404 when the signed-in donor has no profile, and 409 for an email already in use.
The email is the account's sign-in email; changing it changes the email used for future sign-ins.
Only email and phone can be updated. See [US-03 implementation and demo](docs/US-03.md)
for the API contract, acceptance tests, dependency on US-01, and frontend handoff.

US-08 donor search, walk-in registration, profile updates, and coordinator-only
record access are covered by `donors/test_records.py`.

## Project layout

| Folder | Component (Sprint 2 C4 diagram) |
|---|---|
| `accounts/` | Authentication & Access: custom User with role, permissions, donor registration |
| `donors/` | Donor & Donation Management: profile and own-contact API; services and repository for US-03 |
| `config/` | Settings, URLs, shared exceptions, shared choices (blood types) |

## Team workflow

- Branch from `develop` as `feature/US-XX-short-name`.
- Open a pull request into `develop`. CI must pass and one teammate must approve.
- No direct or force pushes to `develop` or `main`.
- At the end of a sprint, `develop` is merged into `main` and tagged (`sprint-3`).
