import { useState } from "react";
import { Link } from "react-router-dom";
import { birthDateToISO } from "./registration";
import { Field, Form, Header, Notice, ResourceState, Table } from "./ui";
import { COMPONENTS, title, time, useResource } from "./viewHelpers";

const PERIOD_MESSAGE = "No requests found for this period";
const STATUS_MARK = {
  pending: "◌",
  partially_fulfilled: "◑",
  fulfilled: "●",
  cancelled: "✕",
};

function StatusLabel({ value }) {
  return (
    <span className={`status-label ${value}`}>
      <span aria-hidden="true">{STATUS_MARK[value] || "•"}</span>
      {title(value)}
    </span>
  );
}

function eventDetail(event) {
  if (event.event_type === "matched") {
    return event.matched_unit_codes?.length
      ? event.matched_unit_codes.join(", ")
      : "No compatible units";
  }
  if (event.event_type === "reserved" || event.event_type === "released") {
    if (!event.unit) return "—";
    return event.unit_code ? `Unit ${event.unit} · ${event.unit_code}` : `Unit ${event.unit}`;
  }
  if (event.event_type === "status_changed") {
    return `${title(event.from_status) || "—"} → ${title(event.to_status)}`;
  }
  return "Request logged";
}

export function RequestHistory() {
  const [search, setSearch] = useState("");
  const [rangeError, setRangeError] = useState("");
  const resource = useResource(`/api/requests/history/${search}`);
  const requests = resource.data?.requests ?? [];
  const periodEmpty = resource.data?.message === PERIOD_MESSAGE;

  function apply(event) {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget));
    const fromText = String(values.logged_from || "").trim();
    const toText = String(values.logged_to || "").trim();
    if (!fromText && !toText) {
      setRangeError("");
      setSearch("");
      return;
    }
    const loggedFrom = birthDateToISO(fromText);
    const loggedTo = birthDateToISO(toText);
    if (!loggedFrom || !loggedTo) {
      setRangeError("Enter both a start date and an end date in MM/DD/YYYY format.");
      return;
    }
    if (loggedFrom > loggedTo) {
      setRangeError("The start date must be on or before the end date.");
      return;
    }
    setRangeError("");
    setSearch(`?${new URLSearchParams({ logged_from: loggedFrom, logged_to: loggedTo })}`);
  }

  return (
    <>
      <Header title="Request history">
        Trace how each blood request was logged, matched, reserved and updated.
      </Header>
      <p className="request-history-note">
        History entries are kept for traceability and cannot be edited or deleted.
      </p>
      <Form className="filters" onSubmit={apply}>
        <Field label="Logged from" name="logged_from" type="date" />
        <Field label="Logged to" name="logged_to" type="date" />
        <button type="submit" className="secondary">Apply date range</button>
      </Form>
      <Notice error>{rangeError}</Notice>
      <ResourceState resource={resource} />
      {periodEmpty && <p className="empty" role="status">{PERIOD_MESSAGE}</p>}
      {resource.data && !periodEmpty && requests.length === 0 && (
        <p className="empty" role="status">No requests have been logged.</p>
      )}
      {requests.map((request) => (
        <section className="panel audit-request" key={request.id}>
          <div className="panel-title">
            <h2><Link to={`/requests/${request.id}`}>REQ-{request.id}</Link></h2>
            <StatusLabel value={request.status} />
          </div>
          <dl className="audit-summary">
            <div><dt>Blood type</dt><dd>{request.blood_type}</dd></div>
            <div><dt>Component</dt><dd>{COMPONENTS[request.component] || title(request.component)}</dd></div>
            <div><dt>Quantity</dt><dd>{request.quantity}</dd></div>
            <div><dt>Logged</dt><dd>{time(request.logged_at)}</dd></div>
            <div><dt>Coordinator</dt><dd>{request.coordinator}</dd></div>
          </dl>
          <Table
            rows={request.events}
            empty="No request events recorded."
            columns={[
              ["Time", (event) => time(event.created_at)],
              ["Event", (event) => title(event.event_type)],
              ["Detail", eventDetail],
              ["Coordinator", (event) => event.actor_name || event.actor_email],
            ]}
          />
        </section>
      ))}
    </>
  );
}
