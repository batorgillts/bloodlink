import { createContext, useContext, useEffect, useId, useRef, useState } from "react";
import { fieldError, isoToUS } from "./formValidation";
import { BLOOD, COMPONENTS, title } from "./viewHelpers";
export function Notice({ error, children }) {
  return children ? (
    <div
      role={error ? "alert" : "status"}
      className={`notice ${error ? "error" : "success"}`}
    >
      {children}
    </div>
  ) : null;
}
export function Badge({ value }) {
  return <span className={`badge ${value}`}>{title(value)}</span>;
}
const FormErrors = createContext({});

export function Form({ children, onSubmit, onChange, ...props }) {
  const [errors, setErrors] = useState({});
  return <form {...props} noValidate onChange={event => {
    const name = event.target.name;
    setErrors(current => {
      if (!current[name]) return current;
      const next = { ...current };
      delete next[name];
      return next;
    });
    onChange?.(event);
  }} onSubmit={event => {
    const invalid = {};
    let first;
    for (const input of event.currentTarget.elements) {
      if (!input.name || input.disabled || !input.dataset.fieldType) continue;
      const message = fieldError(input);
      if (message) { invalid[input.name] = message; first ??= input; }
    }
    setErrors(invalid);
    if (first) {
      event.preventDefault();
      first.focus();
      return;
    }
    onSubmit?.(event);
  }}>
    {Object.keys(errors).length > 0 && <Notice error>Please correct the highlighted fields before continuing.</Notice>}
    <FormErrors.Provider value={errors}>{children}</FormErrors.Provider>
  </form>;
}

export function Field({ label, name, options, required, type = "text", pattern, minLength, maxLength, min, max, step, defaultValue, title: tooltip, ...props }) {
  const errors = useContext(FormErrors);
  const generatedId = useId();
  const error = errors[name];
  const isDate = type === "date";
  const isDateTime = type === "datetime-local";
  const hint = isDate ? "Month / Day / Year" : isDateTime ? "Month / Day / Year · 24-hour time (HH:mm)" : "";
  const description = [props["aria-describedby"], hint && `${generatedId}-hint`, error && `${generatedId}-error`].filter(Boolean).join(" ");
  // noValidate alone still allows localized hover tooltips. Keep constraints in
  // data attributes, validate in Form, and expose required/error states via ARIA.
  const attributes = {
    ...props, name,
    title: tooltip || (hint ? `${label}: ${hint}` : label),
    "aria-required": required || undefined,
    "aria-invalid": error ? true : props["aria-invalid"],
    "aria-describedby": description || undefined,
    "data-field-type": options ? "select" : type,
    "data-required": !!required,
    "data-pattern": pattern,
    "data-min-length": minLength,
    "data-max-length": maxLength,
    "data-min": min, "data-max": max, "data-step": step,
    defaultValue: isDate ? isoToUS(defaultValue) : defaultValue,
  };
  return <div className="field-control">
    <label className="field">
      <span>{label}</span>
      {options ? <select {...attributes}>
        {options.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
      </select> : <input {...attributes}
        type={["email", "number", "date", "datetime-local"].includes(type) ? "text" : type}
        inputMode={props.inputMode || (type === "email" ? "email" : type === "number" ? "numeric" : undefined)}
        placeholder={props.placeholder || (isDate ? "MM/DD/YYYY" : isDateTime ? "MM/DD/YYYY HH:mm" : undefined)}
      />}
    </label>
    {hint && <p className="field-hint" id={`${generatedId}-hint`}>{hint}</p>}
    {error && <p className="field-error" id={`${generatedId}-error`}>{error}</p>}
  </div>;
}
export function BloodFields({ filters = false }) {
  return (
    <>
      <Field
        label="Blood type"
        name="blood_type"
        required={!filters}
        options={[
          ...(filters ? [["", "All blood types"]] : []),
          ...BLOOD.map((b) => [b, b]),
        ]}
      />
      <Field
        label="Component"
        name="component"
        required={!filters}
        options={[
          ...(filters ? [["", "All components"]] : []),
          ...Object.entries(COMPONENTS),
        ]}
      />
    </>
  );
}
export function Header({ title: heading, children, action }) {
  return (
    <header className="page-heading">
      <div>
        <h1>{heading}</h1>
        <p className="muted">{children}</p>
      </div>
      {action}
    </header>
  );
}
export function Table({ columns, rows, empty = "No records yet.", rowKey }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map(([name]) => (
              <th key={name} scope="col">
                {name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length ? (
            rows.map((row, i) => (
              <tr key={rowKey ? rowKey(row) : (row.id ?? i)}>
                {columns.map(([name, render]) => (
                  <td key={name}>{render(row)}</td>
                ))}
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={columns.length} className="empty">
                {empty}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
export function Modal({ title: heading, children, onClose, busy = false }) {
  const ref = useRef(null);
  useEffect(() => {
    const previous = document.activeElement;
    const dialog = ref.current;
    dialog.showModal();
    return () => {
      dialog.close();
      previous?.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      aria-label={heading}
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onClose();
      }}
    >
      <div className="modal-heading">
        <h2>{heading}</h2>
        <button
          className="icon-button"
          type="button"
          disabled={busy}
          onClick={onClose}
          aria-label="Close dialog"
        >
          ×
        </button>
      </div>
      {children}
    </dialog>
  );
}
export function ResourceState({ resource }) {
  return resource.loading ? (
    <p className="empty" role="status">
      Loading…
    </p>
  ) : resource.error ? (
    <>
      <Notice error>{resource.error}</Notice>
      <button className="secondary" onClick={resource.reload}>
        Try again
      </button>
    </>
  ) : null;
}
