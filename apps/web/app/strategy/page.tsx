import type { Metadata } from "next";
import Link from "next/link";
import { SessionUpdates } from "../_components/session-updates";
import { Pitwall } from "../_components/pitwall";
import { suggestedQuestions } from "../_lib/pitwall";
import { notFound } from "next/navigation";
import type { Driver, SearchPageProps } from "../_lib/contracts";
import { ApiError, getSessionStrategy } from "../_lib/api";
import {
  eventSessions,
  references,
  seasonContext,
  seasonEvents,
} from "../_lib/data";
import { driverName, single } from "../_lib/format";
import type { Strategy } from "../_lib/strategy-contracts";
import { selectStrategies, strategyKey } from "../_lib/strategy";
import {
  EmptyState,
  NoSeason,
  PageHeading,
  SectionHeading,
  SeasonSelector,
} from "../_components/ui";
import { StrategyView } from "./strategy-view";
import { SaveComparison } from "../_components/save-comparison";
import { accountState } from "../_lib/auth-api";
import { strategyPreset } from "../_lib/saved-comparisons";
import "./strategy.css";

export const metadata: Metadata = { title: "Strategy + Tyres" };

export default async function StrategyPage({ searchParams }: SearchPageProps) {
  const query = await searchParams;
  const account = await accountState();
  const returnTo = `/strategy?${new URLSearchParams(
    Object.entries(query).flatMap(([key, value]) => {
      const item = single(value);
      return item === undefined ? [] : [[key, item]];
    }),
  )}`;
  const { seasons, season } = await seasonContext(query);
  const events = season ? await seasonEvents(season.year) : [];
  const event = events.find((row) => row.id === single(query.event));
  if (season && single(query.event) && !event) notFound();
  const races = event
    ? (await eventSessions(event.id)).filter((row) => row.type === "race")
    : [];
  const sessionId = single(query.session);
  const race = sessionId
    ? races.find((row) => row.id === sessionId)
    : (races.find((row) => row.status === "completed") ?? races[0]);
  if (event && sessionId && !race) notFound();
  let strategy: Strategy | null = null;
  let failure: string | null = null;
  if (race?.status === "completed") {
    try {
      strategy = await getSessionStrategy<Strategy>(race.id);
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
      failure =
        error.status === 422 || error.status === 404
          ? "This race is no longer available as a completed race. Load another weekend."
          : "Strategy data is temporarily unreachable. Retry this race or choose another weekend.";
    }
  }
  const drivers = await references<Driver>(
    "drivers",
    strategy?.drivers.map((row) => row.driver_id) ?? [],
  );
  const rows = strategy
    ? [...strategy.drivers].sort(
        (a, b) =>
          driverName(drivers.get(a.driver_id)!).localeCompare(
            driverName(drivers.get(b.driver_id)!),
          ) || a.provider.localeCompare(b.provider),
      )
    : [];
  const selected = selectStrategies(rows, {
    a: single(query.a),
    b: single(query.b),
  });
  const preset =
    event && race && season && strategy && selected
      ? strategyPreset(
          { season: season.year, event_id: event.id, session_id: race.id },
          selected,
        )
      : null;
  return (
    <>
      <PageHeading
        title="Strategy + Tyres."
        intro="Read the recorded stint sequence. Compare compounds, pit timing and observed pace."
      >
        <SeasonSelector seasons={seasons} selected={season} />
      </PageHeading>
      {event && race && (
        <a className="back-link" href="#pitwall">
          Ask Pitwall about this race
        </a>
      )}
      {race && <SessionUpdates session={race} />}
      {!season ? (
        <NoSeason />
      ) : (
        <>
          <section aria-label="Choose a race">
            <SectionHeading title="Choose a race" />
            <form action="/strategy" method="get" className="filter-form">
              <input type="hidden" name="season" value={season.year} />
              <div className="field">
                <label htmlFor="strategy-event">Race weekend</label>
                <select
                  id="strategy-event"
                  name="event"
                  required
                  defaultValue={event?.id ?? ""}
                  disabled={!events.length}
                >
                  <option value="" disabled>
                    Choose a weekend
                  </option>
                  {events
                    .sort((a, b) => a.round - b.round)
                    .map((row) => (
                      <option key={row.id} value={row.id}>
                        Round {row.round} · {row.name}
                      </option>
                    ))}
                </select>
              </div>
              <button
                className="button button-quiet"
                type="submit"
                disabled={!events.length}
              >
                Load race
              </button>
            </form>
            {event && (
              <p className="section-note">
                <Link
                  href={`/races/${event.id}?season=${season.year}${race ? `&session=${race.id}` : ""}`}
                  prefetch={false}
                >
                  {event.name}
                </Link>{" "}
                · Race{race?.status === "completed" ? " · Completed" : ""}
              </p>
            )}
          </section>
          {!events.length ? (
            <EmptyState title="No imported weekends">
              <p>Choose another season with race data.</p>
            </EmptyState>
          ) : !event ? (
            <EmptyState title="Start with a completed race">
              <p>Load a weekend to inspect its recorded strategy.</p>
            </EmptyState>
          ) : !race || race.status !== "completed" ? (
            <EmptyState title="Completed race required">
              <p>
                The source records do not confirm a completed race for this
                weekend. Choose another weekend or return after completed-race
                data has been imported.
              </p>
            </EmptyState>
          ) : failure ? (
            <div className="empty-state" role="alert">
              <h2>Strategy unavailable</h2>
              <p>{failure}</p>
              <a
                className="button button-quiet"
                href={`/strategy?season=${season.year}&event=${event.id}&session=${race.id}`}
              >
                Retry strategy
              </a>
            </div>
          ) : !strategy || !rows.length ? (
            <EmptyState title="No historical strategy records">
              <p>
                Core classification alone does not include stints or pit stops.
                Choose another race or return after historical session data has
                been imported.
              </p>
            </EmptyState>
          ) : (
            <>
              <section aria-label="Choose comparison drivers">
                <SectionHeading title="Compare drivers" />
                <form
                  action="/strategy"
                  method="get"
                  className="filter-form strategy-selectors"
                >
                  <input type="hidden" name="season" value={season.year} />
                  <input type="hidden" name="event" value={event.id} />
                  <input type="hidden" name="session" value={race.id} />
                  {(["a", "b"] as const).map((side, index) => (
                    <div className="field" key={side}>
                      <label htmlFor={`strategy-${side}`}>
                        Driver {side.toUpperCase()}
                      </label>
                      <select
                        key={single(query[side]) ?? "default"}
                        id={`strategy-${side}`}
                        name={side}
                        defaultValue={
                          selected?.[index]
                            ? strategyKey(selected[index])
                            : (single(query[side]) ?? "")
                        }
                        required={side === "a"}
                      >
                        <option value="" disabled={side === "a"}>
                          {side === "a"
                            ? "Choose an imported driver"
                            : "Single driver"}
                        </option>
                        {rows.map((row) => (
                          <option
                            value={strategyKey(row)}
                            key={strategyKey(row)}
                          >
                            {driverName(drivers.get(row.driver_id)!)} ·{" "}
                            {row.provider}
                          </option>
                        ))}
                      </select>
                    </div>
                  ))}
                  <button className="button button-quiet" type="submit">
                    Compare strategies
                  </button>
                </form>
              </section>
              {selected === null ? (
                <EmptyState title="Choose distinct imported records">
                  <p>
                    Choose one driver or two different driver/provider records,
                    then compare again.
                  </p>
                </EmptyState>
              ) : (
                <>
                  {preset && (
                    <SaveComparison
                      key={JSON.stringify(preset)}
                      preset={preset}
                      signedIn={!!account.user}
                      authUnavailable={!!account.error}
                      returnTo={returnTo}
                      suggestedTitle={`${season.year} ${event.name} · ${selected.map((row) => driverName(drivers.get(row.driver_id)!)).join(" / ")}`}
                    />
                  )}
                  <StrategyView
                    strategy={strategy}
                    selected={selected}
                    drivers={drivers}
                  />
                </>
              )}
            </>
          )}
        </>
      )}
      {event && race && season && (
        <Pitwall
          selectionKey={selected?.map(strategyKey).join("|") ?? "no-selection"}
          questionScope={
            selected?.length
              ? `Displayed strategy drivers: ${selected.map((row, index) => `${index === 0 ? "A" : "B"} = ${driverName(drivers.get(row.driver_id)!)} (driver ID ${row.driver_id})`).join("; ")}.`
              : undefined
          }
          context={{
            route: "/strategy",
            season: season.year,
            event_id: event.id,
            session_id: race.id,
            ...(selected?.length === 1
              ? { driver_id: selected[0].driver_id }
              : {}),
          }}
          label={`${season.year} · ${event.name}`}
          contextDetails={[
            { label: "Session", value: "Race" },
            ...(selected?.length
              ? selected.map((row, index) => ({
                  label: `Driver ${index === 0 ? "A" : "B"}`,
                  value: driverName(drivers.get(row.driver_id)!),
                }))
              : [{ label: "Drivers", value: "No strategy drivers selected" }]),
          ]}
          names={Object.fromEntries(
            [...drivers].map(([id, row]) => [id, driverName(row)]),
          )}
          suggestions={suggestedQuestions({
            page: "strategy",
            drivers: (selected ?? []).map((row) => ({
              ...row,
              name: driverName(drivers.get(row.driver_id)!),
            })),
          })}
        />
      )}
    </>
  );
}
