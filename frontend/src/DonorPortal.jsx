import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "./api/client";
import { Form, Badge, Header, Notice, ResourceState, Table } from "./ui";
import { date, title, useResource } from "./viewHelpers";
import { WithdrawRegistration } from "./InventoryActions";
import "./donor.css";

const recordCode = (id) => `DN-${String(id).padStart(4, "0")}`;

function Identity({ profile }) {
  return <div className="donor-identity">
    <strong>{profile.full_name}</strong>
    <span className="blood-type">{profile.blood_type}</span>
    <span className="muted">Your account only</span>
  </div>;
}

function DonationRecords({ records }) {
  if (!records.length) return <div className="donor-empty">
    <h3>No donations recorded yet</h3>
    <p>Your donation history will appear here when the blood bank records your first donation.</p>
  </div>;
  return <>
    <div className="donor-desktop-table">
      <Table rows={records} rowKey={d => d.donation_id} columns={[
        ["Entry", d => recordCode(d.donation_id)],
        ["Date", d => date(d.donation_date)],
        ["Donation type", d => title(d.donation_type)],
        ["Blood type", d => d.blood_type],
        ["Volume", d => `${d.volume_ml} mL`],
        ["Recorded by", d => d.recorded_by || "Blood bank coordinator"],
      ]} />
    </div>
    <ul className="donor-record-cards">
      {records.map(d => <li key={d.donation_id}>
        <div className="donor-record-heading"><strong>{date(d.donation_date)}</strong><span>{recordCode(d.donation_id)}</span></div>
        <p>{title(d.donation_type)} · {d.blood_type} · {d.volume_ml} mL</p>
        <span className="muted">Recorded by {d.recorded_by || "Blood bank coordinator"}</span>
      </li>)}
    </ul>
  </>;
}

function Eligibility({ rows }) {
  return <>
    <div className="donor-desktop-table">
      <Table rows={rows} rowKey={r => r.donation_type} columns={[
        ["Donation type", r => r.label],
        ["Last donation", r => r.last_donation_date ? date(r.last_donation_date) : "No previous donation"],
        ["Next eligible date", r => r.eligible ? "Eligible today" : date(r.next_eligible_date)],
        ["Status", r => <Badge value={r.eligible ? "eligible" : "not_yet_eligible"} />],
      ]} />
    </div>
    <ul className="donor-eligibility-cards">
      {rows.map(r => <li key={r.donation_type}>
        <div className="donor-record-heading"><strong>{r.label}</strong><Badge value={r.eligible ? "eligible" : "not_yet_eligible"} /></div>
        <p>{r.eligible ? "Eligible today under interval rules" : `Next eligible: ${date(r.next_eligible_date)}`}</p>
        <span className="muted">Last donation: {r.last_donation_date ? date(r.last_donation_date) : "No previous donation"}</span>
      </li>)}
    </ul>
  </>;
}

export function DonorOverview() {
  const profile = useResource("/api/donors/me/profile/");
  const resource = useResource("/api/donors/me/eligibility/");
  const data = resource.data;
  return <div className="donor-page">
    <Header title="Your donation overview">Review your eligibility and recent donation activity.</Header>
    <ResourceState resource={profile} />
    {profile.data && <Identity profile={profile.data} />}
    <ResourceState resource={resource} />
    {data && <>
      {data.no_donation_history && <section className="donor-welcome">
        <h2>Welcome{profile.data?.full_name ? `, ${profile.data.full_name}` : " to BloodLink"}</h2>
        <p>Your account is ready. Review your contact details and check the donation intervals below.</p>
        <Link to="/me/contact">Review contact information</Link>
      </section>}
      <div className="stats donor-stats">
        <div><span>Recorded donations</span><strong>{data.donations.length}</strong></div>
        <div><span>Types with a waiting period</span><strong>{data.eligibility.filter(r => !r.eligible).length}</strong></div>
        <div><span>Eligibility checked</span><strong className="donor-summary-date">{date(data.as_of)}</strong></div>
      </div>
      <section className="panel">
        <div className="panel-title"><h2>Eligibility by donation type</h2><button className="text-button" onClick={resource.reload}>Refresh eligibility</button></div>
        <Eligibility rows={data.eligibility} />
        <div className="donor-panel-note">Eligibility is based on the configured interval for each donation type. The blood bank confirms donation suitability.</div>
      </section>
      <section className="panel">
        <div className="panel-title"><h2>Recent donations</h2><Link to="/me/history">View all history</Link></div>
        <DonationRecords records={data.donations.slice(0, 3)} />
      </section>
      <div className="donor-quick-links"><Link to="/me/history">View donation history</Link><Link to="/me/contact">Update contact information</Link></div>
    </>}
  </div>;
}

export function DonorHistory() {
  const resource = useResource("/api/donors/me/eligibility/");
  const [filter, setFilter] = useState("");
  const data = resource.data;
  const records = data?.donations.filter(d => !filter || d.donation_type === filter) ?? [];
  return <div className="donor-page">
    <Header title="Donation history">Review the donation entries recorded for your account.</Header>
    <ResourceState resource={resource} />
    {data && <>
      <div className="donor-history-tools">
        <p>{data.donations.length} donation {data.donations.length === 1 ? "entry" : "entries"} · Most recent first</p>
        <label className="field"><span>Donation type</span><select value={filter} onChange={e => setFilter(e.target.value)}>
          <option value="">All donation types</option>
          {data.eligibility.map(r => <option key={r.donation_type} value={r.donation_type}>{r.label}</option>)}
        </select></label>
        <button className="secondary" onClick={resource.reload}>Refresh history</button>
      </div>
      <section className="panel" aria-label="Donation records">
        {filter && !records.length ? <div className="donor-empty"><h2>No matching donations</h2><p>No records for this donation type.</p><button className="secondary" onClick={() => setFilter("")}>Show all donations</button></div> : <DonationRecords records={records} />}
      </section>
      <section className="donor-guidance"><h2>Need to correct an entry?</h2><p>Contact the blood bank coordinator. Donors cannot edit or delete donation records.</p><Link to="/me">View eligibility</Link></section>
    </>}
  </div>;
}

function ContactField({ name, label, value, error, hint, onChange, required, type, maxLength, ...props }) {
  return <div className="field">
    <label htmlFor={`contact-${name}`}>{label}</label>
    <input type={type === "email" ? "text" : type} inputMode={type === "email" ? "email" : props.inputMode} aria-required={required} title={hint} data-max-length={maxLength} id={`contact-${name}`} name={name} value={value} onChange={e => onChange(name, e.target.value)} aria-invalid={!!error} aria-describedby={`contact-${name}-hint${error ? ` contact-${name}-error` : ""}`} {...props} />
    <span className="field-hint" id={`contact-${name}-hint`}>{hint}</span>
    {error && <span className="field-error" id={`contact-${name}-error`}>{error}</span>}
  </div>;
}

function ContactForm({ profile, onContactSaved }) {
  const initial = {email: profile.email, phone: profile.phone};
  const [saved, setSaved] = useState(initial);
  const [draft, setDraft] = useState(initial);
  const [errors, setErrors] = useState({});
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const dirty = draft.email !== saved.email || draft.phone !== saved.phone;
  function change(name, value) {
    setDraft(d => ({...d, [name]: value}));
    setErrors(e => ({...e, [name]: ""}));
    setError(""); setMessage("");
  }
  function focusError(fields) {
    const name = ["email", "phone"].find(k => fields[k]);
    if (name) document.getElementById(`contact-${name}`)?.focus();
  }
  async function submit(event) {
    event.preventDefault();
    if (busy || !dirty) return;
    setError(""); setMessage("");
    const body = { email: draft.email.trim(), phone: draft.phone };
    const invalid = {};
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(body.email)) invalid.email = "Enter an email such as name@example.com.";
    else if (body.email.length > 254) invalid.email = "Use no more than 254 characters.";
    if (!/^[0-9]{10}$/.test(body.phone)) invalid.phone = "Enter exactly 10 digits.";
    setErrors(invalid);
    if (Object.keys(invalid).length) {
      setError("Changes were not saved. Check the highlighted fields.");
      focusError(invalid); return;
    }
    setBusy(true);
    try {
      const result = await api("/api/donors/me/contact/", {method: "PATCH", body});
      const updated = {email: result.email, phone: result.phone};
      setSaved(updated); setDraft(updated);
      onContactSaved(result.email);
      setMessage("Contact information saved. Your registration remains active.");
    } catch (err) {
      const fields = {};
      for (const name of ["email", "phone"]) {
        const detail = err.data?.[name];
        if (detail) fields[name] = Array.isArray(detail) ? detail.join(" ") : String(detail);
      }
      setErrors(fields);
      setError(Object.keys(fields).length ? "Changes were not saved. Check the highlighted fields." : err.message);
      focusError(fields);
    } finally { setBusy(false); }
  }
  return <Form noValidate onSubmit={submit}>
    <Notice error>{error}</Notice><Notice>{message}</Notice>
    <fieldset disabled={busy} className="form-grid">
      <div className="two-columns">
        <ContactField name="email" label="Email address" value={draft.email} error={errors.email} hint="Changing this also changes your sign-in email." type="email" autoComplete="email" required maxLength={254} onChange={change} />
        <ContactField name="phone" label="Phone number" value={draft.phone} error={errors.phone} hint="Exactly 10 digits, with no spaces or punctuation." type="tel" autoComplete="tel" inputMode="numeric" required onChange={change} />
      </div>
      <div className="donor-form-actions">
        <button type="submit" disabled={!dirty || busy}>{busy ? "Saving…" : "Save changes"}</button>
        <button type="button" className="secondary" disabled={!dirty || busy} onClick={() => {setDraft(saved);setErrors({});setError("");setMessage("");}}>Cancel changes</button>
        {dirty && <span className="muted">Unsaved changes</span>}
      </div>
    </fieldset>
  </Form>;
}

export function DonorContact({ onContactSaved, onWithdrawn }) {
  const [contactEmail, setContactEmail] = useState(null);
  const resource = useResource("/api/donors/me/profile/");
  return <div className="donor-page">
    <Header title="Contact information">Keep your details current so the blood bank can reach you.</Header>
    <ResourceState resource={resource} />
    {resource.data && <>
      <section className="panel donor-contact-panel">
        <h2>Your profile</h2>
        <dl className="donor-profile-grid">
          <div><dt>Name</dt><dd>{resource.data.full_name}</dd><span>Managed by the blood bank.</span></div>
          <div><dt>Blood type</dt><dd className="blood-type">{resource.data.blood_type}</dd><span>Managed by the blood bank.</span></div>
        </dl>
        <ContactForm profile={resource.data} onContactSaved={(email) => { setContactEmail(email); onContactSaved(email); }} />
      </section>
      <div className="donor-registration"><WithdrawRegistration email={contactEmail ?? resource.data.email} onWithdrawn={onWithdrawn} /></div>
    </>}
  </div>;
}
