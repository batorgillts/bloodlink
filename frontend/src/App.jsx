import { useEffect, useState } from "react";
import {
  BrowserRouter,
  Link,
  NavLink,
  Navigate,
  Route,
  Routes,
  useNavigate,
  useParams,
} from "react-router-dom";
import { api, clearSession, readSession, saveSession } from "./api/client";
import { birthDateToISO } from "./registration";
import { EditBloodUnit, RecordBloodUnit } from "./RecordBloodUnit";
import "./app.css";

import { Form, Notice, Badge, Field, BloodFields, Header, Table, Modal, ResourceState } from "./ui";
import { BLOOD, COMPONENTS, title, date, time, useResource } from "./viewHelpers";
import { DonorRegistry, DonorRecord } from "./DonorManagement";
import { DiscardUnit, RequestExtras } from "./InventoryActions";
import { StockAlerts } from "./StockAlerts";
import { DonorOverview, DonorHistory, DonorContact } from "./DonorPortal";
const home = (user) => (user?.role === "coordinator" ? "/requests" : "/me");

function Auth({ register, onSignIn, expired, withdrawn }) {
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  async function submit(event) {
    event.preventDefault();
    setError("");
    const form = event.currentTarget;
    const body = Object.fromEntries(new FormData(form));
    if (register) {
      const invalid = {};
      if (body.password !== body.password_confirmation) {
        invalid.password_confirmation = "Passwords do not match. Enter the same password again.";
      }
      const isoDate = birthDateToISO(body.date_of_birth);
      if (!isoDate) invalid.date_of_birth = "Enter a valid date in MM/DD/YYYY format.";
      setFieldErrors(invalid);
      if (Object.keys(invalid).length) {
        form.elements.namedItem(Object.keys(invalid)[0])?.focus();
        return;
      }
      body.date_of_birth = isoDate;
      delete body.password_confirmation;
    }
    setBusy(true);
    try {
      const data = await api(
        register ? "/api/auth/register/" : "/api/auth/token/",
        {
          method: "POST",
          body,
          anonymous: true,
        },
      );
      const user = onSignIn(data);
      navigate(home(user), { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="auth-layout">
      <section className="auth-brand">
        <Link to="/login" className="brand">
          <img className="brand-mark" src="/favicon.svg" alt="" aria-hidden="true" /> BloodLink
        </Link>
        <div>
          <h2>Blood bank management</h2>
          <p>Manage donor records, blood inventory and requests in one workspace.</p>
        </div>
        <small>Blood bank inventory & request matching</small>
      </section>
      <section className="auth-content">
        <div className="auth-card">
          <h1>{register ? "Create your account" : "Sign in to BloodLink"}</h1>
          <p className="muted">
            {register
              ? "Keep your information up to date and follow your donation eligibility."
              : "Use your donor or assigned coordinator account."}
          </p>
          <Notice error>
            {error ||
              (!register && expired
                ? "Your session has expired. Please sign in again."
                : "")}
          </Notice>
          {withdrawn && <Notice>Registration withdrawn. Your account is deactivated and donation history has been retained.</Notice>}
          <Form onSubmit={submit}>
            <fieldset disabled={busy} className="form-grid">
              {register && (
                <Field
                  label="Full name"
                  name="full_name"
                  autoComplete="name"
                  required
                  maxLength={200}
                />
              )}
              <Field
                label="Email address"
                name="email"
                type="email"
                autoComplete="email"
                required
              />
              <Field
                label="Password"
                name="password"
                type="password"
                autoComplete={register ? "new-password" : "current-password"}
                required
                minLength={register ? 8 : undefined}
                onChange={() => setFieldErrors(current => ({ ...current, password_confirmation: "" }))}
              />
              {register && (
                <>
                  <p className="hint">At least 8 characters, including a number.</p>
                  <div className="registration-field">
                    <Field
                      label="Confirm password"
                      name="password_confirmation"
                      type="password"
                      autoComplete="new-password"
                      required
                      aria-invalid={!!fieldErrors.password_confirmation}
                      aria-describedby={fieldErrors.password_confirmation ? "confirm-password-error" : undefined}
                      onChange={() => setFieldErrors(current => ({ ...current, password_confirmation: "" }))}
                    />
                    {fieldErrors.password_confirmation && <p id="confirm-password-error" className="registration-error" role="alert">{fieldErrors.password_confirmation}</p>}
                  </div>
                  <div className="two-columns">
                    <div className="registration-field">
                      <Field
                        label="Date of birth"
                        name="date_of_birth"
                        type="text"
                        placeholder="MM/DD/YYYY"
                        maxLength={10}
                        required
                        aria-invalid={!!fieldErrors.date_of_birth}
                        aria-describedby={`birth-date-hint${fieldErrors.date_of_birth ? " birth-date-error" : ""}`}
                        onChange={() => setFieldErrors(current => ({ ...current, date_of_birth: "" }))}
                      />
                      <p id="birth-date-hint" className="registration-hint">Month / Day / Year · Age 17 or older.</p>
                      {fieldErrors.date_of_birth && <p id="birth-date-error" className="registration-error" role="alert">{fieldErrors.date_of_birth}</p>}
                    </div>
                    <Field
                      label="Blood type"
                      name="blood_type"
                      options={BLOOD.map((b) => [b, b])}
                    />
                  </div>
                  <Field
                    label="Phone number"
                    name="phone"
                    type="tel"
                    autoComplete="tel"
                    pattern="[0-9]{10}"
                    title="Exactly 10 digits"
                    required
                  />
                </>
              )}
              <button type="submit">
                {busy
                  ? "Please wait…"
                  : register
                    ? "Create account"
                    : "Sign in"}
              </button>
            </fieldset>
          </Form>
          <p className="auth-switch">
            {register ? "Already have an account? " : "New to BloodLink? "}
            <Link to={register ? "/login" : "/register"}>
              {register ? "Sign in" : "Register as a donor"}
            </Link>
          </p>
          {register && (
            <p className="hint">
              Coordinator accounts are assigned by the blood bank.
            </p>
          )}
        </div>
      </section>
    </main>
  );
}
function Shell({ user, onSignOut, children }) {
  return (
    <div className="app-layout">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <aside className="sidebar">
        <Link className="brand" to={home(user)}>
          <img className="brand-mark" src="/favicon.svg" alt="" aria-hidden="true" />BloodLink
        </Link>
        <nav aria-label="Main navigation">
          {user.role === "coordinator" ? (
            <>
              <NavLink to="/requests">
                ▤ <span>Blood requests</span>
              </NavLink>
              <NavLink to="/donors">♡ <span>Donor registry</span></NavLink>
              <NavLink to="/inventory">
                ▦ <span>Blood inventory</span>
              </NavLink>
            </>
          ) : (
            <>
              <NavLink to="/me" end><span>Overview</span></NavLink>
              <NavLink to="/me/history"><span>Donation history</span></NavLink>
              <NavLink to="/me/contact"><span>Contact information</span></NavLink>
            </>
          )}
        </nav>
        <div className="sidebar-bottom">
          <Badge value={user.role} />
          <p className="account-email">{user.email}</p>
          <button className="secondary" onClick={onSignOut}>
            Sign out
          </button>
        </div>
      </aside>
      <div className="workspace">
        <div className="topbar">
          <span>
            {user.role === "coordinator"
              ? "Coordinator workspace"
              : "Your donor account"}
          </span>
          <span className="muted">BloodLink</span>
        </div>
        <main id="main" className="main-content">
          {children}
        </main>
        <footer>BloodLink · Group 7 · Software Engineering</footer>
      </div>
    </div>
  );
}
function CreateRecord({ onClose, onCreated }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event) {
    event.preventDefault();
    const body = Object.fromEntries(new FormData(event.currentTarget));
    body.quantity = Number(body.quantity);
    setBusy(true); setError("");
    try { onCreated(await api("/api/requests/", {method: "POST", body})); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  return <Modal title="Log blood request" onClose={onClose} busy={busy}>
    <p className="muted">Create a request on behalf of a clinician.</p>
    <Notice error>{error}</Notice>
    <Form onSubmit={submit}><fieldset disabled={busy} className="form-grid">
      <div className="two-columns"><BloodFields /></div>
      <Field label="Quantity (units)" name="quantity" type="number" min="1" step="1" defaultValue="1" required />
      <div className="actions">
        <button className="secondary" type="button" onClick={onClose}>Cancel</button>
        <button type="submit">{busy ? "Saving…" : "Create request"}</button>
      </div>
    </fieldset></Form>
  </Modal>;
}
function Inventory() {
  const [editing, setEditing] = useState(null);
  const [discarding, setDiscarding] = useState(null);
  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false);
  const [message, setMessage] = useState("");
  const [dashboardVersion, setDashboardVersion] = useState(0);
  const resource = useResource(`/api/units/${query}`);
  const changed = () => { resource.reload(); setDashboardVersion((v) => v + 1); };
  return (
    <>
      <Header
        title="Blood inventory"
        action={
          <button onClick={() => setCreating(true)}>+ Record blood unit</button>
        }
      >
        Track available units, components and expiry dates.
      </Header>
      <Notice>{message}</Notice>
      <StockAlerts key={dashboardVersion} />
      <Form
        className="filters inventory-filters"
        onSubmit={(e) => {
          e.preventDefault();
          const values = [...new FormData(e.currentTarget)].filter(
            ([, v]) => v.trim(),
          ).map(([key, value]) => [key, value.trim()]);
          setQuery(`?${new URLSearchParams(values)}`);
        }}
      >
        <Field label="Search inventory" name="search" type="search" maxLength={254}
          placeholder="Unique unit code, donor name or email" />
        <div className="inventory-filter-row">
        <BloodFields filters />
        <Field
          label="Status"
          name="status"
          options={[
            ["", "All statuses"],
            ...["available", "reserved", "expired", "discarded"].map((s) => [
              s,
              title(s),
            ]),
          ]}
        />
        <button type="submit" className="secondary">
          Apply filters
        </button>
        </div>
      </Form>
      <section className="panel">
        <div className="panel-title">
          <h2>Inventory units</h2>
          <button className="text-button" onClick={resource.reload}>
            Refresh
          </button>
        </div>
        <ResourceState resource={resource} />
        {resource.data && (
          <Table
            rows={resource.data}
            empty="No units found. Record a blood unit or change your filters."
            columns={[
              ["Unit", (u) => <strong>{u.unit_code}</strong>],
              ["Source donation", (u) => u.source_donation
                ? <Link to={`/donors/${u.source_donation.donor_id}`}>{u.source_donation.donor_name} · Donation #{u.source_donation.id}</Link>
                : <span className="muted">Source not recorded</span>],
              ["Action", (u) => <div className="actions">
                {u.can_edit && <button className="secondary" onClick={() => setEditing(u)} aria-label={`Edit ${u.unit_code}`}>Edit</button>}
                {u.can_discard ? <button className="danger secondary" onClick={() => setDiscarding(u)}>Discard {u.unit_code}</button> : <span>Discarded: {title(u.discard_reason)}</span>}
              </div>],
              [
                "Blood type",
                (u) => <span className="blood-type">{u.blood_type}</span>,
              ],
              ["Component", (u) => COMPONENTS[u.component]],
              ["Donation type", (u) => u.source_donation ? title(u.source_donation.donation_type) : "Source not recorded"],
              ["Collected", (u) => time(u.collected_at)],
              ["Expires", (u) => time(u.expires_at)],
              [
                "Status",
                (u) => <Badge value={u.effective_status || u.status} />,
              ],
            ]}
          />
        )}
      </section>
      {discarding && <DiscardUnit unit={discarding} onClose={()=>setDiscarding(null)} onDiscarded={()=>{setDiscarding(null);setMessage("Unit discarded. Any affected request has been updated.");changed();}} />}
      {editing && <EditBloodUnit unit={editing} onClose={() => setEditing(null)} onSaved={() => {
        setEditing(null); setMessage("Corrections saved. Source donation, expiry and eligibility have been recalculated."); changed();
      }} />}
      {creating && (
        <RecordBloodUnit
          onClose={() => setCreating(false)}
          onCreated={(unit) => {
            setCreating(false);
            setMessage(
              `Unit ${unit.unit_code} linked to donation #${unit.donation_id}. Expiry: ${time(unit.expires_at)}. It appears when it matches the current filters.`,
            );
            changed();
          }}
        />
      )}
    </>
  );
}
function Requests() {
  const [status, setStatus] = useState("");
  const [creating, setCreating] = useState(false);
  const navigate = useNavigate();
  const resource = useResource(
    `/api/requests/${status ? `?status=${status}` : ""}`,
  );
  return (
    <>
      <Header
        title="Blood requests"
        action={
          <button onClick={() => setCreating(true)}>+ Log blood request</button>
        }
      >
        Log, match and track requests on behalf of clinicians.
      </Header>
      <div className="tabs" aria-label="Filter request status">
        {["", "pending", "partially_fulfilled", "fulfilled", "cancelled"].map(
          (value) => (
            <button
              className={status === value ? "selected" : ""}
              key={value}
              aria-pressed={status === value}
              onClick={() => setStatus(value)}
            >
              {value ? title(value) : "All requests"}
            </button>
          ),
        )}
      </div>
      <section className="panel">
        <div className="panel-title">
          <h2>Recent requests</h2>
          <button className="text-button" onClick={resource.reload}>
            Refresh
          </button>
        </div>
        <ResourceState resource={resource} />
        {resource.data && (
          <Table
            rows={resource.data}
            empty="No requests found. Log a request to begin matching."
            columns={[
              [
                "Request",
                (r) => <Link to={`/requests/${r.id}`}>REQ-{r.id}</Link>,
              ],
              ["Logged", (r) => date(r.logged_at)],
              [
                "Blood type",
                (r) => <span className="blood-type">{r.blood_type}</span>,
              ],
              ["Component", (r) => COMPONENTS[r.component]],
              ["Requested", (r) => r.quantity],
              ["Reserved", (r) => r.reserved_units.length],
              ["Status", (r) => <Badge value={r.status} />],
            ]}
          />
        )}
      </section>
      {creating && (
        <CreateRecord
          onClose={() => setCreating(false)}
          onCreated={(r) => navigate(`/requests/${r.id}`)}
        />
      )}
    </>
  );
}
function RequestDetail() {
  const { id } = useParams();
  const resource = useResource(`/api/requests/${id}/`);
  const [matches, setMatches] = useState(null);
  const [selected, setSelected] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [confirm, setConfirm] = useState(null);
  const request = resource.data;
  const remaining = request
    ? request.quantity - request.reserved_units.length
    : 0;
  async function findMatches() {
    setBusy(true);
    setError("");
    setSelected([]);
    setMatches(null);
    try {
      const result = await api(`/api/requests/${id}/matches/`);
      setMatches(result.units);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  async function perform() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await api(`/api/requests/${id}/${confirm}/`, {
        method: "POST",
        body:
          confirm === "reserve" ? { unit_ids: selected } : { confirm: true },
      });
      setMessage(
        confirm === "reserve"
          ? `Reservation saved. ${result.remaining_quantity} unit(s) still needed.`
          : `Request cancelled. ${result.released_units} unit(s) released.`,
      );
      setConfirm(null);
      setMatches(null);
      setSelected([]);
      resource.reload();
    } catch (err) {
      setError(err.message);
      setConfirm(null);
      setMatches(null);
      setSelected([]);
      resource.reload();
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Link className="back-link" to="/requests">
        ← All blood requests
      </Link>
      <Header title={`Request REQ-${id}`}>
        Review the request and reserve compatible, in-date units.
      </Header>
      <Notice error>{error}</Notice>
      <Notice>{message}</Notice>
      <ResourceState resource={resource} />
      {request && (
        <>
          <div className="stats">
            <div>
              <span>Requested blood</span>
              <strong>{request.blood_type}</strong>
              <small>{COMPONENTS[request.component]}</small>
            </div>
            <div>
              <span>Units requested</span>
              <strong>{request.quantity}</strong>
            </div>
            <div>
              <span>Currently reserved</span>
              <strong>{request.reserved_units.length}</strong>
            </div>
            <div>
              <span>Still needed</span>
              <strong>
                {request.status === "cancelled" ? "—" : remaining}
              </strong>
              <Badge value={request.status} />
            </div>
          </div>
          <section className="panel">
            <div className="panel-title">
              <h2>Reserved units</h2>
              <button
                className="text-button"
                disabled={busy}
                onClick={() => {
                  setMatches(null);
                  setSelected([]);
                  resource.reload();
                }}
              >
                Refresh request
              </button>
            </div>
            <Table
              rows={request.reserved_units}
              rowKey={(u) => u.unit_id}
              empty="No units are currently reserved for this request."
              columns={[
                ["Unit", (u) => u.unit_code],
                ["Blood type", (u) => u.blood_type],
                ["Component", (u) => COMPONENTS[u.component]],
                ["Expires", (u) => time(u.expires_at)],
              ]}
            />
          </section>
          {request.can_cancel && (
            <section className="panel">
              <div className="panel-title">
                <div>
                  <h2>Compatible inventory</h2>
                  <p className="muted">
                    Exact matches first, then compatible substitutes.
                    Availability is checked again when you reserve.
                  </p>
                </div>
                <button disabled={busy} onClick={findMatches}>
                  {busy
                    ? "Please wait…"
                    : matches
                      ? "Refresh matches"
                      : "Find compatible units"}
                </button>
              </div>
              {matches !== null && (
                <>
                  <Table
                    rows={matches}
                    empty="No compatible units available."
                    columns={[
                      [
                        "Select",
                        (u) => (
                          <input
                            type="checkbox"
                            aria-label={`Select ${u.unit_code}`}
                            checked={selected.includes(u.id)}
                            disabled={
                              busy ||
                              (!selected.includes(u.id) &&
                                selected.length >= remaining)
                            }
                            onChange={(e) =>
                              setSelected((values) =>
                                e.target.checked
                                  ? [...values, u.id]
                                  : values.filter((v) => v !== u.id),
                              )
                            }
                          />
                        ),
                      ],
                      ["Unit", (u) => u.unit_code],
                      ["Blood type", (u) => u.blood_type],
                      [
                        "Match",
                        (u) =>
                          u.match_label ||
                          (u.is_identical
                            ? "Identical"
                            : "Compatible substitute"),
                      ],
                      ["Expires", (u) => time(u.expires_at)],
                    ]}
                  />
                  <div className="panel-title">
                    <span>
                      {selected.length} selected · {remaining} still needed
                    </span>
                    <button
                      disabled={!selected.length || busy}
                      onClick={() => setConfirm("reserve")}
                    >
                      Reserve selected units
                    </button>
                  </div>
                </>
              )}
            </section>
          )}
          <RequestExtras request={request} />
          {request.can_cancel && (
            <div className="actions">
              <button
                className="danger secondary"
                disabled={busy}
                onClick={() => setConfirm("cancel")}
              >
                Cancel request
              </button>
            </div>
          )}
        </>
      )}
      {confirm && (
        <Modal
          title={
            confirm === "reserve"
              ? "Confirm unit reservation"
              : `Cancel request REQ-${id}?`
          }
          onClose={() => setConfirm(null)}
          busy={busy}
        >
          <p>
            {confirm === "reserve"
              ? `Reserve ${selected.length} unit(s) for this request? These units will leave available inventory.`
              : "All active reservations will be released. Units past expiry will remain unavailable."}
          </p>
          <div className="actions">
            <button
              className="secondary"
              disabled={busy}
              onClick={() => setConfirm(null)}
            >
              Go back
            </button>
            <button disabled={busy} onClick={perform}>
              {busy ? "Saving…" : "Confirm"}
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
function Application() {
  const [user, setUser] = useState(readSession);
  const [expired, setExpired] = useState(false);
  const [withdrawn, setWithdrawn] = useState(false);
  useEffect(() => {
    const expire = () => {
      setUser(null);
      setExpired(true);
    };
    const sync = () => setUser(readSession());
    window.addEventListener("bloodlink-session-expired", expire);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener("bloodlink-session-expired", expire);
      window.removeEventListener("storage", sync);
    };
  }, []);
  const onSignIn = (data) => {
    const value = saveSession(data);
    setUser(value);
    setExpired(false);
    setWithdrawn(false);
    return value;
  };
  const protect = (role, element) =>
    !user ? (
      <Navigate to="/login" replace />
    ) : user.role !== role ? (
      <section>
        <h1>You do not have access</h1>
        <p>This page is for {role}s.</p>
        <Link to={home(user)}>Go to your workspace</Link>
      </section>
    ) : (
      element
    );
  const routes = (
    <Routes>
      <Route
        path="/login"
        element={
          user ? (
            <Navigate to={home(user)} replace />
          ) : (
            <Auth key="login" onSignIn={onSignIn} expired={expired} withdrawn={withdrawn} />
          )
        }
      />
      <Route
        path="/register"
        element={
          user ? (
            <Navigate to={home(user)} replace />
          ) : (
            <Auth key="register" register onSignIn={onSignIn} />
          )
        }
      />
      <Route
        path="/inventory"
        element={protect("coordinator", <Inventory />)}
      />
      <Route path="/donors" element={protect("coordinator", <DonorRegistry />)} />
      <Route path="/donors/:id" element={protect("coordinator", <DonorRecord />)} />
      <Route path="/requests" element={protect("coordinator", <Requests />)} />
      <Route
        path="/requests/:id"
        element={protect("coordinator", <DetailRoute />)}
      />
      <Route path="/me" element={protect("donor", <DonorOverview />)} />
      <Route path="/me/history" element={protect("donor", <DonorHistory />)} />
      <Route path="/me/contact" element={protect("donor", <DonorContact
        onWithdrawn={() => { clearSession(); setUser(null); setExpired(false); setWithdrawn(true); }}
        onContactSaved={(email) => {
          const value = { ...user, email };
          localStorage.setItem("bloodlink-user", JSON.stringify(value));
          setUser(value);
        }}
      />)} />
      <Route
        path="*"
        element={<Navigate to={user ? home(user) : "/login"} replace />}
      />
    </Routes>
  );
  return user ? (
    <Shell
      user={user}
      onSignOut={() => {
        clearSession();
        setUser(null);
        setExpired(false);
      }}
    >
      {routes}
    </Shell>
  ) : (
    routes
  );
}
function DetailRoute() {
  const { id } = useParams();
  return <RequestDetail key={id} />;
}
export default function App() {
  return (
    <BrowserRouter>
      <Application />
    </BrowserRouter>
  );
}
