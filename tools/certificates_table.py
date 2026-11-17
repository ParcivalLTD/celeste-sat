#!/usr/bin/env python3
"""
certificates_table.py -- summarise a results file of tools/certify.py as Markdown.

    tools/certificates_table.py results/certificates/ledge_w8.json
"""
import json
import sys


def main():
    for path in sys.argv[1:]:
        with open(path) as f:
            d = json.load(f)
        rows = [r for r in d["windows"] if "disagreement" not in r]
        bad = [r for r in d["windows"] if "disagreement" in r]
        cert = [r for r in rows if r["certified"]]
        print(f"**{d['room']}**, route `{d['route']}` (leaves on frame {d['exit']}), W = {d['width']}: "
              f"**{len(cert)} of {len(rows)} windows certified**"
              + (f", {len(bad)} disagreements" if bad else "") + ".\n")
        print("| K | frames | variables | clauses | CBMC | CaDiCaL | s | proof MB | drat-trim | s |")
        print("|---|---|---|---|---|---|---|---|---|---|")
        for r in rows:
            print(f"| {r['k']} | {r['frames'][0]}–{r['frames'][1]} | {r.get('variables', 0):,} | "
                  f"{r.get('clauses', 0):,} | {r.get('cbmc', '–')} ({r.get('cbmc_seconds', 0):.0f} s) | "
                  f"{r['solver']} | {r.get('solver_seconds', 0):.0f} | "
                  f"{r.get('proof_bytes', 0) / 1e6:,.0f} | {r.get('checker', '–')} | {r.get('checker_seconds', 0):.0f} |")
        tot = lambda key: sum(r.get(key, 0) for r in rows)  # noqa: E731
        print(f"\nTime per step, summed over the windows: CBMC {tot('cbmc_seconds') / 60:.0f} min, CNF export {tot('cnf_seconds') / 60:.0f} min, "
              f"CaDiCaL {tot('solver_seconds') / 60:.0f} min, drat-trim {tot('checker_seconds') / 60:.0f} min; "
              f"proofs {tot('proof_bytes') / 1e9:.1f} GB in all (checked, then deleted).")
        print(f"Tools: {d['versions']['cbmc']}; CaDiCaL {d['versions']['cadical']}; drat-trim {d['versions']['drat-trim']}.\n")


if __name__ == "__main__":
    main()
