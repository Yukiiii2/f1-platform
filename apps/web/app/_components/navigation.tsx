"use client";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { seasonHref } from "../_lib/format";
import type { ReactNode } from "react";

function useSeasonYear() {
  const requested = useSearchParams().get("season");
  return requested && /^\d{4}$/.test(requested) && Number(requested) >= 1950
    ? Number(requested)
    : undefined;
}

export function SeasonHomeLink({ children }: { children: ReactNode }) {
  const year = useSeasonYear();
  return (
    <Link
      className="brand"
      href={seasonHref("/", year)}
      prefetch={false}
      aria-label="F1 Intelligence home"
    >
      {children}
    </Link>
  );
}
const links = [
  ["/", "Home"],
  ["/races", "Races"],
  ["/drivers", "Drivers"],
  ["/standings", "Standings"],
  ["/telemetry", "Telemetry Lab"],
  ["/strategy", "Strategy"],
  ["/pitwall", "Pitwall"],
  ["/comparisons", "Saved Comparisons"],
] as const;
export function Navigation() {
  const pathname = usePathname();
  const year = useSeasonYear();
  return (
    <nav className="primary-nav" aria-label="Main navigation">
      {links.map(([href, label]) => (
        <Link
          key={href}
          href={seasonHref(href, year)}
          prefetch={false}
          aria-current={
            (href === "/" ? pathname === href : pathname.startsWith(href))
              ? "page"
              : undefined
          }
        >
          {label}
        </Link>
      ))}
    </nav>
  );
}
