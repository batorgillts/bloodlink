# BloodLink

Blood bank inventory and request-matching system. CS-GY 6063 Software Engineering I, Group I2-7.

Backend: Django + Django REST Framework, PostgreSQL in production. Layered design
(request -> rules -> data) as described in the Sprint 2 design document.

## Run it locally

Requires Python 3.12 or newer.

## Team

| Name | Role | GitHub |
|---|---|---|
| Bat-Orgil Tsend-Ochir | Backend: auth, inventory, matching, CI | @batorgillts |
| Chenshuo Li | | |
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

Protected endpoints require `Authorization: Bearer <access token>`.
Without it they return 401. A signed-in donor calling a coordinator-only endpoint gets 403.

## Project layout

| Folder | Component (Sprint 2 C4 diagram) |
|---|---|
| `accounts/` | Authentication & Access: custom User with role, permissions, donor registration |
| `donors/` | Donor & Donation Management: Donor profile (date of birth, blood type, phone, status) |
| `config/` | Settings, URLs, shared exceptions, shared choices (blood types) |

## Team workflow

- Branch from `develop` as `feature/US-XX-short-name`.
- Open a pull request into `develop`. CI must pass and one teammate must approve.
- No direct or force pushes to `develop` or `main`.
- At the end of a sprint, `develop` is merged into `main` and tagged (`sprint-3`).
