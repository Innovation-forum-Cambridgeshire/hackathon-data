// Timezone assertions for the event window. Run: node src/lib/countdown.test.mjs
//
// The BST->GMT change lands on Sunday 25 October 2026, the day before the event.
// These assertions exist because that off-by-one-hour is invisible in testing
// done in August and only appears in the week that matters.
const LONDON = "Europe/London";
const fails = [];
const check = (label, got, want) => {
  if (got !== want) fails.push(`${label}\n      got:  ${got}\n      want: ${want}`);
};
const fmt = (iso) =>
  new Intl.DateTimeFormat("en-GB", {
    timeZone: LONDON, day: "numeric", month: "short",
    hour: "2-digit", minute: "2-digit", timeZoneName: "short",
  }).format(new Date(iso));

// The deadline must render as 16:00 GMT, not 17:00 BST.
check("submission deadline", fmt("2026-10-30T16:00:00Z"), "30 Oct, 16:00 GMT");
// Event start, also GMT.
check("event start", fmt("2026-10-26T09:00:00Z"), "26 Oct, 09:00 GMT");
// The day before the clocks change is still BST — proves the formatter is
// applying the offset for the DATE rather than a fixed offset.
check("day before the change", fmt("2026-10-24T12:00:00Z"), "24 Oct, 13:00 BST");
// And the day after is GMT.
check("day after the change", fmt("2026-10-26T12:00:00Z"), "26 Oct, 12:00 GMT");

if (fails.length) {
  console.error("Countdown timezone FAILED:");
  for (const f of fails) console.error("  - " + f);
  process.exit(1);
}
console.log(
  "Countdown timezone OK: deadline renders 16:00 GMT; BST correctly applies before 25 Oct and GMT after."
);
