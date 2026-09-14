# Data Archiving Rules

## Table of contents
1. Copy-never-move
2. SHA256 manifest
3. Manifest maintenance cycle
4. CSV encoding
5. Version naming

## 1. Copy, never move

- Original downloaded/raw data files are immutable. Work copies are made; derived files get new names.
- Never overwrite an old version by filename alone: new versions carry date/version suffix (`_V1_20260914.csv`).
- Read-only sources (authoritative input panels, frozen datasets) are marked READ_ONLY_SOURCE in the protocol; stage code reads them and writes outputs to stage directories only.

## 2. SHA256 manifest

One manifest per data folder: `00_说明与清单/文件清单_SHA256.csv`

Columns:

```csv
"relative_path","source_path","bytes","modified_time","sha256","source_check"
```

- `relative_path`: path relative to the data folder root
- `source_path`: where the file first came from (original source or parent derived file)
- `source_check`: `VERIFIED` (original archived), `DERIVED` (computed), `REHASHED_AFTER_REVIEW` (content edited after initial archiving), `FORMAL_AGGREGATED_GATE_OPEN` (final canonical table)

## 3. Manifest maintenance cycle

After ANY batch of file work (create/edit/move):

1. List all files on disk in the data folder.
2. Diff against manifest rows.
3. For each disk file:
   - in manifest AND unchanged → keep
   - in manifest AND content changed → re-hash, update row, mark `REHASHED_AFTER_REVIEW`
   - not in manifest → append row
4. For each manifest row with missing disk file → flag (do not silently delete the row; log it).
5. Final verification: re-hash EVERY manifest row vs disk and report `ok / mismatch / missing`. Target: 100% ok.

The final verification step is the point of the exercise — "did everything get recorded" questions get answered by running it, not by memory.

## 4. CSV encoding (Excel compatibility)

- Generated CSVs: **UTF-8 with BOM** (EF BB BF). Excel on Chinese Windows misreads BOM-less UTF-8 as GBK → mojibake.
- Verify with the first 3 bytes after writing.
- PowerShell 5.1 note: `Export-Csv -Encoding UTF8` sometimes writes no BOM — verify and rewrite via .NET `[System.IO.File]::WriteAllText(path, text, New-Object System.Text.UTF8Encoding($true))` if needed.

## 5. Version naming

- Pattern: `descriptive_name_版本号_YYYYMMDD.ext` (e.g., `省级政策设计支持度省年表_正式聚合_V1_20260914.csv`)
- Human-facing explanation files pair with derived data files and carry the same date.
- Historical drafts go to a quarantine folder (`_历史稿归档/`) with `[!WARNING]` header marking them non-current; protocol points to them as history, never as current authority.
