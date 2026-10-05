import type { Driver } from "./contracts";

export function formatPoints(value: string | null): string {
  if (value === null) return "Not available";
  return new Intl.NumberFormat("en-GB", { maximumFractionDigits: 3 }).format(
    Number(value),
  );
}
export function formatDuration(value: number | null): string {
  if (value === null) return "Not available";
  const hours = Math.floor(value / 3600000);
  const minutes = Math.floor(value / 60000) % 60;
  const seconds = (Math.floor(value / 1000) % 60).toString().padStart(2, "0");
  const milliseconds = (value % 1000).toString().padStart(3, "0");
  return `${hours ? `${hours}:${minutes.toString().padStart(2, "0")}` : minutes}:${seconds}.${milliseconds}`;
}
export function formatSchedule(value: {
  scheduled_date: string | null;
  starts_at: string | null;
}): string {
  const source =
    value.starts_at ||
    (value.scheduled_date ? `${value.scheduled_date}T12:00:00Z` : null);
  if (!source) return "Schedule unavailable";
  const date = new Date(source);
  const day = new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
  const time = value.starts_at
    ? `${new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: "UTC" }).format(date)} UTC`
    : "Time unavailable";
  return `${day} · ${time}`;
}
export function selectSeason<T extends { year: number }>(
  seasons: T[],
  requested?: string,
): T | null {
  if (requested !== undefined)
    return seasons.find((season) => String(season.year) === requested) || null;
  return [...seasons].sort((a, b) => b.year - a.year)[0] || null;
}
export function single(
  value: string | string[] | undefined,
): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}
export function driverName(driver: Driver): string {
  return `${driver.given_name} ${driver.family_name}`;
}
export function rank(value: number | null): string {
  return value === null ? "Not ranked" : String(value);
}
