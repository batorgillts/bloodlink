import { RecordBloodUnit } from "./RecordBloodUnit";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { birthDateToISO } from "./registration";
import { bankDateInput } from "./formValidation";
import { api } from "./api/client";
import { Form, Badge, Field, Header, Modal, Notice, ResourceState, Table } from "./ui";
import { BLOOD, date, useResource } from "./viewHelpers";

function ProfileFields({ donor = {} }) {
  return <>
    <Field label="Full name" name="full_name" defaultValue={donor.full_name} required maxLength={200} />
    <div className="two-columns">
      <Field label="Date of birth" name="date_of_birth" type="date" defaultValue={donor.date_of_birth} required />
      <Field label="Blood type" name="blood_type" defaultValue={donor.blood_type} options={BLOOD.map(b => [b,b])} required />
    </div>
    <Field label="Email address" name="email" type="email" defaultValue={donor.email} required />
    <Field label="Phone number" name="phone" type="tel" defaultValue={donor.phone} pattern="[0-9]{10}" title="Exactly 10 digits" required />
    {!donor.id && <Field label="Initial password" name="password" type="password" autoComplete="new-password" minLength={8} required />}
  </>;
}

function ProfileForm({ donor, onClose, onSaved }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event) {
    event.preventDefault();
    const body = Object.fromEntries(new FormData(event.currentTarget));
    body.date_of_birth = birthDateToISO(body.date_of_birth);
    setBusy(true); setError("");
    try {
      onSaved(await api(donor ? `/api/donors/${donor.id}/` : "/api/donors/", { method: donor ? "PATCH" : "POST", body }));
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  }
  return <Modal title={donor ? "Edit donor record" : "Register walk-in donor"} onClose={onClose} busy={busy}>
    <Notice error>{error}</Notice>
    <Form onSubmit={submit}><fieldset className="form-grid" disabled={busy}>
      <ProfileFields donor={donor} />
      {!donor && <p className="hint">Use synthetic information. The donor can sign in with this initial password.</p>}
      <button type="submit">{busy ? "Saving…" : "Save donor"}</button>
    </fieldset></Form>
  </Modal>;
}

export function DonorRegistry() {
  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false);
  const resource = useResource(`/api/donors/${query}`);
  const navigate = useNavigate();
  return <>
    <Header title="Donor registry" action={<button onClick={() => setCreating(true)}>+ Register walk-in donor</button>}>Find active donors and manage their records.</Header>
    <Form className="filters" onSubmit={e => {
      e.preventDefault();
      setQuery(`?${new URLSearchParams([...new FormData(e.currentTarget)].filter(([,v]) => v))}`);
    }}>
      <Field label="Name" name="name" />
      <Field label="Email" name="email" />
      <Field label="Blood type" name="blood_type" options={[["", "All blood types"], ...BLOOD.map(b => [b,b])]} />
      <button type="submit">Search donors</button>
    </Form>
    <section className="panel"><ResourceState resource={resource} />
      {resource.data && <Table rows={resource.data} empty="No active donors found." columns={[
        ["Name", d => <Link to={`/donors/${d.id}`}>{d.full_name}</Link>],
        ["Blood type", d => d.blood_type], ["Email", d => d.email], ["Phone", d => d.phone], ["Status", d => <Badge value={d.status} />],
      ]} />}
    </section>
    {creating && <ProfileForm onClose={() => setCreating(false)} onSaved={d => navigate(`/donors/${d.id}`)} />}
  </>;
}

function DonationForm({ donor, onClose, onSaved }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event) {
    event.preventDefault();
    const body = Object.fromEntries(new FormData(event.currentTarget));
    body.donation_date = birthDateToISO(body.donation_date);
    body.volume_ml = Number(body.volume_ml);
    body.blood_type = donor.blood_type;
    setBusy(true); setError("");
    try { await api(`/api/donors/${donor.id}/donations/`, {method:"POST", body}); onSaved(); }
    catch (err) { setError(err.message); } finally { setBusy(false); }
  }
  return <Modal title="Record donation" onClose={onClose} busy={busy}>
    <p>{donor.full_name} · {donor.blood_type}</p>
    <Notice error>{error}</Notice>
    <Form onSubmit={submit}><fieldset disabled={busy} className="form-grid">
      <Field label="Donation type" name="donation_type" options={donor.eligibility.map(e => [e.donation_type, e.label])} required />
      <Field label="Donation date" name="donation_date" type="date" defaultValue={bankDateInput()} required />
      <Field label="Volume (mL)" name="volume_ml" type="number" min="1" step="1" defaultValue="450" required />
      <p className="hint">Eligibility is checked when saved. After processing, use Record unit beside this donation to link its inventory units.</p>
      <button type="submit">{busy ? "Saving…" : "Save donation"}</button>
    </fieldset></Form>
  </Modal>;
}

export function ConfirmAction({ title, children, path, method = "POST", onClose, onDone }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return <Modal title={title} onClose={onClose} busy={busy}>
    <p>{children}</p><Notice error>{error}</Notice>
    <div className="actions">
      <button className="secondary" disabled={busy} onClick={onClose}>Go back</button>
      <button className="danger" disabled={busy} onClick={async () => {
        setBusy(true); setError("");
        try { await api(path, {method, body:{confirm:true}}); onDone(); }
        catch (err) { setError(err.message); } finally { setBusy(false); }
      }}>{busy ? "Saving…" : "Confirm"}</button>
    </div>
  </Modal>;
}

export function DonorRecord() {
  const {id} = useParams();
  return <Record key={id} id={id} />;
}
function Record({ id }) {
  const resource = useResource(`/api/donors/${id}/`);
  const [action, setAction] = useState(null);
  const [message, setMessage] = useState("");
  const donor = resource.data;
  function saved(message) { setAction(null); setMessage(message); resource.reload(); }
  return <>
    <Link to="/donors">← Donor registry</Link>
    <ResourceState resource={resource} /><Notice>{message}</Notice>
    {donor && <>
      <Header title={donor.full_name}><Badge value={donor.status} /> · {donor.blood_type} · Born {date(donor.date_of_birth)}</Header>
      <section className="panel"><h2>Contact information</h2><p>{donor.email} · {donor.phone}</p>
        {donor.status === "active" && <div className="actions">
          <button onClick={() => setAction("donation")}>Record donation</button>
          <button className="secondary" onClick={() => setAction("edit")}>Edit donor record</button>
          <button className="danger secondary" onClick={() => setAction("delete")}>Delete donor record</button>
        </div>}
      </section>
      <section className="panel"><h2>Donation eligibility</h2><Table rows={donor.eligibility} rowKey={e=>e.donation_type} columns={[
        ["Type", e=>e.label], ["Eligibility", e=><Badge value={e.eligible ? "eligible" : "not_yet_eligible"} />], ["Next eligible", e=>date(e.next_eligible_date)],
      ]} /></section>
      <section className="panel"><div className="panel-title"><h2>Donation history</h2><button className="text-button" onClick={resource.reload}>Refresh record</button></div>
        <Table rows={donor.donations} rowKey={d=>d.donation_id} empty="No previous donations are recorded." columns={[
          ["Date", d=>date(d.donation_date)], ["Type", d=>d.donation_type], ["Blood type", d=>d.blood_type], ["Volume", d=>`${d.volume_ml} mL`],
          ["Units", d=>d.unit_codes?.join(", ") || "None recorded"],
          ["Action", d=><div className="actions">
            {donor.status === "active" && <button className="secondary" onClick={()=>setAction({unitFor:d})} aria-label={`Record unit for donation ${d.donation_id}`}>Record unit</button>}
            {d.can_delete !== false ? <button className="danger secondary" onClick={()=>setAction(d)} aria-label={`Delete donation ${d.donation_id}`}>Delete entry</button> : <span className="hint">Linked to inventory</span>}
          </div>],
        ]} />
      </section>
      {action?.unitFor && <RecordBloodUnit donor={donor} donation={action.unitFor} onClose={()=>setAction(null)} onCreated={()=>saved("Blood unit recorded and linked to this donation.")} />}
      {action === "edit" && <ProfileForm donor={donor} onClose={()=>setAction(null)} onSaved={()=>saved("Donor information saved.")} />}
      {action === "donation" && <DonationForm donor={donor} onClose={()=>setAction(null)} onSaved={()=>saved("Donation recorded. Eligibility has been recalculated.")} />}
      {action === "delete" && <ConfirmAction title="Delete donor record?" method="DELETE" path={`/api/donors/${id}/`} onClose={()=>setAction(null)} onDone={()=>saved("Donor deactivated. Donation history is retained below.")}>This disables sign-in and removes the donor from searches and suggestions. Donation history is retained.</ConfirmAction>}
      {action?.donation_id && <ConfirmAction title="Delete donation entry?" method="DELETE" path={`/api/donors/${id}/donations/${action.donation_id}/`} onClose={()=>setAction(null)} onDone={()=>saved("Donation entry deleted. Eligibility has been recalculated.")}>This removes the selected donation entry and recalculates eligibility.</ConfirmAction>}
    </>}
  </>;
}
