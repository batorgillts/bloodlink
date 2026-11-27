import { useId, useRef, useState } from "react";
import { api } from "./api/client";
import { isoToUS } from "./formValidation";
import { birthDateToISO } from "./registration";
import { Badge, Field, Form, Header, Modal, Notice, ResourceState } from "./ui";
import { date, title, useResource } from "./viewHelpers";
import "./appointments.css";

const APPOINTMENTS_URL = "/api/donors/me/appointments/";
const appointmentWhen = (appointment) =>
  `${date(appointment.appointment_date)} at ${appointment.appointment_time.slice(0, 5)}`;
const cancellationMessages = {
  donor: "Cancelled by you.",
  coordinator: "Cancelled by the blood bank coordinator.",
  expired: "Cancelled after the appointment time.",
  account_inactive: "Cancelled because the donor account is inactive.",
};
const isActiveAppointment = (appointment) => appointment.status === "in_progress"
  || appointment.status === "scheduled";

export function AppointmentForm({ appointment = null, onClose, onSaved }) {
  const eligibility = useResource("/api/donors/me/eligibility/");
  const [donationType, setDonationType] = useState(appointment?.donation_type || "");
  const [appointmentDate, setAppointmentDate] = useState(isoToUS(appointment?.appointment_date));
  const [appointmentTime, setAppointmentTime] = useState(appointment?.appointment_time.slice(0, 5) || "");
  const [errors, setErrors] = useState({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const formId = useId();
  const rows = eligibility.data?.eligibility || [];
  const selected = rows.find(row => row.donation_type === donationType);
  const earliest = selected
    ? [eligibility.data.as_of, selected.next_eligible_date].sort().at(-1)
    : null;
  const available = !!selected && !eligibility.loading && !eligibility.error;

  function change(name, value, update) {
    update(value);
    setErrors(current => ({ ...current, [name]: "", ...(name === "donation_type" ? { appointment_date: "" } : {}) }));
    setError("");
  }

  async function submit(event) {
    event.preventDefault();
    if (submitting.current || !available) return;
    const invalid = {};
    const day = birthDateToISO(appointmentDate);
    const clock = appointmentTime.trim();
    if (!day) invalid.appointment_date = "Enter a valid date in MM/DD/YYYY format.";
    else if (day < earliest) {
      invalid.appointment_date = `Choose ${date(earliest)} or later for ${selected.label}.`;
    }
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(clock)) {
      invalid.appointment_time = "Enter a valid time in HH:mm format (24-hour time).";
    }
    setErrors(invalid);
    setError("");
    if (Object.keys(invalid).length) {
      event.currentTarget.elements.namedItem(Object.keys(invalid)[0])?.focus();
      return;
    }
    submitting.current = true;
    setBusy(true);
    try {
      const saved = await api(appointment ? `${APPOINTMENTS_URL}${appointment.id}/` : APPOINTMENTS_URL, {
        method: appointment ? "PATCH" : "POST",
        body: { donation_type: donationType, appointment_date: day, appointment_time: clock },
      });
      onSaved(saved);
    } catch (err) {
      const fields = {};
      for (const name of ["donation_type", "appointment_date", "appointment_time"]) {
        if (err.data?.[name]) {
          fields[name] = Array.isArray(err.data[name]) ? err.data[name].join(" ") : String(err.data[name]);
        }
      }
      setErrors(fields);
      setError(err.message);
      if (err.status === 400) eligibility.reload();
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }

  return <Modal title={appointment ? "Edit appointment" : "Book a donation"} onClose={onClose} busy={busy}>
    <p className="muted">Choose your donation type, date and time.</p>
    <ResourceState resource={eligibility} />
    <Notice error>{error}</Notice>
    {eligibility.data && !rows.length && <Notice error>No donation types are available for booking. Please contact the blood bank.</Notice>}
    <Form onSubmit={submit}>
      <fieldset className="form-grid" disabled={busy || eligibility.loading || !!eligibility.error || !rows.length}>
        <div>
          <Field label="Donation type" name="donation_type" required value={donationType}
            options={[["", "Choose a donation type"], ...rows.map(row => [row.donation_type, row.label])]}
            onChange={event => change("donation_type", event.target.value, setDonationType)}
            aria-invalid={!!errors.donation_type}
            aria-describedby={errors.donation_type ? `${formId}-type-error` : undefined} />
          {errors.donation_type && <p className="field-error" id={`${formId}-type-error`}>{errors.donation_type}</p>}
        </div>
        {selected && <div className="appointment-eligibility" role="status">
          <span>Earliest eligible date</span>
          <strong>{date(earliest)}</strong>
          <small>Based on your recorded donations. Existing appointments are checked when you save.</small>
        </div>}
        <div className="appointment-date-time">
          <div>
            <Field label="Appointment date" name="appointment_date" type="date" required
              value={appointmentDate} onChange={event => change("appointment_date", event.target.value, setAppointmentDate)}
              aria-invalid={!!errors.appointment_date}
              aria-describedby={errors.appointment_date ? `${formId}-date-error` : undefined} />
            {errors.appointment_date && <p className="field-error" id={`${formId}-date-error`}>{errors.appointment_date}</p>}
          </div>
          <div>
            <Field label="Appointment time" name="appointment_time" required placeholder="HH:mm" maxLength={5}
              value={appointmentTime} onChange={event => change("appointment_time", event.target.value, setAppointmentTime)}
              aria-invalid={!!errors.appointment_time}
              aria-describedby={`${formId}-time-hint${errors.appointment_time ? ` ${formId}-time-error` : ""}`} />
            <p className="field-hint" id={`${formId}-time-hint`}>24-hour time, for example 14:30.</p>
            {errors.appointment_time && <p className="field-error" id={`${formId}-time-error`}>{errors.appointment_time}</p>}
          </div>
        </div>
        <p className="appointment-form-note">Booking an appointment does not add a donation record or change your current eligibility.</p>
        <div className="appointment-form-actions">
          <button type="button" className="secondary" onClick={onClose} disabled={busy}>Go back</button>
          <button type="submit" disabled={busy || !available}>{busy ? "Saving…" : appointment ? "Save changes" : "Book appointment"}</button>
        </div>
      </fieldset>
    </Form>
  </Modal>;
}

function CancelAppointment({ appointment, onClose, onCancelled }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submitting = useRef(false);
  async function cancel() {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    try {
      const result = await api(`${APPOINTMENTS_URL}${appointment.id}/cancel/`, {
        method: "POST", body: { confirm: true },
      });
      onCancelled(result);
    } catch (err) {
      setError(err.message);
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  return <Modal title="Cancel appointment?" onClose={onClose} busy={busy}>
    <p>Cancel your {appointment.donation_type_label || title(appointment.donation_type)} appointment on {appointmentWhen(appointment)}?</p>
    <Notice error>{error}</Notice>
    <div className="appointment-form-actions">
      <button className="secondary" disabled={busy} onClick={onClose}>Keep appointment</button>
      <button className="danger secondary" disabled={busy} onClick={cancel}>{busy ? "Cancelling…" : "Cancel appointment"}</button>
    </div>
  </Modal>;
}

function AppointmentList({ appointments, onEdit, onCancel }) {
  return <ul className="appointment-list">
    {appointments.map(appointment => <li key={appointment.id} className="appointment-card">
      <div className="appointment-summary">
        <h3>{appointmentWhen(appointment)}</h3>
        <p>{appointment.donation_type_label || title(appointment.donation_type)}</p>
        <span className="muted">Appointment #{appointment.id}</span>
        {appointment.status === "in_progress" && <p className="muted appointment-state-note">The blood bank has started recording this appointment.</p>}
        {appointment.status === "scheduled" && !appointment.can_modify && <p className="muted appointment-state-note">Awaiting coordinator review.</p>}
        {appointment.status === "cancelled" && cancellationMessages[appointment.cancellation_reason] && (
          <p className="muted appointment-state-note">{cancellationMessages[appointment.cancellation_reason]}</p>
        )}
      </div>
      <div className="appointment-controls">
        <Badge value={appointment.status} />
        {appointment.status === "scheduled" && appointment.can_modify && <div className="appointment-row-actions">
          <button className="secondary" aria-label={`Edit appointment ${appointment.id}`} onClick={() => onEdit(appointment)}>Edit</button>
          <button className="danger secondary" aria-label={`Cancel appointment ${appointment.id}`} onClick={() => onCancel(appointment)}>Cancel</button>
        </div>}
      </div>
    </li>)}
  </ul>;
}

export function DonorAppointments() {
  const resource = useResource(APPOINTMENTS_URL, { refreshInterval: 10000 });
  const [editor, setEditor] = useState(null);
  const [cancelling, setCancelling] = useState(null);
  const [message, setMessage] = useState("");
  const appointments = resource.data || [];
  const upcoming = appointments.filter(isActiveAppointment)
    .sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at));
  const previous = appointments.filter(appointment => !isActiveAppointment(appointment))
    .sort((a, b) => b.scheduled_at.localeCompare(a.scheduled_at));

  return <div className="donor-page appointment-page">
    <Header title="Donation appointments" action={<div className="appointment-page-actions">
      <button className="secondary" onClick={resource.reload}>Refresh appointments</button>
      <button onClick={() => setEditor({})}>Book a donation</button>
    </div>}>
      View and manage your appointments.
    </Header>
    <Notice>{message}</Notice>
    <ResourceState resource={resource} />
    {resource.data && <>
      <section className="panel" aria-labelledby="upcoming-appointments-title">
        <div className="panel-title"><h2 id="upcoming-appointments-title">Active appointments</h2><span className="muted">{upcoming.length}</span></div>
        {upcoming.length
          ? <AppointmentList appointments={upcoming} onEdit={appointment => setEditor({ appointment })} onCancel={setCancelling} />
          : <div className="donor-empty"><h3>No active appointments</h3><p>Book a donation when you are ready to choose a date.</p></div>}
      </section>
      <section className="panel" aria-labelledby="previous-appointments-title">
        <div className="panel-title"><h2 id="previous-appointments-title">Appointment history</h2><span className="muted">{previous.length}</span></div>
        {previous.length
          ? <AppointmentList appointments={previous} />
          : <div className="donor-empty"><p>No completed or cancelled appointments.</p></div>}
        <div className="donor-panel-note">Completed donations appear in Donation history. Cancelled appointments do not count as donations.</div>
      </section>
    </>}
    {editor && <AppointmentForm appointment={editor.appointment} onClose={() => setEditor(null)} onSaved={() => {
      setMessage(editor.appointment ? "Appointment updated." : "Appointment booked.");
      setEditor(null);
      resource.reload();
    }} />}
    {cancelling && <CancelAppointment appointment={cancelling} onClose={() => setCancelling(null)} onCancelled={() => {
      setMessage("Appointment cancelled.");
      setCancelling(null);
      resource.reload();
    }} />}
  </div>;
}
