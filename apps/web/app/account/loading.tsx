export default function AccountLoading() {
  return (
    <div className="empty-state" role="status" aria-busy="true">
      <h1>Loading your account…</h1>
      <p>Retrieving account details and active sessions.</p>
    </div>
  );
}
