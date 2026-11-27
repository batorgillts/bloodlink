import { useId, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "./api/client";
import { isoToUS } from "./formValidation";
import { birthDateToISO } from "./registration";
import { Badge, Field, Form, Header, Modal, Notice, ResourceState } from "./ui";
import { BLOOD, COMPONENTS, date, title, useResource } from "./viewHelpers";
import "./coordinator-appointments.css";

const APPOINTMENTS_URL = "/api/appointments/";
const CANCELLATION_REASONS = {
  donor: "Cancelled by donor",
  coordinator: "Cancelled by coordinator",
  expired: "Appointment time passed",
  account_inactive: "Donor account deactivated",
};
const appointmentWhen = appointment => `${date(appointment.appointment_date)} at ${appointment.appointment_time.slice(0, 5)}`;

export function RecordAppointmentUnit({ appointment, onClose, onRecorded }) {
  const components = appointment.allowed_components || [];
  const [component, setComponent] = useState(components[0] || "");
  const [collectedDate, setCollectedDate] = useState(isoToUS(appointment.appointment_date));
  const [collectedTime, setCollectedTime] = useState(appointment.appointment_time.slice(0, 5));
  const [errors, setErrors] = useState({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const formId = useId();

  async function submit(event) {
    event.preventDefault();
    if (submitting.current || !components.includes(component)) return;
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form));
    const day = birthDateToISO(collectedDate);
    const clock = collectedTime.trim();
    const invalid = {};
    if (!day) invalid.collected_date = "Enter a valid date in MM/DD/YYYY format.";
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(clock)) invalid.collected_time = "Enter a valid time in HH:mm format (24-hour time).";
    setErrors(invalid);
    setError("");
    if (Object.keys(invalid).length) {
      form.elements.namedItem(Object.keys(invalid)[0])?.focus();
      return;
    }
    submitting.current = true;
    setBusy(true);
    try {
      const saved = await api(`${APPOINTMENTS_URL}${appointment.id}/record/`, {
        method: "POST",
        body: {
          unit_code: values.unit_code.trim(), volume_ml: Number(values.volume_ml), component,
          collected_date: day, collected_time: clock,
        },
      });
      onRecorded(saved);
    } catch (err) {
      setError(err.message);
      const fields = {};
      for (const name of ["unit_code", "volume_ml", "component", "collected_date", "collected_time"]) {
        if (err.data?.[name]) fields[name] = Array.isArray(err.data[name]) ? err.data[name].join(" ") : String(err.data[name]);
      }
      setErrors(fields);
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }

  function fieldErrors(name) {
    return {
      "aria-invalid": !!errors[name],
      "aria-describedby": errors[name] ? `${formId}-${name}-error` : undefined,
    };
  }
  function errorMessage(name) {
    return errors[name] && <p className="field-error" id={`${formId}-${name}-error`}>{errors[name]}</p>;
  }

  return <Modal title="Record blood unit" onClose={onClose} busy={busy}>
    <p className="muted">Create a new donation and blood unit for appointment #{appointment.id}.</p>
    <dl className="coordinator-booking-donor">
      <div><dt>Donor</dt><dd>{appointment.donor.full_name}</dd></div>
      <div><dt>Email</dt><dd>{appointment.donor.email}</dd></div>
      <div><dt>Donation type</dt><dd>{appointment.donation_type_label || title(appointment.donation_type)}</dd></div>
      <div><dt>Blood type</dt><dd className="blood-type">{appointment.donor.blood_type}</dd></div>
    </dl>
    <Notice error>{error}</Notice>
    {!components.length && <Notice error>No inventory components are configured for this donation type. Contact the blood bank administrator.</Notice>}
    <Form onSubmit={submit} onChange={event => {
      const name = event.target.name;
      setErrors(current => ({ ...current, [name]: "" }));
      setError("");
    }}>
      <fieldset className="form-grid" disabled={busy || !components.length}>
        <div className="coordinator-booking-fields">
          <div><Field label="Donation volume (mL)" name="volume_ml" type="number" min={1} step="1" required {...fieldErrors("volume_ml")} />{errorMessage("volume_ml")}</div>
          <div><Field label="Unique unit code" name="unit_code" required maxLength={32} {...fieldErrors("unit_code")} />{errorMessage("unit_code")}</div>
        </div>
        <div><Field label="Component" name="component" required value={component} onChange={event => setComponent(event.target.value)}
          options={components.map(value => [value, COMPONENTS[value] || title(value)])} {...fieldErrors("component")} />{errorMessage("component")}</div>
        <div className="coordinator-booking-fields">
          <div><Field label="Collection date" name="collected_date" type="date" required value={collectedDate}
            onChange={event => setCollectedDate(event.target.value)} {...fieldErrors("collected_date")} />{errorMessage("collected_date")}</div>
          <div>
            <Field label="Collection time" name="collected_time" required placeholder="HH:mm" maxLength={5} value={collectedTime}
              onChange={event => setCollectedTime(event.target.value)} {...fieldErrors("collected_time")}
              aria-describedby={`${formId}-time-hint${errors.collected_time ? ` ${formId}-collected_time-error` : ""}`} />
            <p className="field-hint" id={`${formId}-time-hint`}>24-hour time, for example 14:30. Use the actual collection time.</p>
            {errorMessage("collected_time")}
          </div>
        </div>
        <p className="coordinator-booking-note">This appointment is in progress. You can close this form and continue recording later. The collection time cannot be in the future.</p>
        <div className="coordinator-booking-actions">
          <button type="button" className="secondary" disabled={busy} onClick={onClose}>Close</button>
          <button type="submit" disabled={busy || !components.includes(component)}>{busy ? "Recording…" : "Record unit"}</button>
        </div>
      </fieldset>
    </Form>
  </Modal>;
}

function CancelCoordinatorAppointment({ appointment, onClose, onCancelled }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submitting = useRef(false);
  async function cancel() {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    try {
      const saved = await api(`${APPOINTMENTS_URL}${appointment.id}/cancel/`, { method: "POST", body: { confirm: true } });
      onCancelled(saved);
    } catch (err) {
      setError(err.message);
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  return <Modal title="Cancel appointment?" onClose={onClose} busy={busy}>
    <p>Cancel {appointment.donor.full_name}'s {appointment.donation_type_label || title(appointment.donation_type)} appointment on {appointmentWhen(appointment)}?</p>
    <Notice error>{error}</Notice>
    <div className="coordinator-booking-actions">
      <button className="secondary" disabled={busy} onClick={onClose}>Keep appointment</button>
      <button className="danger secondary" disabled={busy} onClick={cancel}>{busy ? "Cancelling…" : "Cancel appointment"}</button>
    </div>
  </Modal>;
}

export function CoordinatorAppointments() {
  const [query, setQuery] = useState("");
  const [donationTypes, setDonationTypes] = useState(null);
  const [filters, setFilters] = useState({ search: "", donation_type: "", blood_type: "", status: "" });
  const [recording, setRecording] = useState(null);
  const [cancelling, setCancelling] = useState(null);
  const [startingId, setStartingId] = useState(null);
  const starting = useRef(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const resource = useResource(`${APPOINTMENTS_URL}${query}`, { refreshInterval: 10000 });
  const appointments = resource.data?.appointments || [];

  // Keep the filter options visible while a different result set is loading.
  if (resource.data?.donation_types && resource.data.donation_types !== donationTypes) {
    setDonationTypes(resource.data.donation_types);
  }

  function filterField(name) {
    return { value: filters[name], onChange: event => setFilters(current => ({ ...current, [name]: event.target.value })) };
  }
  function apply(event) {
    event.preventDefault();
    const params = new URLSearchParams(Object.entries(filters).map(([key, value]) => [key, value.trim()]).filter(([, value]) => value));
    const next = params.size ? `?${params}` : "";
    if (next === query) resource.reload();
    else setQuery(next);
  }
  async function start(appointment) {
    if (starting.current) return;
    starting.current = true;
    setStartingId(appointment.id);
    setError("");
    setMessage("");
    try {
      const current = await api(`${APPOINTMENTS_URL}${appointment.id}/start/`, { method: "POST" });
      setRecording(current);
      resource.reload();
    } catch (err) {
      setError(err.message);
      resource.reload();
    } finally {
      starting.current = false;
      setStartingId(null);
    }
  }

  return <div className="coordinator-appointments">
    <Header title="Donation appointments" action={<button className="secondary" onClick={resource.reload}>Refresh appointments</button>}>
      Review donor bookings and record completed donations.
    </Header>
    <Notice>{message}</Notice>
    <Notice error>{error}</Notice>
    <Form className="filters coordinator-booking-filters" onSubmit={apply}>
      <Field label="Search appointments" name="search" type="search" placeholder="Name or email" maxLength={254} {...filterField("search")} />
      <div className="coordinator-booking-filter-row">
        <Field label="Donation type" name="donation_type" options={[["", "All donation types"], ...(donationTypes || []).map(row => [row.donation_type, row.label])]} {...filterField("donation_type")} />
        <Field label="Blood type" name="blood_type" options={[["", "All blood types"], ...BLOOD.map(value => [value, value])]} {...filterField("blood_type")} />
        <Field label="Status" name="status" options={[["", "All statuses"], ...["scheduled", "in_progress", "completed", "cancelled"].map(value => [value, title(value)])]} {...filterField("status")} />
        <button type="submit" className="secondary">Apply filters</button>
      </div>
    </Form>
    <ResourceState resource={resource} />
    {resource.data && <section className="panel" aria-labelledby="coordinator-bookings-title">
      <div className="panel-title"><h2 id="coordinator-bookings-title">Appointments</h2><span className="muted">{appointments.length} {appointments.length === 1 ? "appointment" : "appointments"}</span></div>
      {!appointments.length ? <p className="empty">{query ? "No appointments match these filters." : "No donation appointments yet."}</p> : <ul className="coordinator-booking-list">
        {appointments.map(appointment => <li className="coordinator-booking-card" key={appointment.id}>
          <div className="coordinator-booking-identity">
            <h3><Link to={`/donors/${appointment.donor.id}`}>{appointment.donor.full_name}</Link></h3>
            <p>{appointment.donor.email}</p>
            <span className="muted">Appointment #{appointment.id}</span>
          </div>
          <dl className="coordinator-booking-details">
            <div><dt>Scheduled</dt><dd>{appointmentWhen(appointment)}</dd></div>
            <div><dt>Donation type</dt><dd>{appointment.donation_type_label || title(appointment.donation_type)}</dd></div>
            <div><dt>Blood type</dt><dd className="blood-type">{appointment.donor.blood_type}</dd></div>
          </dl>
          <div className="coordinator-booking-controls">
            <Badge value={appointment.status} />
            <div className="coordinator-booking-row-actions">
              {appointment.can_record && <button className="secondary" disabled={startingId !== null} aria-label={`Record blood unit for appointment ${appointment.id}`} onClick={() => start(appointment)}>{startingId === appointment.id ? "Opening…" : "Record blood unit"}</button>}
              {appointment.can_cancel && <button className="danger secondary" disabled={startingId !== null} aria-label={`Cancel appointment ${appointment.id}`} onClick={() => setCancelling(appointment)}>Cancel</button>}
            </div>
          </div>
          {appointment.unit_code && <p className="coordinator-booking-outcome">Recorded unit: <strong>{appointment.unit_code}</strong>{appointment.donation_id ? ` · Donation #${appointment.donation_id}` : ""}</p>}
          {appointment.cancellation_reason && <p className="coordinator-booking-outcome">{CANCELLATION_REASONS[appointment.cancellation_reason] || title(appointment.cancellation_reason)}</p>}
        </li>)}
      </ul>}
    </section>}
    {recording && <RecordAppointmentUnit appointment={recording} onClose={() => { setRecording(null); resource.reload(); }} onRecorded={saved => {
      setMessage(`Unit ${saved.unit.unit_code} recorded. Appointment completed.`);
      setRecording(null);
      resource.reload();
    }} />}
    {cancelling && <CancelCoordinatorAppointment appointment={cancelling} onClose={() => setCancelling(null)} onCancelled={() => {
      setMessage("Appointment cancelled.");
      setCancelling(null);
      resource.reload();
    }} />}
  </div>;
}
