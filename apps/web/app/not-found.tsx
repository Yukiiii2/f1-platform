import Link from "next/link";
export default function NotFound() {
  return (
    <div className="empty-state">
      <h1>This page is unavailable.</h1>
      <p>The requested race, driver or session was not found.</p>
      <Link className="button" href="/races" prefetch={false}>
        Browse races
      </Link>
    </div>
  );
}
