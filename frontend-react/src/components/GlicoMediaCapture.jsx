import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];

function formatBytes(bytes) {
  return `${Math.round((bytes / 1048576) * 10) / 10} MiB`;
}

// Capture is transient: the Blob only lives in this closure until onSubmit settles; nothing is stored or previewed.
export default function GlicoMediaCapture({ capabilities, enabled, processing, onSubmit, onCancel, onError }) {
  const { t } = useTranslation();
  const fileInput = useRef(null);
  const recorder = useRef(null);
  const stream = useRef(null);
  const timer = useRef(null);
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);

  const maxSeconds = capabilities?.limits?.audio_seconds || 60;
  const photoLimit = capabilities?.limits?.photo_bytes || 3145728;
  const audioLimit = capabilities?.limits?.audio_bytes || 3145728;

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

  const pickPhoto = (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!IMAGE_TYPES.includes(file.type)) return onError("unsupported");
    if (file.size > photoLimit) return onError("tooLarge");
    onSubmit("image", file);
  };

  const stopRecording = useCallback(() => {
    if (recorder.current && recorder.current.state !== "inactive") recorder.current.stop();
  }, []);

  const startRecording = async () => {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") return onError("micUnsupported");
    let media;
    try {
      media = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (reason) {
      return onError(reason?.name === "NotFoundError" ? "micUnsupported" : "micDenied");
    }
    stream.current = media;
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
      if (!blob.size) return;
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

  const photoOn = Boolean(capabilities?.photo);
  const audioOn = Boolean(capabilities?.audio);

  return (
    <div className="glico-media" role="group" aria-label={t("glicoAssistant.media.groupLabel")}>
      <div className="glico-media__item">
        <input
          ref={fileInput}
          type="file"
          accept={IMAGE_TYPES.join(",")}
          capture="environment"
          className="react-visually-hidden"
          tabIndex={-1}
          aria-hidden="true"
          data-testid="glico-photo-input"
          onChange={pickPhoto}
        />
        <button
          type="button"
          className="react-button react-button--ghost"
          onClick={() => fileInput.current?.click()}
          disabled={!photoOn || !enabled || processing || recording}
          aria-describedby="glico-photo-hint"
        >
          {t("glicoAssistant.media.photoButton")}
        </button>
        <span id="glico-photo-hint" className="glico-hint">
          {photoOn ? t("glicoAssistant.media.photoHint", { size: formatBytes(photoLimit) }) : t("glicoAssistant.media.disabledPhoto")}
        </span>
      </div>

      <div className="glico-media__item">
        {recording ? (
          <button type="button" className="react-button react-button--danger" onClick={stopRecording}>
            {t("glicoAssistant.media.audioStop")}
          </button>
        ) : (
          <button
            type="button"
            className="react-button react-button--ghost"
            onClick={startRecording}
            disabled={!audioOn || !enabled || processing}
            aria-describedby="glico-audio-hint"
          >
            {t("glicoAssistant.media.audioStart")}
          </button>
        )}
        <span id="glico-audio-hint" className="glico-hint">
          {recording
            ? <span role="timer">{t("glicoAssistant.media.recording", { seconds: elapsed })}</span>
            : audioOn
              ? t("glicoAssistant.media.audioHint", { seconds: maxSeconds })
              : t("glicoAssistant.media.disabledAudio")}
        </span>
      </div>

      {processing ? (
        <div className="glico-media__progress" role="status">
          <span>{t(processing === "image" ? "glicoAssistant.media.processingPhoto" : "glicoAssistant.media.processingAudio")}</span>
          <button type="button" className="react-button react-button--quiet" onClick={onCancel}>
            {t("glicoAssistant.media.cancel")}
          </button>
        </div>
      ) : null}
    </div>
  );
}
