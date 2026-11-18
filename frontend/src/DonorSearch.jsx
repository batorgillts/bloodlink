import { useEffect, useId, useRef, useState } from "react";
import { api } from "./api/client";

export function DonorSearch({ value, onChange, disabled }) {
  const id = useId();
  const input = useRef(null);
  const list = useRef(null);
  const [text, setText] = useState(value?.full_name || "");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [retry, setRetry] = useState(0);
  const [result, setResult] = useState({term: "", rows: [], error: ""});
  const term = text.trim();
  const current = result.term === term;
  const rows = current ? result.rows : [];
  const searching = open && !value && !!term;

  useEffect(() => {
    list.current?.children[active]?.scrollIntoView?.({block: "nearest"});
  }, [active]);

  useEffect(() => {
    if (!term || value) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      api(`/api/donors/?${new URLSearchParams({search: term, limit: "20"})}`, {signal: controller.signal})
        .then(rows => {
          if (!controller.signal.aborted) {setResult({term, rows, error: ""}); setActive(-1);}
        })
        .catch(error => {
          if (!controller.signal.aborted) setResult({term, rows: [], error: error.message});
        });
    }, 300);
    return () => {clearTimeout(timer); controller.abort();};
  }, [term, value, retry]);

  function choose(donor) {
    onChange(donor); setText(donor.full_name); setOpen(false); setActive(-1);
  }
  function edit(next) {
    setText(next); onChange(null); setOpen(true); setActive(-1);
    // A previous query must not expose old matches while the next request is pending.
    setResult({term: "", rows: [], error: ""});
  }
  return <div className="donor-search" onBlur={event => {
    if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
  }}>
    <label className="field" htmlFor={id}><span>Find donor</span></label>
    <input ref={input} id={id} type="text" role="combobox" autoComplete="off"
      value={text} disabled={disabled} placeholder="First name, last name or email"
      maxLength={254} title="Search donors by first name, last name or email"
      aria-autocomplete="list" aria-expanded={searching} aria-controls={`${id}-results`}
      aria-describedby={`${id}-hint`} aria-activedescendant={searching && rows[active] ? `${id}-option-${active}` : undefined}
      onFocus={() => setOpen(true)} onChange={event => edit(event.target.value)}
      onKeyDown={event => {
        if (event.key === "Escape" && open) {event.preventDefault(); event.stopPropagation(); setOpen(false);}
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
          event.preventDefault(); setOpen(true);
          if (rows.length) setActive(index => event.key === "ArrowDown"
            ? (index + 1) % rows.length : (index <= 0 ? rows.length - 1 : index - 1));
        }
        if (event.key === "Enter") {
          event.preventDefault();
          if (searching && rows[active]) choose(rows[active]);
        }
      }} />
    <p className="field-hint" id={`${id}-hint`}>Search by any part of a name or email, then select a donor.</p>
    {searching && <div className="donor-search-results">
      {!current && <p role="status">Searching donors…</p>}
      {current && result.error && <><p role="alert">{result.error}</p><button type="button" className="secondary" onClick={() => {
        setResult({term: "", rows: [], error: ""}); setRetry(n => n + 1);
      }}>Try again</button></>}
      {current && !result.error && !rows.length && <p role="status">No matching donors. Try another name or email.</p>}
      <ul ref={list} id={`${id}-results`} role="listbox" aria-label="Matching donors">
        {rows.map((donor, index) => <li key={donor.id} id={`${id}-option-${index}`} role="option"
          aria-selected={active === index} onMouseDown={event => event.preventDefault()}
          onMouseEnter={() => setActive(index)} onClick={() => choose(donor)}>
          <strong>{donor.full_name}</strong><span>{donor.email}</span><span className="donor-search-blood">{donor.blood_type}</span>
        </li>)}
      </ul>
      {rows.length === 20 && <p className="field-hint">Showing up to 20 matches. Refine your search to find a specific donor.</p>}
    </div>}
    {value && <div className="donor-search-selection">
      <div><strong>{value.full_name} · {value.blood_type}</strong><span>{value.email}</span></div>
      <button type="button" className="text-button" disabled={disabled} onClick={() => {edit(""); input.current?.focus();}}>Change donor</button>
    </div>}
  </div>;
}
