"""Builds docs/design/milestones/ENTITLEMENT_DECISIONS.md.

Every excerpt is copied line for line from its source file by this script
(never retyped): the tier-revision review package, the handover Coverage Pack
(read straight out of the archive) and repository records. The script fails if
an expected line is missing or ambiguous.

    python build_decisions_doc.py <worktree> <package.md> <handover.zip>
"""
from __future__ import annotations

import hashlib
import pathlib
import sys
import zipfile

root = pathlib.Path(sys.argv[1])
package = pathlib.Path(sys.argv[2])
archive = pathlib.Path(sys.argv[3])
READ_ON = "2026-11-27"

pkg_bytes = package.read_bytes()
pkg = pkg_bytes.decode("utf-8").splitlines()
with zipfile.ZipFile(archive) as z:
    cov_bytes = z.read("handover-tier-revision/COVERAGE.md")
cov = cov_bytes.decode("utf-8").splitlines()


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def one(lines: list[str], prefix: str) -> tuple[int, str]:
    hits = [(i + 1, l) for i, l in enumerate(lines) if l.startswith(prefix)]
    assert len(hits) == 1, (prefix, len(hits))
    return hits[0]


def span(lines: list[str], start_prefix: str, end_prefix: str) -> tuple[int, int, list[str]]:
    a, _ = one(lines, start_prefix)
    b, _ = one(lines, end_prefix)
    assert b >= a
    return a, b, lines[a - 1:b]


def rows(lines: list[str], lo: int, hi: int, prefixes: list[str]) -> list[tuple[int, str]]:
    out = []
    for p in prefixes:
        hits = [(i, lines[i - 1]) for i in range(lo, hi + 1) if lines[i - 1].startswith(p)]
        assert len(hits) == 1, (p, len(hits))
        out.append(hits[0])
    return out


out: list[str] = []
w = out.append

w("# Entitlement decisions — excerpts and where each stands (record of 2026-11-27)")
w("")
w("**What this file is.** A transcription, made so that the decisions the Playground tier-revision work relies on are readable inside the repository. Until now the approvals of 2026-11-02 and the proposals of 2026-11-03 existed only in a review package held outside it. This file changes nothing: it records, it does not decide.")
w("")
w("**How it was made.** Every excerpt below was copied line for line from its source file by a script, not retyped, and each carries the source's line numbers. Nothing is quoted from memory or from a summary. The commentary sections (§1, §7 and §8) are analysis written for the M8-R plan and are marked as such.")
w("")
w("**What it does not establish.** The review package *reports* the owner's approvals; it is not the owner's own message. If any entry here differs from what was decided, the owner's correction governs and this file is amended.")
w("")
w("| Source | Identity | SHA-256 | Read |")
w("|---|---|---|---|")
w(f"| Tier-revision review package | v3.9, dated 2026-11-03 in its status line; file `{package.name}`, held outside the repository | `{sha(pkg_bytes)}` | {READ_ON} |")
w(f"| Design handover, Coverage Pack | `handover-tier-revision/COVERAGE.md`, dated 28 October 2026 in its opening lines; inside the handover archive `{archive.name}` (archive SHA-256 `{sha(archive.read_bytes())}`), held outside the repository | `{sha(cov_bytes)}` | {READ_ON} |")
w("| Repository records | the files named in §5, at the commit that adds this file | — | — |")
w("")

# ── 1. status summary (analysis) ────────────────────────────────────────────
w("## 1. Status at a glance (analysis; the excerpts in §2–§6 are the authority)")
w("")
w("| Decision | Status | Excerpt |")
w("|---|---|---|")
for d, s, e in [
    ("5-4 paid→Free", "approved 2026-11-02", "§2"),
    ("5-6a existing personal material", "approved 2026-11-02", "§2"),
    ("5-6b existing Free holders at create / edit activation", "deferred 2026-11-02 — blocks full activation", "§2"),
    ("5-9a ledger storage; 5-19 consume timing; 5-21 mapping; 5-22 activation flag", "approved 2026-11-02", "§2"),
    ("5-23 month boundary under `choices`", "approved 2026-11-02", "§2"),
    ("5-20 transition table", "unresolved; a proposal exists (§3)", "§2, §3"),
    ("5-13 rollback window and triggers", "unresolved", "§2"),
    ("5-1 prices", "unresolved; one part decided 2026-11-06 and 2026-11-07", "§4, §5"),
    ("5-2 upgrade timing; 5-3 cancellation, downgrade, grace", "register recommendations only", "§4"),
    ("5-7 Max access policy; 5-10 Free device policy; 5-12; 5-14; 5-15", "register recommendations only; applied parts are in §5", "§4, §5"),
    ("5-24 partial refunds and open disputes", "gap; interim behaviour stated", "§4"),
]:
    w(f"| {d} | {s} | {e} |")
w("")

# ── 2. §5.4 ────────────────────────────────────────────────────────────────
a, b, body = span(pkg, "### 5.4 Decision table", "Not required for B1:")
w("## 2. Review package §5.4 — decision table after the approvals of 2026-11-02")
w("")
w(f"Verbatim, package lines {a}–{b}.")
w("")
out.extend(body)
w("")

# ── 3. §5.5.1 proposed table ───────────────────────────────────────────────
h, hl = one(pkg, "### 5.5 The two unresolved decisions")
a, b, body = span(pkg, "**Proposed table (decision 5-20;", "**You decide (5-20):**")
w("## 3. Review package §5.5.1 — the 5-20 transition table. **PROPOSED; nothing in it is approved**")
w("")
w(f"Section heading, verbatim, package line {h}:")
w("")
w("> " + hl.lstrip("# "))
w("")
w(f"Table and the decision it asks for, verbatim, package lines {a}–{b}. The \"Today\" column describes the code at `3719b9f`.")
w("")
out.extend(body)
w("")

# ── 4. §5.2 register rows ──────────────────────────────────────────────────
ra, _ = one(pkg, "### 5.2 Full register")
rb, _ = one(pkg, "### 5.3 Transition table")
hdr = rows(pkg, ra, rb, ["| # | Decision | Recommendation | Blocks |", "|---|---|---|---|"])
picked = rows(pkg, ra, rb, [f"| {n} |" for n in ("5-1", "5-2", "5-3", "5-7", "5-10", "5-12", "5-14", "5-15", "5-24")])
w("## 4. Review package §5.2 — register rows that bear on subscription and device states")
w("")
w(f"Heading, verbatim, package line {ra}: \"{pkg[ra - 1].lstrip('# ')}\". These rows are recommendations, not approvals. Verbatim, package lines " + ", ".join(str(i) for i, _ in picked) + ".")
w("")
for _, l in hdr + picked:
    w(l)
w("")

# ── 5. repository records of later decisions ───────────────────────────────
def repo_row(rel: str, prefix: str) -> tuple[int, str]:
    lines = (root / rel).read_text(encoding="utf-8").splitlines()
    return one(lines, prefix)


w("## 5. Later decisions already recorded in the repository")
w("")
w("Verbatim rows from the milestone records, with file and line.")
w("")
for rel, prefix in [
    ("docs/design/milestones/M2-R-evidence.md", "| 5-1 |"),
    ("docs/design/milestones/M5.md", "| Q6 |"),
    ("docs/design/milestones/M5.md", "| Q7 |"),
    ("docs/design/milestones/M5.md", "| Q8 |"),
]:
    n, l = repo_row(rel, prefix)
    w(f"`{rel}:{n}`")
    w("")
    w("> " + l)
    w("")
w("The locked plan-change and status rules that remain in force are in `docs/PAYMENT_ENTITLEMENT_AUDIT.md` §15 (\"Upgrade / downgrade (locked)\") and §21; they are not copied here because that file is already in the repository.")
w("")

# ── 6. coverage pack ────────────────────────────────────────────────────────
w("## 6. Design handover, Coverage Pack — rows that bear on these states")
w("")
conf_n, conf = one(cov, "Confirmed rules (unchanged):")
w(f"Verbatim, `COVERAGE.md` line {conf_n}:")
w("")
w("> " + conf)
w("")
cov_rows = [one(cov, p) for p in (
    "| Item | Covered by | Status |",
    "|---|---|---|",
    "| Checkout summary, verifying, success, failure, cancelled |",
    "| Active subscription, upgrade review, scheduled cancellation, resubscription |",
    "| Downgrade: Pro → Plus / paid → Free |",
    "| Free accounts and the existing Playground device limit |",
    "| Payment problem, grace period |",
    "| Prices, proration, grace, refunds |",
    "| Free accounts already holding personal tasks |",
    "| Legacy Max accounts and billing records |",
)]
w("Verbatim rows, `COVERAGE.md` lines " + ", ".join(str(n) for n, _ in cov_rows[2:]) + ". The pack's own status key: \"**Complete** = designed to the confirmed entitlement rules · **Proposed** = designed, needs owner approval\".")
w("")
for _, l in cov_rows:
    w(l)
w("")

# ── 7. conflicts (analysis) ────────────────────────────────────────────────
w("## 7. Where the documents differ, one by one (analysis for the M8-R plan)")
w("")
w("No document is superseded as a whole. Each row names the later dated record that governs the point.")
w("")
w("| # | Difference | What governs, and since when |")
w("|---|---|---|")
for n, d, g in [
    ("C1", "The audit's §21 lists Plus ₹199 / Pro ₹399 / Max ₹1,199 as \"Locked\"", "They remain the configured catalogue. They are not approved pricing for the redesign: 2026-11-06 (\"pricing approval itself remains open\", §5 above) and 2026-11-07 (M5 Q7, §5 above). 5-1 is open (§4)"),
    ("C2", "The audit's §15 and §21 treat Max as a tier that can be bought", "2026-11-07, M5 Q7: \"Max never offered\". The Coverage Pack agrees: \"Max removed\" with legacy Max accounts kept intact (§6)"),
    ("C3", "The audit's monthly roster with Keep / Remove rollover", "Stands under `monthly`. Under `choices`, 5-23 as approved 2026-11-02 (§2)"),
    ("C4", "The audit's §21 status → access matrix and §15 plan-change timing", "No conflict: in force, and they match the code. The 5-20 table (§3) is a proposal only"),
    ("C5", "Coverage Pack \"decision 2\": on paid → Free, \"other laws locked\" (§6)", "5-4 as approved 2026-11-02 (§2) gives the detail: original choices preserved, explicit selection of any remaining allowance, saved data kept"),
    ("C6", "Coverage Pack \"decision 4b\": Free accounts already holding personal tasks (§6)", "5-6a approved and 5-6b deferred, 2026-11-02 (§2): the create / edit gate for existing holders is not decided"),
    ("C7", "Coverage Pack \"period-end cancellation per decision 3\" (§6)", "Consistent with the audit's §21 and with the service. Only 5-20's sub-question on immediate cancellation is open (§2)"),
    ("C8", "The roadmap's \"M8\" (prototype viewers, gate DV-18) and the review package's \"M8-R\"", "Both apply. DV-18 stays the gate and stays U wherever a comparison was not made"),
]:
    w(f"| {n} | {d} | {g} |")
w("")
w("## 8. Findings recorded against these decisions")
w("")
w("Found by inspection at `079257e`; to be confirmed and characterised by tests in M8-Ra. They are defects or open questions, not decisions.")
w("")
w("- **H2 — blocks `choices` activation.** Paid adds never write the choice ledger, so under `choices` a former paid account is RecallC Free with 0 of 3 choices used, every paid-era law carried forward and learnable, and three more addable. This does not follow 5-4 (§2).")
w("- **H3 — blocks `choices` activation.** A checkout that is started and abandoned leaves a `created` subscription row current; under `choices` that account is hard-gated and loses its Free choices until the provider expires the row (5-20 row 1, §3).")
w("- **H1.** The read-only \"expired\" state pinned by the expired cohort tests is a subscription row that is both terminal and current — a shape the service does not keep (`subscriptions/service.py`, `_persist_provider` marks a terminal row not-current).")
w("- **H7.** With the stored period elapsed and the provider row still `active`, the billing page shows the ordinary current-plan actions. Not changed; a state / action matrix is to be reviewed first.")

target = root / "docs/design/milestones/ENTITLEMENT_DECISIONS.md"
target.write_text("\n".join(out) + "\n", encoding="utf-8")
print(target, len(out), "lines")
