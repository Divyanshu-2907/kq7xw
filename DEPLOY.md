# Deploying Headroom

Two ways to run the whole app. Docker is for local and for anyone who wants it
on their own machine; Vercel is the hosted deployment.

---

## Run it locally with Docker

```bash
docker compose up --build
```

Then open **http://localhost:8080**.

- `frontend` builds the static bundle and serves it from nginx on port 8080.
- `backend` runs the FastAPI app on an internal port; nginx forwards `/api/*` to
  it, so the browser only ever talks to one origin and needs no CORS grant.
- The frontend waits for the backend's healthcheck before it starts.

Stop with `Ctrl-C`, or `docker compose down` to remove the containers.

To rebuild from scratch (no layer cache): `docker compose build --no-cache`.

---

## Deploy to Vercel

The repository is already configured. Everything below is done by you, in your
own account — I cannot and should not log in on your behalf.

### 1. Push the repository to GitHub

Create a new **public** repository under an anonymous name (the client brief
asks for this), then:

```bash
git remote add origin https://github.com/<your-anonymous-handle>/<repo-name>.git
git branch -M main
git push -u origin main
```

Pushing is enough to make CI run: `.github/workflows/ci.yml` lints and tests the
backend and lints and builds the frontend on every push and pull request.

### 2. Import the project into Vercel

1. Sign in at <https://vercel.com> (GitHub sign-in is simplest, as it gives
   Vercel access to the repo you just pushed).
2. **Add New… → Project**, then **Import** the repository.
3. On the configure screen, **change nothing**. `vercel.json` already sets the
   build command, the output directory, the Python function and the rewrites.
   In particular, leave the Framework Preset as whatever it detects and do not
   set a Root Directory — the config assumes the repository root.
4. Click **Deploy**.

The first build takes a few minutes: it installs the frontend packages, builds
the bundle, and installs pandas for the Python function.

### 3. Environment variables

**None are required.** The app runs correctly with no variables set, because
the frontend calls the API same-origin and the backend defaults are the ones we
want in production.

Set any of these only if you want to change behaviour
(**Project → Settings → Environment Variables**, then redeploy):

| Variable | Default | What it does |
|---|---|---|
| `HEADROOM_DAY_AHEAD_CUTOFF_LOCAL` | `09:20` | Day-ahead gate, Europe/London. `09:50` models the N2EX gate instead of EPEX; `15:30` the half-hourly auction. |
| `HEADROOM_FORECAST_ALIGNMENT` | `hold` | `hold` scores both half-hours of each hourly forecast; `hourly_points` scores only exact hours. |
| `HEADROOM_CORS_ORIGINS` | `http://localhost:5173` | Only matters if something off-origin calls the API. The deployed frontend does not. |
| `VITE_API_BASE` | *(unset → same origin)* | Leave unset on Vercel. Setting it would point the bundle at some other backend. |

### 4. Tell me the URL

Once the deployment is green, send me the URL and I will verify it: every page,
every endpoint, and deep links surviving a hard refresh.

---

## How the Vercel setup fits together

- `api/index.py` puts `backend/` on `sys.path` and re-exports the same
  `app.main:app` that Docker and the tests use, so there is one copy of the
  application, not two.
- `vercel.json` sets `includeFiles: "backend/**"`, which is what ships the
  committed `backend/data/*.csv.gz` snapshot inside the function. The API reads
  that snapshot and never calls Elexon at request time.
- Rewrites send `/api/*` to the function and everything else to `index.html`,
  so a deep link such as `/?tab=replay&day=2026-01-12` survives a refresh.
- The function installs the root `requirements.txt`, which is deliberately
  minimal: FastAPI, pandas and Pydantic, with no test tooling and no `pyarrow`.
  Measured at roughly **130 MB installed**, against Vercel's 250 MB limit.
- There are three requirement files, each with one job: the root one for the
  Vercel function, `backend/requirements.txt` for the Docker image (runtime
  only), and `backend/requirements-dev.txt` for CI and local work.
