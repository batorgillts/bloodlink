// US-12: low-stock alerts, the expiring-soon report and coordinator-set thresholds.
import { useState } from "react";
import { api } from "./api/client";
import { BloodFields, Field, Form, Header, Modal, Notice, ResourceState, Table } from "./ui";
import { COMPONENTS, time, useResource } from "./viewHelpers";

const label = (row) => `${row.blood_type} ${COMPONENTS[row.component] ?? row.component}`;

export function StockAlerts() {
  const resource = useResource("/api/inventory/dashboard/");
  const [settings, setSettings] = useState(false);
  // Older test mocks answer every request with a list; only an object is a dashboard.
  const data = resource.data && !Array.isArray(resource.data) ? resource.data : null;
  const stockRows = data?.stock?.filter((row) => row.available > 0 || row.minimum_units) ?? [];

  return (
    <>
      <Header title="Inventory alerts" action={
        <div className="actions">
          <button className="secondary" onClick={() => setSettings(true)}>Alert settings</button>
          <button className="text-button" onClick={resource.reload}>Refresh alerts</button>
        </div>
      }>
        Monitor low stock and upcoming expiries. Reserved, discarded and expired units are not counted.
      </Header>
      <section className="panel" aria-label="Inventory stock and expiry alerts">
        <ResourceState resource={resource} />
        {data && (
          <div className="stock-alerts">
            <div>
              <h2>Low-stock alerts</h2>
              {data.low_stock.length ? (
                <ul className="alert-list">
                  {data.low_stock.map((row) => (
                    <li key={`${row.blood_type}-${row.component}`} className="notice error">
                      <strong>Low stock: {label(row)}</strong> · {row.available} available, alert below {row.minimum_units}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted">No low-stock alerts. Set thresholds under Alert settings.</p>
              )}
            </div>
            <div>
              <h2>Expiring soon</h2>
              {data.expiring_soon.map((group) => (
                <div key={group.component} className="expiry-group">
                  <h3>{group.label} <span className="muted">(within {group.window_days} days by default)</span></h3>
                  {group.overrides?.length > 0 && (
                    <p className="muted window-overrides">
                      Own window: {group.overrides.map((o) => `${o.blood_type} ${o.window_days} days`).join(", ")}
                    </p>
                  )}
                  <Table
                    rows={group.units}
                    empty={`No ${group.label.toLowerCase()} expiring soon.`}
                    columns={[
                      ["Unit", (u) => <strong>{u.unit_code}</strong>],
                      ["Blood type", (u) => <span className="blood-type">{u.blood_type}</span>],
                      ["Expires", (u) => time(u.expires_at)],
                      ["Window", (u) => (u.window_days === group.window_days
                        ? `${u.window_days} days`
                        : `${u.window_days} days (${u.blood_type} setting)`)],
                    ]}
                  />
                </div>
              ))}
            </div>
            <div>
              <h2>Stock by blood type</h2>
              <Table
                rows={stockRows}
                rowKey={(row) => `${row.blood_type}-${row.component}`}
                empty="No usable units and no thresholds yet."
                columns={[
                  ["Blood type", (r) => <span className="blood-type">{r.blood_type}</span>],
                  ["Component", (r) => COMPONENTS[r.component]],
                  ["Available", (r) => r.available],
                  ["Alert below", (r) => r.minimum_units ?? "Not set"],
                  ["Status", (r) => (r.is_low ? <span className="badge expired">Low stock</span> : <span className="badge available">OK</span>)],
                  ["Closest to expiry", (r) => r.closest_to_expiry
                    ? `${r.closest_to_expiry.unit_code} · ${time(r.closest_to_expiry.expires_at)}`
                    : "—"],
                ]}
              />
            </div>
          </div>
        )}
      </section>
      {settings && (
        <ThresholdSettings
          onClose={() => setSettings(false)}
          onSaved={resource.reload}
        />
      )}
    </>
  );
}

export function ThresholdSettings({ onClose, onSaved }) {
  const thresholds = useResource("/api/inventory/thresholds/");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const window = form.get("expiring_soon_days").trim();
    setBusy(true); setError(""); setMessage("");
    try {
      const saved = await api("/api/inventory/thresholds/", {
        method: "PUT",
        body: {
          blood_type: form.get("blood_type"),
          component: form.get("component"),
          minimum_units: form.get("minimum_units").trim(),
          expiring_soon_days: window ? window : null,
        },
      });
      setMessage(`Saved: alert when ${label(saved)} drops below ${saved.minimum_units} units.`);
      thresholds.reload();
      onSaved?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Alert settings" onClose={onClose} busy={busy}>
      <p>Set a low-stock threshold for a blood type and component. Leave the window empty to use the component’s default, which follows its shelf life.</p>
      <Notice error>{error}</Notice>
      <Notice>{message}</Notice>
      <Form onSubmit={save}>
        <BloodFields />
        <Field label="Alert when available units drop below" name="minimum_units" type="number" min={1} step="1" required />
        <Field label="Expiring-soon window in days (optional)" name="expiring_soon_days" type="number" min={1} step="1" />
        <div className="actions">
          <button type="button" className="secondary" onClick={onClose} disabled={busy}>Close</button>
          <button type="submit" disabled={busy}>Save threshold</button>
        </div>
      </Form>
      <h3>Current thresholds</h3>
      <ResourceState resource={thresholds} />
      {Array.isArray(thresholds.data) && (
        <Table
          rows={thresholds.data}
          empty="No thresholds set yet."
          columns={[
            ["Blood type", (t) => <span className="blood-type">{t.blood_type}</span>],
            ["Component", (t) => COMPONENTS[t.component]],
            ["Alert below", (t) => t.minimum_units],
            ["Window", (t) => (t.expiring_soon_days ? `${t.expiring_soon_days} days` : "Component default")],
          ]}
        />
      )}
    </Modal>
  );
}
