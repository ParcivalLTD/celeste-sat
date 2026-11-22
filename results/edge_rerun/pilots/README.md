# Pilot runs of the W = 12 edge re-check

Two trial runs of `.github/workflows/edge-windows.yml` on the `lvl_6b` windows
K = 0 and 1, before the full run 39244071132 whose results are in
`results/edge_rerun/w12/` and `w12_all.json`.

- `run-39238480657`: the first pilot; CBMC exited with status 1 (see `run.log`).
- `run-39239480316`: the second pilot; both windows proven, about 6.9 GB per
  query. The full run covers the same windows again in `w12/lvl_6b_k0-5`.

Kept for the record only; nothing in the results depends on them.
