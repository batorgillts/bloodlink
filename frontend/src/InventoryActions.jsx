import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "./api/client";
import { Field, Modal, Notice, ResourceState, Table } from "./ui";
import { date, time, title, useResource } from "./viewHelpers";
import { ConfirmAction } from "./DonorManagement";

export function WithdrawRegistration({ onWithdrawn, email }) {
  const [confirm, setConfirm] = useState(false);
  return <section className="panel">
    <h2>Registration</h2>
    <p>Withdrawing disables sign-in and removes you from donor suggestions. Your donation history is retained.</p>
    <button className="danger secondary" onClick={()=>setConfirm(true)}>Withdraw registration</button>
    {confirm && <ConfirmAction title="Withdraw registration?" path="/api/donors/me/withdraw/" onClose={()=>setConfirm(false)} onDone={onWithdrawn}>{email ? `${email}: ` : ""}Your account will be deactivated. You will no longer be able to sign in. Previous donation history will be retained.</ConfirmAction>}
  </section>;
}

export function DiscardUnit({ unit, onClose, onDiscarded }) {
  const [reason, setReason] = useState(unit.effective_status === "expired" ? "expired" : "");
  const [warning, setWarning] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function discard(confirm) {
    setBusy(true); setError("");
    try { const result = await api(`/api/units/${unit.id}/discard/`, { method:"POST", body:{reason, confirm} }); onDiscarded(result); }
    catch (err) {
      if (err.status === 409 && err.data?.confirm_required) setWarning(err.data);
      else { setWarning(null); setError(err.message); }
    } finally { setBusy(false); }
  }
  return <Modal title={`Discard ${unit.unit_code}?`} onClose={onClose} busy={busy}>
    <p>This permanently removes the unit from usable inventory.</p>
    <Notice error>{error}</Notice>
    <Field label="Discard reason" name="reason" value={reason} disabled={busy || !!warning} onChange={e=>setReason(e.target.value)} options={[
      ["", "Choose a reason"], ...["expired", "damaged", "failed_testing", "other"].map(r=>[r,title(r)]),
    ]} />
    {warning && <div role="alert" className="notice error">
      This unit is reserved for request REQ-{warning.request_id}. Discarding it releases its reservation and reduces the request's reserved quantity.
    </div>}
    <div className="actions">
      <button className="secondary" disabled={busy} onClick={onClose}>Go back</button>
      <button className="danger" disabled={busy || !reason} onClick={()=>discard(!!warning)}>{busy ? "Saving…" : warning ? "Confirm discard of reserved unit" : "Discard unit"}</button>
    </div>
  </Modal>;
}

function Suggestions({ id }) {
  const resource = useResource(`/api/requests/${id}/donor-suggestions/`);
  return <><ResourceState resource={resource} />{resource.data && <>
    <p className="muted">Eligible for {title(resource.data.donation_type)} under the configured project rules. Suggestions do not reserve blood or send messages.</p>
    <Table rows={resource.data.donors} rowKey={d=>d.donor_id} empty="No eligible donors found." columns={[
      ["Name",d=><Link to={`/donors/${d.donor_id}`}>{d.full_name}</Link>], ["Blood type",d=>d.blood_type],
      ["Last donation",d=>date(d.last_donation_date)], ["Email",d=>d.email], ["Phone",d=>d.phone],
    ]} />
  </>}</>;
}
function History({ id }) {
  const resource = useResource(`/api/requests/${id}/history/`);
  return <><ResourceState resource={resource} />{resource.data && <Table rows={resource.data} empty="No request events recorded." columns={[
    ["Time",e=>time(e.created_at)], ["Event",e=>title(e.event_type)], ["From",e=>title(e.from_status) || "—"], ["To",e=>title(e.to_status) || "—"], ["Coordinator",e=>e.actor_email],
  ]} />}</>;
}
export function RequestExtras({ request }) {
  const [suggestions, setSuggestions] = useState(false);
  const [history, setHistory] = useState(false);
  const [version, setVersion] = useState(0);
  return <>
    {request.can_cancel && <section className="panel"><div className="panel-title"><h2>Eligible donor suggestions</h2>
      <button onClick={()=>{setSuggestions(true);setVersion(v=>v+1);}}>{suggestions ? "Refresh donor suggestions" : "Find eligible donors"}</button>
    </div>{suggestions && <Suggestions key={version} id={request.id} />}</section>}
    <section className="panel"><div className="panel-title"><h2>Request activity</h2>
      <button className="secondary" onClick={()=>{setHistory(true);setVersion(v=>v+1);}}>View / refresh activity</button>
    </div>{history && <History key={version} id={request.id} />}</section>
  </>;
}
