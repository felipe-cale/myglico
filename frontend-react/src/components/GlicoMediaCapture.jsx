import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { CameraIcon, CloseIcon, ImageIcon, MicIcon, StopIcon } from "./GlicoIcons";

const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];

const MAX_PICK_BYTES = 40 * 1048576;
const MAX_SIDE = 1600;

// Camera photos are big (3 MB or more) and slow on mobile networks. Shrink them in the browser before
// sending: upright pixels (the browser applies the EXIF rotation), 1600 px, JPEG. Falls back to the
// original file if anything is unavailable.
async function shrinkPhoto(file) {
  try {
    if (typeof createImageBitmap !== "function" || typeof document === "undefined") return file;
    const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
    const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
    if (scale === 1 && file.size <= 1.5 * 1048576) {
      bitmap.close?.();
      return file;
    }
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close?.();
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.88));
    return blob && blob.size < file.size ? blob : file;
  } catch {
    return file;
  }
}

function formatBytes(bytes) {
  return `${Math.round((bytes / 1048576) * 10) / 10} MiB`;
}

// Renders two grid children of the composer: the strip above the text field (photo preview or
// recording bar) and the tool buttons. The Blob and its preview URL live only in memory until the
// user sends or discards them; nothing is persisted.
export default function GlicoMediaCapture({ capabilities, enabled, hidden = false, processing, onSubmit, onCancel, onError }) {
  const { t } = useTranslation();
  const galleryInput = useRef(null);
  const cameraInput = useRef(null);
  const recorder = useRef(null);
  const stream = useRef(null);
  const timer = useRef(null);
  const discardRecording = useRef(false);
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [photo, setPhoto] = useState(null);
  const [touch] = useState(() => typeof navigator !== "undefined" && navigator.maxTouchPoints > 0);

  const maxSeconds = capabilities?.limits?.audio_seconds || 60;
  const photoLimit = capabilities?.limits?.photo_bytes || 3145728;
  const audioLimit = capabilities?.limits?.audio_bytes || 3145728;
  const photoOn = Boolean(capabilities?.photo);
  const audioOn = Boolean(capabilities?.audio);

  const releaseStream = useCallback(() => {
    clearInterval(timer.current);
    timer.current = null;
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
  }, []);

  useEffect(() => () => {
    if (recorder.current && recorder.current.state !== "inactive") {
      recorder.current.onstop = null;
      recorder.current.stop();
    }
    recorder.current = null;
    releaseStream();
  }, [releaseStream]);

  useEffect(() => () => {
    if (photo?.url) URL.revokeObjectURL(photo.url);
  }, [photo]);

  // A new conversation context (patient or account switch) never keeps a stale preview.
  useEffect(() => {
    if (!enabled) setPhoto(null);
  }, [enabled]);

  const pickPhoto = (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!IMAGE_TYPES.includes(file.type)) return onError("unsupported");
    if (file.size > MAX_PICK_BYTES) return onError("tooLarge");
    setPhoto({ file, url: URL.createObjectURL(file) });
  };

  const sendPhoto = async () => {
    if (!photo) return;
    const { file } = photo;
    setPhoto(null);
    const prepared = await shrinkPhoto(file);
    if (prepared.size > photoLimit) return onError("tooLarge");
    onSubmit("image", prepared);
  };

  const stopRecording = useCallback(() => {
    if (recorder.current && recorder.current.state !== "inactive") recorder.current.stop();
  }, []);

  const cancelRecording = () => {
    discardRecording.current = true;
    stopRecording();
  };

  const startRecording = async () => {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") return onError("micUnsupported");
    let media;
    try {
      media = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (reason) {
      return onError(reason?.name === "NotFoundError" ? "micUnsupported" : "micDenied");
    }
    stream.current = media;
    discardRecording.current = false;
    const chunks = [];
    const instance = new MediaRecorder(media);
    recorder.current = instance;
    instance.ondataavailable = (event) => {
      if (event.data?.size) chunks.push(event.data);
    };
    instance.onstop = () => {
      releaseStream();
      setRecording(false);
      const blob = new Blob(chunks, { type: instance.mimeType || "application/octet-stream" });
      chunks.length = 0;
      recorder.current = null;
      if (discardRecording.current || !blob.size) return;
      if (blob.size > audioLimit) return onError("tooLarge");
      onSubmit("audio", blob);
    };
    setElapsed(0);
    setRecording(true);
    instance.start();
    let seconds = 0;
    timer.current = setInterval(() => {
      seconds += 1;
      setElapsed(seconds);
      if (seconds >= maxSeconds) stopRecording();
    }, 1000);
  };

  const idle = !processing && !recording;
  const clock = `${String(Math.floor(elapsed / 60)).padStart(2, "0")}:${String(elapsed % 60).padStart(2, "0")}`;

  if (hidden) return null;

  return (
    <>
      <div className="glico-attach" role="group" aria-label={t("glicoAssistant.media.groupLabel")}>
        {photo ? (
          <div className="glico-attach__photo">
            <img src={photo.url} alt={t("glicoAssistant.media.previewAlt")} />
            <span className="glico-attach__meta">{formatBytes(photo.file.size)}</span>
            <button type="button" className="react-button react-button--primary react-button--compact" onClick={sendPhoto} disabled={!enabled || Boolean(processing)}>
              {t("glicoAssistant.media.sendPhoto")}
            </button>
            <button type="button" className="glico-icon-button" onClick={() => setPhoto(null)} aria-label={t("glicoAssistant.media.removePhoto")} title={t("glicoAssistant.media.removePhoto")}>
              <CloseIcon />
            </button>
          </div>
        ) : null}

        {recording ? (
          <div className="glico-attach__recording">
            <span className="glico-attach__dot" aria-hidden="true" />
            <span role="timer" className="glico-attach__clock">
              <span className="react-visually-hidden">{t("glicoAssistant.media.recording", { seconds: elapsed })}</span>
              <span aria-hidden="true">{clock}</span>
            </span>
            <button type="button" className="react-button react-button--quiet react-button--compact" onClick={cancelRecording}>
              {t("glicoAssistant.media.audioCancel")}
            </button>
            <button type="button" className="react-button react-button--danger react-button--compact" onClick={stopRecording}>
              <StopIcon size={16} />
              {t("glicoAssistant.media.audioStop")}
            </button>
          </div>
        ) : null}

        {processing ? (
          <div className="glico-attach__progress" role="status">
            <img src="/img/mascote-avatar-96.webp" alt="" className={`glico-attach__avatar glico-attach__avatar--${processing === "image" ? "look" : "listen"}`} width="36" height="36" />
            <span>{t(processing === "image" ? "glicoAssistant.media.processingPhoto" : "glicoAssistant.media.processingAudio")}</span>
            <button type="button" className="react-button react-button--quiet react-button--compact" onClick={onCancel}>
              {t("glicoAssistant.media.cancel")}
            </button>
          </div>
        ) : null}
      </div>

      <div className="glico-tools">
        <input
          ref={galleryInput}
          type="file"
          accept={IMAGE_TYPES.join(",")}
          className="react-visually-hidden"
          tabIndex={-1}
          aria-hidden="true"
          data-testid="glico-photo-input"
          onChange={pickPhoto}
        />
        <input
          ref={cameraInput}
          type="file"
          accept={IMAGE_TYPES.join(",")}
          capture="environment"
          className="react-visually-hidden"
          tabIndex={-1}
          aria-hidden="true"
          data-testid="glico-camera-input"
          onChange={pickPhoto}
        />
        <button
          type="button"
          className="glico-icon-button"
          onClick={() => galleryInput.current?.click()}
          disabled={!photoOn || !enabled || !idle}
          aria-label={t("glicoAssistant.media.photoButton")}
          title={photoOn ? t("glicoAssistant.media.photoHint", { size: formatBytes(photoLimit) }) : t("glicoAssistant.media.disabledPhoto")}
        >
          <ImageIcon />
        </button>
        {touch ? (
          <button
            type="button"
            className="glico-icon-button"
            onClick={() => cameraInput.current?.click()}
            disabled={!photoOn || !enabled || !idle}
            aria-label={t("glicoAssistant.media.cameraButton")}
            title={t("glicoAssistant.media.cameraButton")}
          >
            <CameraIcon />
          </button>
        ) : null}
        <button
          type="button"
          className="glico-icon-button"
          onClick={startRecording}
          disabled={!audioOn || !enabled || !idle}
          aria-label={t("glicoAssistant.media.audioStart")}
          title={audioOn ? t("glicoAssistant.media.audioHint", { seconds: maxSeconds }) : t("glicoAssistant.media.disabledAudio")}
        >
          <MicIcon />
        </button>
        {!photoOn || !audioOn ? (
          <span className="glico-tools__note">
            {!photoOn ? t("glicoAssistant.media.disabledPhoto") : t("glicoAssistant.media.disabledAudio")}
          </span>
        ) : null}
      </div>
    </>
  );
}
