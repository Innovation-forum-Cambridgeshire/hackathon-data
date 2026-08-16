"""Run the assurance suite over the built corpus.

    python quality/run_assurance.py --data-root sample/data

The corpus is generated, not committed (see sample/.gitignore), so this needs a
built data root. In CI that is whatever `build.py build --out` produced; locally
it is sample/data after `sample/setup.sh`.

WHAT IT DOES, IN ORDER
    1. load the catalogue, contract, defect and relationship configs, cross-checked
    2. read each gold table, add the derived columns the checks need
    3. validate the contract suite   — must pass
    4. validate the defect suite     — must also pass, by failing to be clean
    5. reconcile every CSV twin against its parquet
    6. profile every column and diff against the committed baseline
    7. build branded Data Docs, the architecture diagrams and the assessment

EXIT CODE
    0  contract holds, deliberate defects intact, no structural drift
    1  something in that list is not true

`--allow-known-findings` keeps the exit code at 0 for findings already recorded
in quality/FINDINGS.md. That flag exists so a known, triaged, unfixed defect does
not block every unrelated PR — and it is deliberately explicit, so nobody can
turn a red build green without saying so in the diff.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

import great_expectations as gx
from great_expectations.checkpoint import Checkpoint, UpdateDataDocsAction

from . import metrics as metrics_mod
from . import profile as profile_mod
from . import reconcile as reconcile_mod
from . import suites as suites_mod
from .model import Spec, Table, load_spec

import yaml


@dataclass
class TableResult:
    table: Table
    contract_success: bool = True
    defect_success: bool = True
    expectations: int = 0
    failures: list[dict[str, Any]] = field(default_factory=list)
    row_count: int = 0
    drifts: list = field(default_factory=list)


@dataclass
class RunResult:
    started: str
    data_root: str
    tables: list[TableResult] = field(default_factory=list)
    metrics: list = field(default_factory=list)
    metric_failures: list[dict[str, Any]] = field(default_factory=list)
    reconciliation: pd.DataFrame | None = None
    reconciliation_success: bool = True
    brand_drift: list[str] = field(default_factory=list)
    docs_url: str | None = None
    blocked_tables: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def structural_drift(self) -> list:
        return [d for t in self.tables for d in t.drifts if d.is_failure]

    @property
    def material_drift(self) -> list:
        return [d for t in self.tables for d in t.drifts if d.level == "material"]

    @property
    def success(self) -> bool:
        return (
            all(t.contract_success and t.defect_success for t in self.tables)
            and self.reconciliation_success
            and not self.metric_failures
            and not self.structural_drift
        )


def _collect_failures(validation_result, index_columns: list[str]) -> list[dict[str, Any]]:
    """Pull the failing expectations, with their top ten affected rows."""
    out = []
    for r in validation_result.results:
        if r.success:
            continue
        cfg = r.expectation_config
        res = r.result or {}
        out.append(
            {
                "type": cfg.type,
                "description": cfg.description or cfg.type,
                "notes": cfg.notes or "",
                "column": (cfg.kwargs or {}).get("column"),
                "dimension": (cfg.meta or {}).get("dimension", ""),
                "severity": (cfg.meta or {}).get("severity", ""),
                "defect_id": (cfg.meta or {}).get("defect_id", ""),
                "unexpected_count": res.get("unexpected_count"),
                "unexpected_percent": res.get("unexpected_percent"),
                "element_count": res.get("element_count"),
                "partial_unexpected_list": res.get("partial_unexpected_list", [])[:10],
                "top_10_affected_rows": res.get("partial_unexpected_index_list", [])[:10],
                "index_columns": index_columns,
                "observed_value": res.get("observed_value"),
                "exception": (r.exception_info or {}).get("exception_message"),
            }
        )
    return out


def run(
    repo_root: Path,
    data_root: Path,
    out_dir: Path,
    update_baseline: bool = False,
    website_css: Path | None = None,
    progress_bars: bool = False,
) -> RunResult:
    spec = load_spec(repo_root)
    contract_cfg = yaml.safe_load(
        (repo_root / "quality" / "config" / "contract.yml").read_text(encoding="utf-8")
    ).get("challenges", {})

    out_dir.mkdir(parents=True, exist_ok=True)
    gx_root = out_dir / "gx"
    gx_root.mkdir(parents=True, exist_ok=True)

    context = gx.get_context(mode="file", project_root_dir=str(gx_root))
    # One tqdm bar per metric, and there are thousands. In a terminal it is
    # noise; piped to a CI log it is tens of megabytes of carriage returns that
    # bury the one line anybody wanted. Off unless asked for.
    context.variables.progress_bars = {"globally": progress_bars}
    _install_branding(gx_root)

    # TWO DATASOURCES, BOTH PATH-BASED, AND THE REASON MATTERS.
    #
    # A dataframe asset needs its dataframe handed in at run time, via
    # Checkpoint.run(batch_parameters=...). That parameter is global to the
    # checkpoint, so a checkpoint over dataframe assets can only ever validate
    # ONE table — which is why this used to run forty separate checkpoints and
    # produce forty separate entries in Data Docs.
    #
    # A path-based asset carries its own data. Every batch becomes self-contained,
    # so a single master checkpoint can hold every validation definition and run
    # the whole programme in one pass, producing one report.
    #
    #   source    reads the corpus exactly as built — used by the schema suites,
    #             which must see the table before any derived column is added.
    #   prepared  the augmented frames written out below, carrying the foreign-key
    #             resolution flags and computed residuals the contract suites need.
    #
    # Splitting them means the raw tables are never copied: only the augmented
    # ones are written, and the schema checks read the originals in place.
    prepared_dir = out_dir / "prepared"
    prepared_dir.mkdir(parents=True, exist_ok=True)
    ds_source = _filesystem_source(context, "corpus-as-built", data_root)
    ds_prepared = _filesystem_source(context, "corpus-prepared", prepared_dir)

    # suite name -> (TableResult or None, which flag its outcome sets)
    suite_owner: dict[str, tuple[Any, str]] = {}
    validation_defs: list[Any] = []

    result = RunResult(
        started=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        data_root=str(data_root),
    )

    from . import brand

    if website_css:
        result.brand_drift = brand.verify_brand(website_css)

    baseline_dir = repo_root / "quality" / "baseline"
    recon_rows: list[dict[str, Any]] = []

    for challenge in spec.challenges:
        print(f"\n{challenge.slug}", flush=True)
        for tname, reason in challenge.blocked_tables:
            result.blocked_tables.append((challenge.slug, tname, reason))

        frames: dict[str, pd.DataFrame] = {}
        for table in challenge.tables:
            path = table.parquet_path(data_root)
            if not path.exists():
                print(f"  ! {table.key}: parquet not found at {path}", file=sys.stderr)
                continue
            frames[table.name] = pd.read_parquet(path)
            print(f"  read {table.name} ({len(frames[table.name]):,} rows)", flush=True)

        if not frames:
            print(f"  ! {challenge.slug}: no data found, skipped", file=sys.stderr)
            continue

        # The schema suite has to see the table as it was READ. Snapshot the
        # column lists before anything is added, so an extra column in the
        # parquet is still detectable after the derived ones go on.
        raw_columns = {name: list(f.columns) for name, f in frames.items()}

        # Derived columns must exist before any suite is built against them.
        fk_by_table = suites_mod.add_referential_columns(frames, challenge.relationships)

        c_contract = contract_cfg.get(challenge.slug, {}) or {}

        for table in challenge.tables:
            if table.name not in frames:
                continue
            df = frames[table.name]
            cfg = c_contract.get(table.name, {}) or {}
            tr = TableResult(table=table, row_count=len(df))

            derived = suites_mod.add_contract_columns(df, cfg)

            schema_suite = suites_mod.build_schema_suite(table)
            contract_suite = suites_mod.build_contract_suite(
                table, cfg, df, fk_by_table.get(table.name, []), derived
            )
            defect_suite = suites_mod.build_defect_suite(table, df)

            # The augmented frame goes to disk so its batch is self-contained.
            prepared = prepared_dir / f"{table.challenge}__{table.name}.parquet"
            df.to_parquet(prepared, index=False)

            # Same asset name on both datasources — they are different sources,
            # so the names do not collide, and the report should say which TABLE
            # a result is about, not which staging file it happened to read.
            # The datasource name (corpus-as-built / corpus-prepared) already
            # carries that distinction in the batch id for anyone who needs it.
            asset_name = f"{table.challenge}__{table.name}"
            source_rel = f"{table.challenge}/gold/{table.name}.parquet"
            schema_batch = _batch(ds_source, asset_name, source_rel)
            data_batch = _batch(ds_prepared, asset_name, prepared.name)

            # (suite, batch it validates, which flag its outcome sets)
            for suite, batch, flag in (
                (schema_suite, schema_batch, "contract"),
                (contract_suite, data_batch, "contract"),
                (defect_suite, data_batch, "defects"),
            ):
                if suite is None:
                    continue
                context.suites.add_or_update(suite)
                validation_defs.append(
                    context.validation_definitions.add_or_update(
                        gx.ValidationDefinition(name=suite.name, data=batch, suite=suite)
                    )
                )
                # Schema and contract both roll up into "the contract holds"; they
                # are separate suites only so the schema check can see the table
                # before the derived columns go on.
                suite_owner[suite.name] = (tr, flag)
                tr.expectations += len(suite.expectations)

            print(f"    prepared {table.name} ({len(df):,} rows, "
                  f"{len(df.columns)} cols incl. derived)", flush=True)

            # --- profile and drift ---------------------------------------
            prof = profile_mod.profile_frame(df, table.column_names)
            bpath = baseline_dir / f"{table.challenge}.{table.name}.json"
            baseline = profile_mod.load_baseline(bpath)
            if baseline is None or update_baseline:
                profile_mod.write_baseline(bpath, prof)
                if baseline is None:
                    print(f"    baseline written for {table.key}")
            else:
                tr.drifts = profile_mod.compare(table.key, baseline, prof)

            (out_dir / "profiles").mkdir(parents=True, exist_ok=True)
            (out_dir / "profiles" / f"{table.challenge}.{table.name}.json").write_text(
                json.dumps(prof, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )

            result.tables.append(tr)

            # --- CSV twin -------------------------------------------------
            if table.csv_twin:
                recon_rows.append(
                    reconcile_mod.reconcile_table(
                        table.name,
                        table.challenge,
                        table.parquet_path(data_root),
                        table.csv_path(data_root),
                        table.column_names,
                    )
                )

        # --- derived defect metrics for this challenge --------------------
        defect_tables = {t.name: t.defects for t in challenge.tables if t.defects}
        challenge_metrics = metrics_mod.compute_all(challenge.slug, defect_tables, frames)
        if challenge_metrics:
            result.metrics.extend(challenge_metrics)
            msuite = suites_mod.build_metric_suite(challenge.slug, challenge_metrics)
            mpath = prepared_dir / f"{challenge.slug}__derived_metrics.parquet"
            metrics_mod.to_frame(challenge_metrics).to_parquet(mpath, index=False)
            context.suites.add_or_update(msuite)
            validation_defs.append(
                context.validation_definitions.add_or_update(
                    gx.ValidationDefinition(
                        name=msuite.name,
                        data=_batch(ds_prepared, f"{challenge.slug}__derived_metrics", mpath.name),
                        suite=msuite,
                    )
                )
            )
            suite_owner[msuite.name] = (None, "metrics")

    # --- CSV twin reconciliation, all tables at once ----------------------
    if recon_rows:
        rframe = pd.DataFrame(recon_rows)
        result.reconciliation = rframe
        # Tables with no CSV twin present are excluded rather than failed: the
        # catalogue marks some csv_twin: false on purpose.
        checkable = rframe[rframe["csv_present"]]
        if len(checkable):
            rsuite = reconcile_mod.build_suite(checkable)
            rpath = prepared_dir / "programme__csv_twins.parquet"
            checkable.to_parquet(rpath, index=False)
            context.suites.add_or_update(rsuite)
            validation_defs.append(
                context.validation_definitions.add_or_update(
                    gx.ValidationDefinition(
                        name=rsuite.name,
                        data=_batch(ds_prepared, "programme__csv_twins", rpath.name),
                        suite=rsuite,
                    )
                )
            )
            suite_owner[rsuite.name] = (None, "reconciliation")

    # ======================================================================
    # ONE CHECKPOINT, EVERY BATCH.
    #
    # Each validation definition carries its own batch, so this runs the whole
    # programme in a single pass and writes a single entry into Data Docs
    # covering all of it — rather than the forty separate runs this produced when
    # every suite had its own checkpoint. The Data Docs index then reads as one
    # report of the corpus, which is what it is.
    #
    # No result_format here on purpose: a checkpoint carries exactly one, and
    # these batches have thirteen different business keys between them. Each
    # expectation was stamped with its own in suites.adder().
    # ======================================================================
    print(f"\nmaster checkpoint: {len(validation_defs)} batches", flush=True)
    t0 = time.monotonic()
    master = context.checkpoints.add_or_update(
        Checkpoint(
            name="programme.master-assurance",
            validation_definitions=validation_defs,
            actions=[UpdateDataDocsAction(name="update_data_docs")],
        )
    )
    cp_result = master.run()
    print(f"  ran in {time.monotonic() - t0:.1f}s — "
          f"{'all green' if cp_result.success else 'findings present'}", flush=True)

    # Distribute the results back to the tables that own them.
    for vr in cp_result.run_results.values():
        owner, flag = suite_owner.get(vr.suite_name, (None, "unknown"))
        failures = _collect_failures(vr, owner.table.index_columns if owner else [])
        if flag == "metrics":
            result.metric_failures.extend(failures)
        elif flag == "reconciliation":
            result.reconciliation_success = vr.success
        elif owner is not None:
            owner.failures.extend(failures)
            if flag == "contract":
                owner.contract_success = owner.contract_success and vr.success
            else:
                owner.defect_success = owner.defect_success and vr.success
        label = "ok  " if vr.success else "FAIL"
        print(f"  {label} {len(vr.results):3d}  {vr.suite_name}", flush=True)

    urls = context.get_docs_sites_urls()
    if urls:
        result.docs_url = urls[0]["site_url"]

    return result


def _filesystem_source(context, name: str, base_directory: Path):
    """A path-based pandas datasource, tolerant of already existing."""
    try:
        return context.data_sources.add_pandas_filesystem(
            name, base_directory=base_directory
        )
    except Exception:
        return context.data_sources.get(name)


def _batch(datasource, asset_name: str, relative_path: str):
    """One parquet file as a self-contained batch."""
    try:
        asset = datasource.add_parquet_asset(asset_name)
    except Exception:
        asset = datasource.get_asset(asset_name)
    try:
        return asset.add_batch_definition_path(f"{asset_name}__batch", relative_path)
    except Exception:
        return asset.get_batch_definition(f"{asset_name}__batch")


def _install_branding(gx_root: Path) -> None:
    """Write the brand stylesheet where GX's SiteBuilder will find it."""
    from . import brand

    styles = gx_root / "gx" / "plugins" / "custom_data_docs" / "styles"
    styles.mkdir(parents=True, exist_ok=True)
    (styles / "data_docs_custom_styles.css").write_text(brand.data_docs_css(), encoding="utf-8")
