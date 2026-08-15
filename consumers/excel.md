# Excel

**Excel cannot read parquet.** Use the CSV twin.

```
https://data.inno-forum.co.uk/<challenge>/<version>/gold/<table>.csv
```

## Do not double-click the file

Open it through **Data → From Text/CSV**, not by double-clicking. The import dialog
lets you confirm the encoding and column types; double-clicking guesses, and its
guesses are the problem.

The twins are written **UTF-8 with a BOM** specifically so Excel detects the encoding
instead of reading it as Windows-1252 and mangling every accented place name. Dates
are **ISO-8601** so `03/04` cannot be silently read as 3 April here and 4 March in a
US locale. Both failures are quiet — the file opens, the dates parse, they are just
wrong — so nothing warns you.

If a date column arrives as text, set it to **Date (YMD)** in the import dialog
rather than reformatting afterwards.

## Tables too large for a worksheet

Excel stops at 1,048,576 rows, and several tables are larger. Those ship a
**sample** instead of a full twin — check `manifest.json` for `csv_sample`.

A sample is fine for understanding the shape and prototyping a calculation. It is
**not** fine for a headline number: `lsoa_crime_monthly` is 2.4M rows and a
1,000-row sample of it will not total to anything meaningful. If you need the whole
table, use DuckDB or Power Query — both are free.

## Power Query is the better route

**Data → Get Data → From Other Sources → From Web**, paste the CSV URL. It refreshes,
it keeps the type mapping, and it will not silently truncate. It also handles files
larger than a worksheet by loading to the Data Model rather than to cells.
