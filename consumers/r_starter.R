# R starter — arrow reads parquet directly, including over HTTPS.
#
#   install.packages(c("arrow", "dplyr", "jsonlite"))
#   Rscript consumers/r_starter.R

library(arrow)
library(dplyr)
library(jsonlite)

challenge <- "c03-beyond-the-mainframe"
version   <- "v2026-10-26"
published <- FALSE

# Pinned, not "latest" — judging is against an immutable tag.
base <- if (published) {
  sprintf("https://data.inno-forum.co.uk/%s/%s", challenge, version)
} else {
  sprintf("sample/data/%s", challenge)
}

# Read the contract first. It carries column MEANINGS, not just types.
manifest <- fromJSON(file.path(base, "manifest.json"))
cat(manifest$title, "\n\n")
for (i in seq_len(nrow(manifest$tables))) {
  t <- manifest$tables[i, ]
  cat(sprintf("  %-28s ~%s rows   %s\n", t$name, format(t$approx_rows, big.mark = ","), t$grain))
  if (grepl("SYNTHETIC", toupper(t$description))) {
    cat("      ^ SYNTHETIC — not a measurement\n")
  }
}

cost <- read_parquet(file.path(base, "gold", "workload_cost_daily.parquet"))

# Confirm the grain before aggregating.
cat(sprintf("\nrows %s · duplicate keys %s\n",
            format(nrow(cost), big.mark = ","),
            sum(duplicated(cost[c("workload_id", "usage_date")]))))

cost %>%
  group_by(platform) %>%
  summarise(cost_gbp = sum(cost_gbp),
            cost_per_vcpu_hr = sum(cost_gbp) / sum(vcpu_hours),
            mean_util_pct = mean(utilisation_pct)) %>%
  arrange(desc(cost_per_vcpu_hr)) %>%
  print()
