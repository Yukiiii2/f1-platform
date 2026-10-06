"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
const links = [
  ["/", "Home"],
  ["/races", "Races"],
  ["/drivers", "Drivers"],
  ["/standings", "Standings"],
  ["/telemetry", "Telemetry Lab"],
  ["/strategy", "Strategy"],
  ["/pitwall", "Pitwall"],
] as const;
export function Navigation() {
  const pathname = usePathname();
  return (
    <nav className="primary-nav" aria-label="Main navigation">
      {links.map(([href, label]) => (
        <Link
          key={href}
          href={href}
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
