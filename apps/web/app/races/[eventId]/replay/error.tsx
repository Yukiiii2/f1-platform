"use client";
export default function ReplayError({ reset }: { reset: () => void }) {
  return (
    <div className="empty-state" role="alert">
      <h2>Replay temporarily unavailable</h2>
      <p>
        Recorded replay data could not be loaded. Your selected weekend and
        session are preserved. Try again in a moment.
      </p>
      <button className="button" type="button" onClick={reset}>
        Retry replay
      </button>
    </div>
  );
}
