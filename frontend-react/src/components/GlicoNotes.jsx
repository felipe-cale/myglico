import { useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import CloseIcon from "./CloseIcon";
import useFocusTrap from "../hooks/useFocusTrap";
import useBodyScrollLock from "../hooks/useBodyScrollLock";

export default function GlicoNotes({ languageModel }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const titleId = useId();
  const dialogRef = useRef(null);
  const closeRef = useRef(null);
  const close = () => setOpen(false);

  useFocusTrap(open, dialogRef, { initialFocusRef: closeRef, onEscape: close });
  useBodyScrollLock(open);

  return (
    <>
      <button type="button" className="glico__notes-link" onClick={() => setOpen(true)} aria-haspopup="dialog">
        {t("glicoAssistant.notesTitle")}
      </button>
      {open ? (
        <div
          className="react-dialog-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) close();
          }}
        >
          <div className="react-dialog react-dialog--confirm glico-notes" role="dialog" aria-modal="true" aria-labelledby={titleId} ref={dialogRef}>
            <div className="react-dialog__header">
              <div>
                <h3 id={titleId}>{t("glicoAssistant.notesTitle")}</h3>
              </div>
              <button type="button" ref={closeRef} className="react-dialog__close" onClick={close} aria-label={t("common.closeDialog")}>
                <CloseIcon />
              </button>
            </div>
            <div className="react-dialog__body glico-notes__body">
              {languageModel ? <p data-testid="glico-llm-note">{t("glicoAssistant.llmNote")}</p> : null}
              <p>{t("glicoAssistant.notClinicalAdvice")}</p>
              <p>{t("glicoAssistant.privacyNote")}</p>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
