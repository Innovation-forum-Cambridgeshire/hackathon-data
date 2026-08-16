/**
 * Event timing. Stored in UTC, displayed in Europe/London.
 *
 * BST ENDS ON SUNDAY 25 OCTOBER 2026 — THE DAY BEFORE THE EVENT STARTS
 * ---------------------------------------------------------------------
 * This is the whole reason the file exists rather than a `new Date(...)` inline.
 *
 * Challenge 03 runs 26-30 October 2026. The clocks go back on the 25th. So the
 * event is the first working week of GMT, while every planning conversation
 * before it happened in BST. A deadline written as "16:00" without a zone, or a
 * countdown computed from a local-time string, is an hour wrong for the entire
 * event — and wrong in the direction that closes submissions early.
 *
 * Two rules, and neither is negotiable:
 *   1. Every instant is stored as an explicit UTC ISO string with a Z.
 *   2. Every rendering goes through Intl with timeZone: 'Europe/London', which
 *      applies the correct offset for the date rather than the offset today.
 *
 * The published rules must say "16:00 GMT", not "16:00". Participants in other
 * countries will otherwise convert from the wrong zone.
 */

/** The event window and deadline, in UTC. GMT applies on these dates. */
export const EVENT = {
  slug: "c03-beyond-the-mainframe",
  title: "Beyond the Mainframe",
  // 26 Oct 2026 09:00 London == 09:00 UTC, because BST ended on the 25th.
  startsAtUtc: "2026-10-26T09:00:00Z",
  endsAtUtc: "2026-10-30T17:00:00Z",
  // The judged artefact is whatever is on main at this instant. Published as
  // "16:00 GMT" so nobody converts it from the wrong zone.
  submissionDeadlineUtc: "2026-10-30T16:00:00Z",
} as const;

const LONDON = "Europe/London";

export interface Remaining {
  totalMs: number;
  days: number;
  hours: number;
  minutes: number;
  seconds: number;
  past: boolean;
}

export function remainingUntil(targetUtc: string, now: Date = new Date()): Remaining {
  const total = Date.parse(targetUtc) - now.getTime();
  const past = total <= 0;
  const abs = Math.abs(total);
  return {
    totalMs: total,
    days: Math.floor(abs / 86_400_000),
    hours: Math.floor((abs % 86_400_000) / 3_600_000),
    minutes: Math.floor((abs % 3_600_000) / 60_000),
    seconds: Math.floor((abs % 60_000) / 1000),
    past,
  };
}

/**
 * Render an instant in London time, with the zone abbreviation attached.
 *
 * The abbreviation is included deliberately: "30 October, 16:00" is ambiguous to
 * anyone not standing in the UK, and this deadline decides what gets judged.
 */
export function inLondon(utcIso: string): string {
  const d = new Date(utcIso);
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: LONDON,
    weekday: "long",
    day: "numeric",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(d);
  return parts;
}

/** "GMT" or "BST" for a given instant — derived, never assumed. */
export function londonZoneAbbr(utcIso: string): string {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: LONDON,
    timeZoneName: "short",
  }).formatToParts(new Date(utcIso));
  return parts.find((p) => p.type === "timeZoneName")?.value ?? "";
}

export function isDuringEvent(now: Date = new Date()): boolean {
  const t = now.getTime();
  return t >= Date.parse(EVENT.startsAtUtc) && t <= Date.parse(EVENT.endsAtUtc);
}
