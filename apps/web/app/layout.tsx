import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Suspense } from "react";
import Link from "next/link";
import localFont from "next/font/local";
import { Navigation, SeasonHomeLink } from "./_components/navigation";
import "./globals.css";

const displayFont = localFont({
  src: "../public/fonts/BarlowCondensed-SemiBold.ttf",
  weight: "600",
  display: "swap",
  variable: "--font-display",
});

export const metadata: Metadata = {
  title: {
    default: "F1 Intelligence Platform",
    template: "%s | F1 Intelligence",
  },
  description:
    "An independent view of Formula 1 race weekends, drivers and championship standings.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className={displayFont.variable}>
        <a className="skip-link" href="#main-content">
          Skip to content
        </a>
        <header className="site-header">
          <div className="shell header-inner">
            <Suspense
              fallback={
                <Link className="brand" href="/" prefetch={false}>
                  F1 Intelligence
                </Link>
              }
            >
              <SeasonHomeLink>
                <svg
                  aria-hidden="true"
                  viewBox="0 0 32 32"
                  width="32"
                  height="32"
                >
                  <path
                    d="M4 5h24v5H4zm0 9h17v5H4zm0 9h10v5H4z"
                    fill="currentColor"
                  />
                </svg>
                <span>F1 Intelligence</span>
              </SeasonHomeLink>
            </Suspense>
            <Suspense
              fallback={
                <nav aria-label="Main navigation">Loading navigation…</nav>
              }
            >
              <Navigation />
            </Suspense>
          </div>
        </header>
        <main id="main-content" className="shell" tabIndex={-1}>
          {children}
        </main>
        <footer className="site-footer shell">
          <p>Independent race data. Schedules shown in UTC.</p>
          <p>
            An unofficial project. Not affiliated with Formula 1, the FIA, any
            team or driver.
          </p>
        </footer>
      </body>
    </html>
  );
}
