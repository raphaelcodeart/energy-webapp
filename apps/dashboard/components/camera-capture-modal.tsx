"use client";

import { useEffect, useRef, useState } from "react";

/** Live, in-page camera capture (getUserMedia + a viewfinder), not just the
    OS-native camera picker a plain `<input capture>` opens -- that one only
    works on some mobile browsers and does nothing at all on desktop (no
    webcam access), so "accendi la fotocamera" needs a real viewfinder that
    works the same way everywhere a camera exists. Falls back to a clear
    error state (with the option to close and use the file-upload button
    instead) when the camera can't be opened -- permission denied, no
    camera, or a non-secure context. */
export function CameraCaptureModal({
  onCapture,
  onClose,
}: {
  onCapture: (file: File) => void;
  onClose: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [capturing, setCapturing] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function start() {
      if (!navigator.mediaDevices?.getUserMedia) {
        setError("Il tuo browser non supporta l'accesso alla fotocamera.");
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: "environment" } },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
        setReady(true);
      } catch {
        if (!cancelled) {
          setError("Impossibile accedere alla fotocamera. Controlla i permessi del browser oppure carica un file.");
        }
      }
    }

    start();
    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  function handleCapture() {
    const video = videoRef.current;
    if (!video || !video.videoWidth) return;
    setCapturing(true);
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    ctx?.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(
      (blob) => {
        setCapturing(false);
        if (!blob) return;
        const file = new File([blob], `fattura-${Date.now()}.jpg`, { type: "image/jpeg" });
        streamRef.current?.getTracks().forEach((t) => t.stop());
        onCapture(file);
      },
      "image/jpeg",
      0.9
    );
  }

  function handleClose() {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    onClose();
  }

  return (
    <div className="fixed inset-0 z-[110] flex items-center justify-center p-4 bg-black/85 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-md rounded-2xl overflow-hidden bg-slate-950 border border-white/10 animate-scale-up">
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
          <p className="text-sm font-semibold text-white">Scatta una foto della fattura</p>
          <button onClick={handleClose} className="p-1 rounded-lg hover:bg-white/10 text-slate-400 hover:text-white transition cursor-pointer">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="relative aspect-[3/4] bg-black flex items-center justify-center">
          {error ? (
            <div className="p-6 text-center space-y-3">
              <svg className="w-10 h-10 text-rose-400 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 3l18 18M9.88 9.88a3 3 0 104.24 4.24M15 4h.01M5 8V6a2 2 0 012-2h1.586a1 1 0 00.707-.293l.828-.828A2 2 0 0111.536 2h.928a2 2 0 011.414.586l.828.828A1 1 0 0015.414 4H17a2 2 0 012 2v8a2 2 0 01-.586 1.414" />
              </svg>
              <p className="text-sm text-slate-300">{error}</p>
              <button
                onClick={handleClose}
                className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/20 text-white text-xs font-semibold transition cursor-pointer"
              >
                Chiudi e carica un file
              </button>
            </div>
          ) : (
            <>
              {/* eslint-disable-next-line jsx-a11y/media-has-caption -- live camera viewfinder, no captions apply */}
              <video ref={videoRef} autoPlay playsInline muted className="w-full h-full object-cover" />
              {!ready && (
                <div className="absolute inset-0 flex items-center justify-center bg-black/60">
                  <svg className="w-8 h-8 text-white animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                </div>
              )}
              {/* Framing guide only -- purely visual, matches a document-scan UI convention */}
              <div className="absolute inset-6 border-2 border-white/40 rounded-xl pointer-events-none" />
            </>
          )}
        </div>

        {!error && (
          <div className="p-4 flex items-center justify-center">
            <button
              onClick={handleCapture}
              disabled={!ready || capturing}
              className="w-16 h-16 rounded-full bg-white flex items-center justify-center shadow-lg transition disabled:opacity-40 cursor-pointer active:scale-95"
              aria-label="Scatta foto"
            >
              <span className="w-12 h-12 rounded-full border-2 border-slate-900" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
