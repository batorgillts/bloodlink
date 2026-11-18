# BloodLink frontend

Setup, the classroom demo, donor pages, and API notes are in the repository
[README](../README.md#frontend).

From the project root:

```powershell
cd frontend
npm ci
npm run dev
```

```bash
cd frontend
npm ci
npm run dev
```

The app listens on http://127.0.0.1:5173 and calls the backend selected by
`VITE_API_URL` (default `http://127.0.0.1:8000`).
