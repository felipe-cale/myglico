import { useEffect, useId, useRef } from "react";
import { useTranslation } from "react-i18next";
import CloseIcon from "./CloseIcon";

const FOCUSABLE = 'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), a[href]';

export default function ConfirmDialog({
  open,
  eyebrow,
  title,
  description,
  confirmLabel,
  cancelLabel,
  busy = false,
  error = "",
  onConfirm,
  onCancel,
  children
}) {
  const { t } = useTranslation();
  const titleId = useId();
  const descriptionId = useId();
  const dialogRef = useRef(null);
  const cancelRef = useRef(null);
  const onCancelRef = useRef(onCancel);
  onCancelRef.current = onCancel;

  useEffect(() => {
    if (!open) return undefined;
    const previous = document.activeElement;
    cancelRef.current?.focus();
    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCancelRef.current?.();
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = Array.from(dialogRef.current.querySelectorAll(FOCUSABLE));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      if (previous && typeof previous.focus === "function" && document.contains(previous)) previous.focus();
    };
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="react-dialog-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onCancel();
      }}
    >
      <div
        className="react-dialog react-dialog--confirm"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        ref={dialogRef}
      >
        <div className="react-dialog__header">
          <div>
            {eyebrow ? <p className="react-eyebrow">{eyebrow}</p> : null}
            <h3 id={titleId}>{title}</h3>
          </div>
          <button type="button" className="react-dialog__close" onClick={onCancel} aria-label={t("common.closeDialog")}>
            <CloseIcon />
          </button>
        </div>
        <div className="react-dialog__body">
          <p id={descriptionId}>{description}</p>
          {children}
          {error ? <p className="react-form-message is-error" role="alert">{error}</p> : null}
          <div className="react-dialog__actions">
            <button type="button" ref={cancelRef} className="react-button react-button--ghost" onClick={onCancel}>
              {cancelLabel}
            </button>
            <button type="button" className="react-button react-button--danger-solid" onClick={onConfirm} disabled={busy}>
              {confirmLabel}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
