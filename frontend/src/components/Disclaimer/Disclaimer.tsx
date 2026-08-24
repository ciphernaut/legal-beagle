import { useEffect, useRef, useState } from "react";
import "./Disclaimer.css";

export const DISCLAIMER_TEXT =
  "Legal Beagle is a research and education tool. It is not legal advice and may be wrong. " +
  "Every citation is checked against the corpus; treat anything marked unresolved as unverified.";

export const ACK_KEY = "lb.disclaimerAck";

function readAck(): boolean {
  try {
    return window.localStorage.getItem(ACK_KEY) === "1";
  } catch {
    return false;
  }
}

export default function Disclaimer() {
  const [acked, setAcked] = useState<boolean>(readAck);
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    // jsdom has no showModal(); the `open` attribute below keeps the dialog rendered there.
    if (dialog && !acked && typeof dialog.showModal === "function" && !dialog.open) dialog.showModal();
  }, [acked]);

  function acknowledge() {
    try {
      window.localStorage.setItem(ACK_KEY, "1");
    } catch {
      /* storage unavailable: still dismiss for this session */
    }
    setAcked(true);
  }

  return (
    <>
      <div role="note" className="disclaimer-banner">{DISCLAIMER_TEXT}</div>
      {!acked && (
        <dialog ref={dialogRef} open role="alertdialog" aria-labelledby="disclaimer-title" className="disclaimer-modal">
          <h2 id="disclaimer-title">Before you start</h2>
          <p>{DISCLAIMER_TEXT}</p>
          <button type="button" onClick={acknowledge}>I understand</button>
        </dialog>
      )}
    </>
  );
}
