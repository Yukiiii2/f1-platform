export default function Loading() {
  return (
    <div className="loading-state" role="status" aria-live="polite">
      <p>Loading race data…</p>
      <div aria-hidden="true" className="skeleton skeleton-heading" />
      <div aria-hidden="true" className="skeleton skeleton-line" />
      <div aria-hidden="true" className="skeleton skeleton-table" />
    </div>
  );
}
