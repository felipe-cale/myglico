import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

// Searchable replacement for a long <select>: type to filter, arrows and Enter to choose, Escape to close.
export default function GlicoPatientPicker({ patients, value, onChange, disabled }) {
  const { t } = useTranslation();
  const listId = useId();
  const rootRef = useRef(null);
  const searchRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);

  const selected = patients.find((patient) => patient.id === value);
  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return needle ? patients.filter((patient) => patient.display_name.toLowerCase().includes(needle)) : patients;
  }, [patients, query]);

  useEffect(() => {
    if (!open) return undefined;
    searchRef.current?.focus();
    const close = (event) => {
      if (!rootRef.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  useEffect(() => setActive(0), [query, open]);

  useEffect(() => {
    if (open) document.getElementById(`${listId}-${active}`)?.scrollIntoView?.({ block: "nearest" });
  }, [active, open, listId]);

  const choose = (patient) => {
    setOpen(false);
    setQuery("");
    onChange(patient.id);
  };

  const onKeyDown = (event) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      setOpen(false);
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((index) => Math.min(index + 1, matches.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((index) => Math.max(index - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (matches[active]) choose(matches[active]);
    }
  };

  return (
    <div className="glico-picker" ref={rootRef}>
      <button
        type="button"
        id="glico-patient"
        className="glico-picker__trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={t("glicoAssistant.selectPatient")}
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
      >
        <span className={selected ? "" : "is-placeholder"}>{selected ? selected.display_name : t("glicoAssistant.selectPatientPlaceholder")}</span>
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      {open ? (
        <div className="glico-picker__popover" onKeyDown={onKeyDown}>
          <input
            ref={searchRef}
            type="search"
            className="glico-picker__search"
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-activedescendant={matches[active] ? `${listId}-${active}` : undefined}
            aria-label={t("glicoAssistant.searchPatient")}
            placeholder={t("glicoAssistant.searchPatient")}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            autoComplete="off"
          />
          <ul className="glico-picker__list" role="listbox" id={listId} aria-label={t("glicoAssistant.selectPatient")}>
            {matches.map((patient, index) => (
              <li
                key={patient.id}
                id={`${listId}-${index}`}
                role="option"
                aria-selected={patient.id === value}
                className={`glico-picker__option${index === active ? " is-active" : ""}${patient.id === value ? " is-selected" : ""}`}
                onMouseEnter={() => setActive(index)}
                onMouseDown={(event) => {
                  event.preventDefault();
                  choose(patient);
                }}
              >
                {patient.display_name}
              </li>
            ))}
            {!matches.length ? <li className="glico-picker__empty" role="presentation">{t("glicoAssistant.noPatientMatch")}</li> : null}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
