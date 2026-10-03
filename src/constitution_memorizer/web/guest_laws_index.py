"""Guest desktop Laws index (CTA map guest/03-screen). Presentation only.

Phone /laws and authed /laws keep `law_catalog.seed.json`. Cards with an
existing Bare Act or mapped-law reader point at that head. Prototype-only
rows stay on the index for visual/filter match.
"""

from __future__ import annotations

from dataclasses import dataclass

from constitution_memorizer.web.law_catalog import normalize_search


@dataclass(frozen=True)
class GuestLawChip:
    id: str
    label: str
    status: str = ""


@dataclass(frozen=True)
class GuestLawCard:
    id: str
    title: str
    tag_line: str
    scope_label: str
    subjects: tuple[str, ...]
    status: str
    href: str
    search_blob: str


GUEST_LAWS_CHIPS: tuple[GuestLawChip, ...] = (
    GuestLawChip(id="", label="All"),
    GuestLawChip(id="criminal", label="Criminal"),
    GuestLawChip(id="commercial", label="Commercial"),
    GuestLawChip(id="financial", label="Financial"),
    GuestLawChip(id="constitutional", label="Constitutional"),
    GuestLawChip(id="administrative", label="Administrative"),
    GuestLawChip(id="environmental", label="Environmental"),
    GuestLawChip(id="repealed", label="Repealed", status="repealed"),
)


def _card(
    law_id: str,
    tag_line: str,
    title: str,
    scope_label: str,
    subject: str,
    status: str,
    href: str,
    *search_parts: object,
) -> GuestLawCard:
    return GuestLawCard(
        id=law_id,
        title=title,
        tag_line=tag_line,
        scope_label=scope_label,
        subjects=(subject,),
        status=status,
        href=href,
        search_blob=normalize_search(
            title, law_id, subject, status, scope_label, *search_parts
        ),
    )


# Visible All-order matches guest/03-screen.jpg (row-major, two columns).
GUEST_LAWS_CARDS: tuple[GuestLawCard, ...] = (
    _card(
        "bns",
        "CRIMINAL · FULL ACT",
        "The Bharatiya Nyaya Sanhita, 2025",
        "20 Chapters · Sections 1–358",
        "criminal",
        "current",
        "/laws/bns",
        "BNS",
        "Bharatiya Nyaya Sanhita",
        2023,
        2025,
        "IPC",
    ),
    _card(
        "bnss",
        "CRIMINAL · FULL ACT",
        "The Bharatiya Nagarik Suraksha Sanhita, 2023",
        "39 Chapters · Sections 1–531",
        "criminal",
        "current",
        "/laws/bnss",
        "BNSS",
        "CrPC",
        2023,
    ),
    _card(
        "ndps",
        "CRIMINAL · FULL ACT",
        "The Narcotic Drugs and Psychotropic Substances Act, 1985",
        "6 Chapters · Sections 1–83 · Schedule",
        "criminal",
        "current",
        "/laws/ndps",
        "NDPS",
        "Narcotics",
        1985,
    ),
    _card(
        "uapa",
        "CRIMINAL · FULL ACT",
        "The Unlawful Activities (Prevention) Act, 1967",
        "7 Chapters · Sections 1–53",
        "criminal",
        "current",
        "/laws/uapa",
        "UAPA",
        1967,
    ),
    _card(
        "pota",
        "CRIMINAL · FULL ACT",
        "The Prevention of Terrorism Act, 2002",
        "6 Chapters · Sections 1–64",
        "criminal",
        "repealed",
        "/laws/pota",
        "POTA",
        2002,
        "repealed",
    ),
    _card(
        "bsa",
        "CRIMINAL · FULL ACT",
        "The Bharatiya Sakshya Adhiniyam, 2023",
        "12 Chapters · Sections 1–170",
        "criminal",
        "current",
        "/laws/bsa",
        "BSA",
        "Sakshya",
        2023,
        "Evidence",
    ),
    _card(
        "pmla",
        "FINANCIAL · FULL ACT",
        "The Prevention of Money-laundering Act, 2002",
        "10 Chapters · Sections 1–75",
        "financial",
        "current",
        "/laws/pmla",
        "PMLA",
        "Money-laundering",
        2002,
    ),
    _card(
        "pss",
        "FINANCIAL · FULL ACT",
        "The Payment and Settlement Systems Act, 2007",
        "8 Chapters · Sections 1–38",
        "financial",
        "current",
        "/laws/pss",
        "PSS",
        2007,
    ),
    _card(
        "ca",
        "COMMERCIAL · FULL ACT",
        "The Companies Act, 2013",
        "29 Chapters · Sections 1–470",
        "commercial",
        "current",
        "/laws/ca",
        "Companies",
        2013,
    ),
    _card(
        "ica",
        "COMMERCIAL · FULL ACT",
        "The Indian Contract Act, 1872",
        "10 Chapters · Sections 1–238",
        "commercial",
        "current",
        "/laws/ica",
        "Contract",
        1872,
    ),
    _card(
        "arb",
        "COMMERCIAL · FULL ACT",
        "The Arbitration and Conciliation Act, 1996",
        "4 Parts · Sections 1–87",
        "commercial",
        "current",
        "/laws/arb",
        "Arbitration",
        1996,
    ),
    _card(
        "tpa",
        "COMMERCIAL · FULL ACT",
        "The Transfer of Property Act, 1882",
        "8 Chapters · Sections 1–137",
        "commercial",
        "current",
        "/laws/tpa",
        "Transfer of Property",
        1882,
    ),
    _card(
        "it",
        "ADMINISTRATIVE · FULL ACT",
        "The Information Technology Act, 2000",
        "13 Chapters · Sections 1–90",
        "administrative",
        "current",
        "/laws/it",
        "IT Act",
        2000,
    ),
    _card(
        "rti",
        "ADMINISTRATIVE · KEY PROVISIONS",
        "Right to Information Act, 2005",
        "Arts 19",
        "administrative",
        "current",
        "/laws/rti-2005",
        "RTI",
        2005,
    ),
    _card(
        "rpa",
        "CONSTITUTIONAL · KEY PROVISIONS",
        "Representation of the People Act, 1951",
        "Arts 324, 325, 326, 327, 329",
        "constitutional",
        "current",
        "/laws/rpa-1951",
        "RP Act",
        1951,
    ),
    _card(
        "epa",
        "ENVIRONMENTAL · KEY PROVISIONS",
        "Environment (Protection) Act, 1986",
        "Arts 48A, 51A",
        "environmental",
        "current",
        "/laws/epa-1986",
        "EPA",
        1986,
    ),
)

EXISTING_LAW_HEADS: frozenset[str] = frozenset(
    {
        "/laws/bns",
        "/laws/bnss",
        "/laws/ndps",
        "/laws/uapa",
        "/laws/pota",
        "/laws/pss",
        "/laws/rti-2005",
        "/laws/rpa-1951",
        "/laws/epa-1986",
    }
)
