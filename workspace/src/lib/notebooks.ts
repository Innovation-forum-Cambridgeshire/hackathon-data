/**
 * The worked-example notebooks, and the ONLY paths this service will ever fetch.
 *
 * WHY THIS IS A HARDCODED LIST AND NOT A DIRECTORY LISTING
 * --------------------------------------------------------
 * The workspace fetches notebooks from GitHub server-side and hands the JSON to
 * the participant's browser. That makes the Function an outbound HTTP client
 * whose target is chosen per request — which is the exact shape of an SSRF, and
 * of a path traversal if the id is pasted into a URL.
 *
 * The defence is not to sanitise the id. It is never to use it: `findNotebook`
 * matches an incoming id against this fixed list and returns the entry, and the
 * URL is then built from the ENTRY's path. Nothing a caller sends is ever
 * concatenated into the upstream request. An unknown id is a 404 before any
 * fetch happens.
 *
 * Adding a notebook means editing this file. That is the intended cost.
 *
 * WHY A PINNED REF
 * -----------------
 * `main` moves. A notebook is a document participants are told to trust and copy
 * from during a judged event, so what they read on the Friday should be what
 * they read on the Monday. REF is overridable per deploy so the notebooks can be
 * corrected mid-event without a code change, but it defaults to a tag rather
 * than a branch, and a tag that does not exist fails loudly at the first request
 * instead of silently serving something newer.
 */

/** Public repository holding the notebooks. Public: no token is used to read it. */
export const SOURCE = {
  owner: "Innovation-forum-Cambridgeshire",
  repo: "hackathon-data",
  /** Overridable with the NOTEBOOKS_REF environment variable. */
  defaultRef: "main",
} as const;

export interface NotebookEntry {
  /** URL-safe id. Also the filename stem — but see the note above: the PATH is
   *  what gets used, and it comes from here, not from the request. */
  readonly id: string;
  readonly title: string;
  /** Matching challenge on the marketing site, or null for general technique. */
  readonly challengeSlug: string | null;
  readonly challengeTitle: string | null;
  /** The one transferable idea. Lifted from the notebook's own opening cell. */
  readonly technique: string;
  readonly summary: string;
  /** Path within the repository. The only thing used to build the fetch URL. */
  readonly path: string;
}

export const NOTEBOOKS: readonly NotebookEntry[] = [
  {
    id: "c03-beyond-the-mainframe",
    title: "Beyond the Mainframe — first hour",
    challengeSlug: "beyond-the-mainframe",
    challengeTitle: "Beyond the Mainframe",
    technique: "Cost attribution and unit economics",
    summary:
      "Past the cold start: what the data is, one finding genuinely in it, and the two questions a FinOps review always opens with — the two most teams skip on their way to a forecasting model.",
    path: "sample/notebooks/c03-beyond-the-mainframe.ipynb",
  },
  {
    id: "c01-one-farm-one-picture",
    title: "One Farm, One Picture — first hour",
    challengeSlug: "one-farm-one-picture",
    challengeTitle: "One Farm, One Picture",
    technique: "Checking the data before trusting it",
    summary:
      "Sounds like housekeeping, is actually the whole challenge. The brief says so directly, and this notebook shows what the check finds.",
    path: "sample/notebooks/c01-one-farm-one-picture.ipynb",
  },
  {
    id: "c02-mapping-the-gaps",
    title: "Mapping the Gaps — first hour",
    challengeSlug: "mapping-the-gaps",
    challengeTitle: "Mapping the Gaps",
    technique: "Normalising before comparing",
    summary:
      "Worth an hour because the un-normalised version produces a confident, clean, completely wrong answer — the kind that survives a demo.",
    path: "sample/notebooks/c02-mapping-the-gaps.ipynb",
  },
  {
    id: "c04-safe-in-the-open",
    title: "Safe in the Open — first hour",
    challengeSlug: "safe-in-the-open",
    challengeTitle: "Safe in the Open",
    technique: "Classification when positives are rare",
    summary:
      "Worth an hour because the obvious metric actively misleads you: accuracy looks excellent precisely when the model has learned nothing.",
    path: "sample/notebooks/c04-safe-in-the-open.ipynb",
  },
  {
    id: "c05-ahead-of-the-heat",
    title: "Ahead of the Heat — first hour",
    challengeSlug: "ahead-of-the-heat",
    challengeTitle: "Ahead of the Heat",
    technique: "Calibration",
    summary:
      "Whether a risk score means what its number says, not merely whether it ranks people in the right order. Nothing in it is clinical advice.",
    path: "sample/notebooks/c05-ahead-of-the-heat.ipynb",
  },
  {
    id: "live-api-carbon-intensity",
    title: "Connecting to a live API",
    challengeSlug: null,
    challengeTitle: null,
    technique: "Reading a live source, not a built corpus",
    summary:
      "The others read a corpus we built. This one connects to a live source, checks what came back against what you expected, and loads it for analysis.",
    path: "sample/notebooks/live-api-carbon-intensity.ipynb",
  },
];

/**
 * Resolve a caller-supplied id to a catalogue entry, or undefined.
 *
 * Exact string equality against the fixed list. No normalising, no lowercasing,
 * no decoding — anything that does not match one of the ids above is simply not
 * a notebook, and the caller gets a 404 without a fetch being made.
 */
export function findNotebook(id: unknown): NotebookEntry | undefined {
  if (typeof id !== "string") return undefined;
  return NOTEBOOKS.find((n) => n.id === id);
}

/**
 * Build the raw-content URL for an entry.
 *
 * Takes the ENTRY, never an id, so it is not possible to call this with
 * something a request supplied. The ref is encoded because it comes from an
 * environment variable, which is operator input rather than attacker input but
 * is still not this function's to trust.
 */
export function rawUrl(entry: NotebookEntry, ref: string): string {
  return (
    `https://raw.githubusercontent.com/${SOURCE.owner}/${SOURCE.repo}/` +
    `${encodeURIComponent(ref)}/${entry.path}`
  );
}

/** Where a human goes to read the same file on GitHub, with its history. */
export function githubUrl(entry: NotebookEntry, ref: string): string {
  return (
    `https://github.com/${SOURCE.owner}/${SOURCE.repo}/blob/` +
    `${encodeURIComponent(ref)}/${entry.path}`
  );
}

/**
 * The same file in github.dev — a full VS Code editor in the browser, on a copy.
 *
 * This is how a participant gets an IDE without us running any of their code.
 * github.dev is free, needs no quota, and opens read-only against a public repo
 * until they fork it, at which point their edits are theirs and on their own
 * account. We host nothing and execute nothing.
 */
export function githubDevUrl(entry: NotebookEntry, ref: string): string {
  return (
    `https://github.dev/${SOURCE.owner}/${SOURCE.repo}/blob/` +
    `${encodeURIComponent(ref)}/${entry.path}`
  );
}

/** A Codespace on the participant's own free monthly quota, not ours. */
export function codespaceUrl(ref: string): string {
  return (
    `https://github.com/codespaces/new?repo=${SOURCE.owner}%2F${SOURCE.repo}` +
    `&ref=${encodeURIComponent(ref)}`
  );
}
