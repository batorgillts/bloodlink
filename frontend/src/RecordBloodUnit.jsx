import { useState } from "react";
import { api } from "./api/client";
import { localDateTimeInput, localDateTimeToISO } from "./formValidation";
import { Field, Form, Modal, Notice, ResourceState } from "./ui";
import { COMPONENTS, date, title, useResource } from "./viewHelpers";
import { DonorSearch } from "./DonorSearch";

export function RecordBloodUnit({ donor: initialDonor, donation, onClose, onCreated }) {
  const [selectedDonor, setSelectedDonor] = useState(initialDonor || null);
  const donorId = String(selectedDonor?.id || "");
  const [busy, setBusy] = useState(false);
  return <Modal title="Record blood unit" onClose={onClose} busy={busy}>
    <p className="muted">Link every unit to its source donation. Expiry is calculated from the component's shelf life.</p>
    <DonorSearch value={selectedDonor} onChange={setSelectedDonor} disabled={busy} />
    {donorId && <UnitForm key={donorId} donorId={donorId}
      initialDonation={String(initialDonor?.id) === donorId ? donation : null}
      busy={busy} setBusy={setBusy} onClose={onClose} onCreated={onCreated} />}
  </Modal>;
}

export function EditBloodUnit({ unit, onClose, onSaved }) {
  const [busy, setBusy] = useState(false);
  const props = {unit, busy, setBusy, onClose, onSaved};
  return <Modal title={`Edit ${unit.unit_code}`} busy={busy} onClose={onClose}>
    {unit.source_donation ? <SourceCorrection {...props} /> : <UnitCorrectionForm {...props} />}
  </Modal>;
}

function SourceCorrection(props) {
  const resource = useResource(`/api/donors/${props.unit.source_donation.donor_id}/`);
  return <><ResourceState resource={resource} />
    {resource.data && <UnitCorrectionForm {...props} donor={resource.data} />}</>;
}

function UnitCorrectionForm({ unit, donor, busy, setBusy, onClose, onSaved }) {
  const [type, setType] = useState(unit.source_donation?.donation_type || "");
  const [component, setComponent] = useState(unit.component);
  const initialTime = localDateTimeInput(unit.collected_at);
  const [collected, setCollected] = useState(initialTime);
  const [error, setError] = useState("");
  const rule = donor?.eligibility.find(e => e.donation_type === type);
  const components = rule?.allowed_components ?? Object.keys(COMPONENTS);
  const selectedComponent = components.includes(component) ? component : components[0] || "";
  const source = donor?.donations.find(d => d.donation_id === unit.donation_id);
  const dirty = type !== (unit.source_donation?.donation_type || "") ||
    selectedComponent !== unit.component || collected !== initialTime;
  async function submit(event) {
    event.preventDefault();
    const body = {};
    if (selectedComponent !== unit.component) body.component = selectedComponent;
    if (collected !== initialTime) body.collected_at = localDateTimeToISO(collected);
    if (donor && type !== unit.source_donation.donation_type) body.donation_type = type;
    setBusy(true); setError("");
    try {onSaved(await api(`/api/units/${unit.id}/`, {method:"PATCH", body}));}
    catch (err) {setError(err.message);}
    finally {setBusy(false);}
  }
  return <>
    <p>{donor ? `${donor.full_name} · Donation #${unit.donation_id}` : "Source not recorded"} · {unit.blood_type}</p>
    <Notice error>{error}</Notice>
    <Form onSubmit={submit}><fieldset className="form-grid" disabled={busy}>
      {donor && <Field label="Source donation type" name="donation_type" value={type}
        onChange={e => setType(e.target.value)} options={donor.eligibility.map(e => [e.donation_type,e.label])} required />}
      <Field label="Component" name="component" value={selectedComponent} onChange={e => setComponent(e.target.value)}
        options={components.map(c => [c,COMPONENTS[c]])} required />
      <Field label="Collection date and time (your local time)" name="collected_at" type="datetime-local"
        value={collected} onChange={e => setCollected(e.target.value)} required />
      <p className="hint">Expiry is recalculated when the collection time or component changes.</p>
      {donor && <p className="hint">This donation has {source?.unit_codes?.length || 1} linked unit(s). Changing the calendar date updates the donation date and moves all linked units by the same number of days, preserving their times. Correcting the source donation type changes its waiting-period rule. Eligibility is recalculated automatically; the donation count stays the same.</p>}
      <div className="actions"><button className="secondary" type="button" onClick={onClose}>Cancel</button>
        <button type="submit" disabled={!dirty}>{busy ? "Saving…" : "Save corrections"}</button></div>
    </fieldset></Form>
  </>;
}

function UnitForm({ donorId, initialDonation, busy, setBusy, onClose, onCreated }) {
  const resource = useResource(`/api/donors/${donorId}/`);
  const [mode, setMode] = useState("existing");
  const [donationId, setDonationId] = useState(String(initialDonation?.donation_id || ""));
  const [donationType, setDonationType] = useState("");
  const [error, setError] = useState("");
  const donor = resource.data;
  const donation = donor?.donations.find(d => String(d.donation_id) === donationId);
  const type = mode === "existing" ? donation?.donation_type : donationType || donor?.eligibility[0]?.donation_type;
  const rule = donor?.eligibility.find(e => e.donation_type === type);
  const components = rule?.allowed_components ?? Object.keys(COMPONENTS);
  async function submit(event) {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget));
    const body = {
      donor_id: Number(donorId), unit_code: values.unit_code, component: values.component,
      blood_type: mode === "existing" ? donation.blood_type : donor.blood_type,
      collected_at: localDateTimeToISO(values.collected_at),
      ...(mode === "existing" ? { donation_id: Number(donationId) } : {
        donation_type: values.donation_type, volume_ml: Number(values.volume_ml),
      }),
    };
    setBusy(true); setError("");
    try { onCreated(await api("/api/units/", { method: "POST", body })); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  return <>
    <ResourceState resource={resource} />
    {donor && <Form onSubmit={submit}><fieldset className="form-grid" disabled={busy}>
      <Notice error>{error}</Notice>
      <Field label="Donation record" name="source_mode" value={mode} onChange={e => {setMode(e.target.value); setError("");}}
        options={[["existing", "Add a unit from an existing donation"], ["new", "Record a new donation with this unit"]]} />
      {mode === "existing" ? <>
        <Field label="Source donation" name="donation_id" value={donationId} required
          onChange={e => setDonationId(e.target.value)} options={[
            ["", "Select a donation"], ...donor.donations.map(d => [String(d.donation_id),
              `#${d.donation_id} · ${date(d.donation_date)} · ${title(d.donation_type)} · ${d.volume_ml} mL`]),
          ]} />
        <p className="hint">{donor.donations.length
          ? "Creates an additional unit from the same donation. To correct a recorded unit or its source date, use Edit in Blood inventory."
          : "No donations recorded. Choose ‘Record a new donation with this unit’ to record the donor's first donation."}</p>
      </> : <>
        <Field label="Donation type" name="donation_type" value={type} onChange={e => setDonationType(e.target.value)} required options={donor.eligibility.map(e => [e.donation_type, e.label])} />
        <Field label="Donation volume (mL)" name="volume_ml" type="number" min="1" step="1" required />
        <p className="hint">Donation type records how the donor donated and sets the waiting period. Component records the stored product and sets its expiry. Whole blood can supply multiple components; double red cells still produce red-cell units.</p>
      </>}
      <Field label="Unique unit code" name="unit_code" required maxLength={32} />
      <div className="two-columns">
        <Field label="Blood type" name="blood_type" readOnly value={mode === "existing" ? donation?.blood_type || "" : donor.blood_type} />
        <Field key={type || "unselected"} label="Component" name="component" required options={components.map(c => [c, COMPONENTS[c]])} />
      </div>
      <Field key={`${mode}-${donationId}`} label="Collection date and time (your local time)" name="collected_at" type="datetime-local"
        defaultValue={mode === "new" ? localDateTimeInput() : ""} required />
      <p className="hint">The donation date uses the collection date in America/New_York. For an existing donation, these dates must match.</p>
      <div className="actions">
        <button className="secondary" type="button" onClick={onClose}>Cancel</button>
        <button type="submit" disabled={mode === "existing" && !donation}>{busy ? "Saving…" : "Record unit"}</button>
      </div>
    </fieldset></Form>}
  </>;
}
