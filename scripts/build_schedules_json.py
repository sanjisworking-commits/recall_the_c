"""Build the read-only Schedules fixture from tables + official Bare Act wording."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "data" / "reference" / "tables"
OUT = ROOT / "src" / "constitution_memorizer" / "web" / "schedules.json"

OATH_ALT = (
    '<span class="sched-oath-alt"><span>do swear in the name of God</span>'
    "<span>solemnly affirm</span></span>"
)


def oath(form: str, who: str, body: str, note: str | None = None) -> dict:
    text = body.replace("SWEAR_OR_AFFIRM", OATH_ALT)
    item = {"form": form, "who": who, "text": f"“{text}”"}
    if note:
        item["note"] = note
    return item


def three(rows: list[tuple[str, str, str]]) -> dict:
    return {"t": "table", "kind": "three", "rows": [{"a": a, "b": b, "c": c} for a, b, c in rows]}


def two(rows: list[tuple[str, str]]) -> dict:
    return {"t": "table", "kind": "two", "rows": [{"a": a, "b": b} for a, b in rows]}


def pay(rows: list[tuple[str, str]]) -> dict:
    return {"t": "table", "kind": "pay", "rows": [{"a": a, "b": b} for a, b in rows]}


def parts(rows: list[tuple[str, str]]) -> dict:
    return {"t": "table", "kind": "parts", "rows": [{"a": a, "b": b} for a, b in rows]}


def cl(mark: str, s: str, pad: int = 0) -> dict:
    return {"t": "cl", "mark": mark, "s": s, "pad": pad}


def lead(lead_s: str, s: str, pad: int = 0) -> dict:
    return {"t": "lead", "lead": lead_s, "s": s, "pad": pad}


def sec(num: str, title: str) -> dict:
    return {"t": "sec", "num": num, "title": title}


def h(s: str) -> dict:
    return {"t": "h", "s": s}


def p(s: str) -> dict:
    return {"t": "p", "s": s}


def first() -> dict:
    states = [
        ("1", "Andhra Pradesh", "The territories specified in sub-section (1) of section 3 of the Andhra State Act, 1953, sub-section (1) of section 3 of the States Reorganisation Act, 1956, the First Schedule to the Andhra Pradesh and Madras (Alteration of Boundaries) Act, 1959, and the Schedule to the Andhra Pradesh and Mysore (Transfer of Territory) Act, 1968, but excluding the territories specified in the Second Schedule to the Andhra Pradesh and Madras (Alteration of Boundaries) Act, 1959 and the territories specified in section 3 of the Andhra Pradesh Reorganisation Act, 2014."),
        ("2", "Assam", "The territories which immediately before the commencement of this Constitution were comprised in the Province of Assam, the Khasi States and the Assam Tribal Areas, but excluding the territories specified in the Schedule to the Assam (Alteration of Boundaries) Act, 1951 and the territories specified in section 3 of the State of Nagaland Act, 1962 and the territories specified in sections 5, 6 and 7 of the North-Eastern Areas (Reorganisation) Act, 1971 and the territories referred to in Part I of the Second Schedule to the Constitution (One Hundredth Amendment) Act, 2015."),
        ("3", "Bihar", "The territories which immediately before the commencement of this Constitution were either comprised in the Province of Bihar or were being administered as if they formed part of that Province and the territories specified in clause (a) of sub-section (1) of section 3 of the Bihar and Uttar Pradesh (Alteration of Boundaries) Act, 1968, but excluding the territories specified in sub-section (1) of section 3 of the Bihar and West Bengal (Transfer of Territories) Act, 1956 and the territories specified in section 3 of the Bihar Reorganisation Act, 2000."),
        ("4", "Gujarat", "The territories referred to in sub-section (1) of section 3 of the Bombay Reorganisation Act, 1960."),
        ("5", "Kerala", "The territories specified in sub-section (1) of section 5 of the States Reorganisation Act, 1956."),
        ("6", "Madhya Pradesh", "The territories specified in sub-section (1) of section 9 of the States Reorganisation Act, 1956 and the First Schedule to the Rajasthan and Madhya Pradesh (Transfer of Territories) Act, 1959, but excluding the territories specified in section 3 of the Madhya Pradesh Reorganisation Act, 2000."),
        ("7", "Tamil Nadu", "The territories which immediately before the commencement of this Constitution were either comprised in the Province of Madras or were being administered as if they formed part of that Province and the territories specified in section 4 of the States Reorganisation Act, 1956, and the Second Schedule to the Andhra Pradesh and Madras (Alteration of Boundaries) Act, 1959, but excluding the territories specified in sub-section (1) of section 3 and sub-section (1) of section 4 of the Andhra State Act, 1953 and the territories specified in clause (b) of sub-section (1) of section 5, section 6 and clause (d) of sub-section (1) of section 7 of the States Reorganisation Act, 1956 and the territories specified in the First Schedule to the Andhra Pradesh and Madras (Alteration of Boundaries) Act, 1959."),
        ("8", "Maharashtra", "The territories specified in sub-section (1) of section 8 of the States Reorganisation Act, 1956, but excluding the territories referred to in sub-section (1) of section 3 of the Bombay Reorganisation Act, 1960."),
        ("9", "Karnataka", "The territories specified in sub-section (1) of section 7 of the States Reorganisation Act, 1956, but excluding the territory specified in the Schedule to the Andhra Pradesh and Mysore (Transfer of Territory) Act, 1968."),
        ("10", "Odisha", "The territories which immediately before the commencement of this Constitution were either comprised in the Province of Orissa or were being administered as if they formed part of that Province."),
        ("11", "Punjab", "The territories specified in section 11 of the States Reorganisation Act, 1956 and the territories referred to in Part II of the First Schedule to the Acquired Territories (Merger) Act, 1960, but excluding the territories referred to in Part II of the First Schedule to the Constitution (Ninth Amendment) Act, 1960 and the territories specified in sub-section (1) of section 3, section 4 and sub-section (1) of section 5 of the Punjab Reorganisation Act, 1966."),
        ("12", "Rajasthan", "The territories specified in section 10 of the States Reorganisation Act, 1956, but excluding the territories specified in the First Schedule to the Rajasthan and Madhya Pradesh (Transfer of Territories) Act, 1959."),
        ("13", "Uttar Pradesh", "The territories which immediately before the commencement of this Constitution were either comprised in the Province known as the United Provinces or were being administered as if they formed part of that Province and the territories specified in clause (b) of sub-section (1) of section 3 of the Bihar and Uttar Pradesh (Alteration of Boundaries) Act, 1968 and the territories specified in clause (b) of sub-section (1) of section 4 of the Haryana and Uttar Pradesh (Alteration of Boundaries) Act, 1979, but excluding the territories specified in clause (a) of sub-section (1) of section 3 of the Bihar and Uttar Pradesh (Alteration of Boundaries) Act, 1968, and the territories specified in section 3 of the Uttar Pradesh Reorganisation Act, 2000 and the territories specified in clause (a) of sub-section (1) of section 4 of the Haryana and Uttar Pradesh (Alteration of Boundaries) Act, 1979."),
        ("14", "West Bengal", "The territories which immediately before the commencement of this Constitution were either comprised in the Province of West Bengal or were being administered as if they formed part of that Province and the territory of Chandernagore as defined in clause (c) of section 2 of the Chandernagore (Merger) Act, 1954 and also the territories specified in sub-section (1) of section 3 of the Bihar and West Bengal (Transfer of Territories) Act, 1956 and the territories referred to in Part III of the First Schedule to the Acquired Territories (Merger) Act, 1960."),
        ("16", "Nagaland", "The territories specified in sub-section (1) of section 3 of the State of Nagaland Act, 1962."),
        ("17", "Haryana", "The territories specified in sub-section (1) of section 3 of the Punjab Reorganisation Act, 1966 and the territories specified in clause (a) of sub-section (1) of section 4 of the Haryana and Uttar Pradesh (Alteration of Boundaries) Act, 1979, but excluding the territories specified in clause (b) of sub-section (1) of section 4 of that Act."),
        ("18", "Himachal Pradesh", "The territories which immediately before the commencement of this Constitution were being administered as if they were Chief Commissioners' Provinces under the names of Himachal Pradesh and Bilaspur and the territories specified in sub-section (1) of section 5 of the Punjab Reorganisation Act, 1966."),
        ("19", "Manipur", "The territory which immediately before the commencement of this Constitution was being administered as if it were a Chief Commissioner's Province under the name of Manipur."),
        ("20", "Tripura", "The territory which immediately before the commencement of this Constitution was being administered as if it were a Chief Commissioner's Province under the name of Tripura."),
        ("21", "Meghalaya", "The territories specified in section 5 of the North-Eastern Areas (Reorganisation) Act, 1971."),
        ("22", "Sikkim", "The territories which immediately before the commencement of the Constitution (Thirty-sixth Amendment) Act, 1975, were comprised in Sikkim."),
        ("23", "Mizoram", "The territories specified in section 6 of the North-Eastern Areas (Reorganisation) Act, 1971."),
        ("24", "Arunachal Pradesh", "The territories specified in section 7 of the North-Eastern Areas (Reorganisation) Act, 1971."),
        ("25", "Goa", "The territories specified in section 3 of the Goa, Daman and Diu Reorganisation Act, 1987."),
        ("26", "Chhattisgarh", "The territories specified in section 3 of the Madhya Pradesh Reorganisation Act, 2000."),
        ("27", "Uttarakhand", "The territories specified in section 3 of the Uttar Pradesh Reorganisation Act, 2000."),
        ("28", "Jharkhand", "The territories specified in section 3 of the Bihar Reorganisation Act, 2000."),
        ("29", "Telangana", "The territories specified in section 3 of the Andhra Pradesh Reorganisation Act, 2014."),
    ]
    uts = [
        ("1", "Delhi", "The territory which immediately before the commencement of this Constitution was comprised in the Chief Commissioner's Province of Delhi."),
        ("2", "The Andaman and Nicobar Islands", "The territory which immediately before the commencement of this Constitution was comprised in the Chief Commissioner's Province of the Andaman and Nicobar Islands."),
        ("3", "Lakshadweep", "The territory specified in section 6 of the States Reorganisation Act, 1956."),
        ("4", "Dadra and Nagar Haveli and Daman and Diu", "The territories specified in section 4 of the Goa, Daman and Diu Reorganisation Act, 1987 and the territory which immediately before the eleventh day of August, 1961 was comprised in Free Dadra and Nagar Haveli."),
        ("6", "Puducherry", "The territories which immediately before the sixteenth day of August, 1962, were comprised in the French Establishments in India known as Pondicherry, Karikal, Mahe and Yanam."),
        ("7", "Chandigarh", "The territories specified in section 4 of the Punjab Reorganisation Act, 1966."),
        ("8", "Jammu and Kashmir", "The territories specified in section 4 of the Jammu and Kashmir Reorganisation Act, 2019."),
        ("9", "Ladakh", "The territories specified in section 3 of the Jammu and Kashmir Reorganisation Act, 2019."),
    ]
    return {
        "blocks": [h("I. The States"), three(states), h("II. The Union Territories"), three(uts)],
        "notes": [
            "Jammu and Kashmir (entry 15) omitted by the Jammu and Kashmir Reorganisation Act, 2019; the State is now Union territories of Jammu and Kashmir and Ladakh.",
        ],
    }


def second() -> dict:
    return {
        "blocks": [
            sec("A", "Provisions as to the President and the Governors of States"),
            cl("1.", "There shall be paid to the President and to the Governors of the States such emoluments, allowances and privileges as may from time to time be determined by Parliament by law and, until provision in that behalf is so made, such emoluments, allowances and privileges as are specified in this Schedule."),
            cl("2.", "There shall also be paid to the President and to the Governors of the States such other allowances and privileges as are specified in this Schedule."),
            p("Until Parliament by law otherwise provides, there shall be paid to the President and to the Governors of States the following emoluments:"),
            pay(
                [
                    ("The President", "5,00,000 rupees per mensem"),
                    ("The Governor of a State", "3,50,000 rupees per mensem"),
                ]
            ),
            sec("C", "Provisions as to the Speaker and the Deputy Speaker of the House of the People and the Chairman and the Deputy Chairman of the Council of States and the Speaker and the Deputy Speaker of the Legislative Assembly and the Chairman and the Deputy Chairman of the Legislative Council of a State"),
            cl("7.", "There shall be paid to the Speaker of the House of the People and to the Chairman of the Council of States such salaries and allowances as may be respectively fixed by Parliament by law, and, until provision in that behalf is so made, such salaries as are specified in this Schedule."),
            cl("8.", "There shall be paid to the Speaker and the Deputy Speaker of the Legislative Assembly of a State, and to the Chairman and the Deputy Chairman of the Legislative Council of a State, such salaries and allowances as may be respectively fixed by the Legislature of the State by law, and, until provision in that behalf is so made, such salaries as are specified in this Schedule."),
            sec("D", "Provisions as to the Judges of the Supreme Court and of the High Courts"),
            cl("9.", "There shall be paid to the Judges of the Supreme Court, in respect of time spent on actual service, salary at the following rates per mensem, that is to say:—"),
            pay(
                [
                    ("The Chief Justice", "2,80,000 rupees per mensem"),
                    ("Any other Judge", "2,50,000 rupees per mensem"),
                ]
            ),
            cl("10.", "Every Judge of the Supreme Court shall be entitled without payment of rent to the use of an official residence."),
            cl("11.", "There shall be paid to the Judges of High Courts, in respect of time spent on actual service, salary at the following rates per mensem, that is to say:—"),
            pay(
                [
                    ("The Chief Justice", "2,50,000 rupees per mensem"),
                    ("Any other Judge", "2,25,000 rupees per mensem"),
                ]
            ),
            sec("E", "Provisions as to the Comptroller and Auditor-General of India"),
            cl("12.", "There shall be paid to the Comptroller and Auditor-General of India a salary at the rate of 2,50,000 rupees per mensem and he shall be entitled to such other allowances and privileges as may be determined by Parliament by law."),
        ],
        "notes": [
            "Part B omitted by the Constitution (Seventh Amendment) Act, 1956, s. 29 and Sch.",
            "Salary figures in this Schedule have been revised by Parliament from time to time; the amounts shown follow the current statutory rates referenced in the notes to the official text.",
        ],
    }


def third() -> dict:
    return {
        "blocks": [
            {
                "t": "oaths",
                "items": [
                    oath("FORM I", "Form of oath of office for a Minister for the Union", f"I, A. B., {OATH_ALT} that I will bear true faith and allegiance to the Constitution of India as by law established, that I will uphold the sovereignty and integrity of India, that I will faithfully and conscientiously discharge my duties as a Minister for the Union and that I will do right to all manner of people in accordance with the Constitution and the law, without fear or favour, affection or ill-will."),
                    oath("FORM II", "Form of oath of secrecy for a Minister for the Union", f"I, A.B., {OATH_ALT} that I will not directly or indirectly communicate or reveal to any person or persons any matter which shall be brought under my consideration or shall become known to me as a Minister for the Union except as may be required for the due discharge of my duties as such Minister."),
                    oath("FORM III · A", "Form of oath or affirmation to be made by a candidate for election to Parliament", f"I, A.B., having been nominated as a candidate to fill a seat in the Council of States (or the House of the People) {OATH_ALT} that I will bear true faith and allegiance to the Constitution of India as by law established and that I will uphold the sovereignty and integrity of India.", "See also arts. 84 (a) and 173 (a)."),
                    oath("FORM III · B", "Form of oath or affirmation to be made by a member of Parliament", f"I, A.B., having been elected (or nominated) a member of the Council of States (or the House of the People) {OATH_ALT} that I will bear true faith and allegiance to the Constitution of India as by law established, that I will uphold the sovereignty and integrity of India and that I will faithfully discharge the duty upon which I am about to enter."),
                    oath("FORM IV", "Form of oath or affirmation to be made by the Judges of the Supreme Court and the Comptroller and Auditor-General of India", f"I, A.B., having been appointed Chief Justice (or a Judge) of the Supreme Court of India (or Comptroller and Auditor-General of India) {OATH_ALT} that I will bear true faith and allegiance to the Constitution of India as by law established, that I will uphold the sovereignty and integrity of India, that I will duly and faithfully and to the best of my ability, knowledge and judgment perform the duties of my office without fear or favour, affection or ill-will and that I will uphold the Constitution and the laws."),
                    oath("FORM V", "Form of oath of office for a Minister for a State", f"I, A.B., {OATH_ALT} that I will bear true faith and allegiance to the Constitution of India as by law established, that I will uphold the sovereignty and integrity of India, that I will faithfully and conscientiously discharge my duties as a Minister for the State of …… and that I will do right to all manner of people in accordance with the Constitution and the law without fear or favour, affection or ill-will."),
                    oath("FORM VI", "Form of oath of secrecy for a Minister for a State", f"I, A.B., {OATH_ALT} that I will not directly or indirectly communicate or reveal to any person or persons any matter which shall be brought under my consideration or shall become known to me as a Minister for the State of …… except as may be required for the due discharge of my duties as such Minister."),
                    oath("FORM VII · A", "Form of oath or affirmation to be made by a candidate for election to the Legislature of a State", f"I, A.B., having been nominated as a candidate to fill a seat in the Legislative Assembly (or Legislative Council) {OATH_ALT} that I will bear true faith and allegiance to the Constitution of India as by law established and that I will uphold the sovereignty and integrity of India."),
                    oath("FORM VII · B", "Form of oath or affirmation to be made by a member of the Legislature of a State", f"I, A.B., having been elected (or nominated) a member of the Legislative Assembly (or Legislative Council) {OATH_ALT} that I will bear true faith and allegiance to the Constitution of India as by law established, that I will uphold the sovereignty and integrity of India and that I will faithfully discharge the duty upon which I am about to enter."),
                    oath("FORM VIII", "Form of oath or affirmation to be made by the Judges of a High Court", f"I, A.B., having been appointed Chief Justice (or a Judge) of the High Court at (or of) …… {OATH_ALT} that I will bear true faith and allegiance to the Constitution of India as by law established, that I will uphold the sovereignty and integrity of India, that I will duly and faithfully and to the best of my ability, knowledge and judgment perform the duties of my office without fear or favour, affection or ill-will and that I will uphold the Constitution and the laws."),
                ],
            }
        ],
        "notes": [
            "Ins. by the Constitution (Sixteenth Amendment) Act, 1963, s. 5 (w.e.f. 5-10-1963).",
        ],
    }


def fourth() -> dict:
    rows = [
        ("1", "Andhra Pradesh", "11"),
        ("2", "Telangana", "7"),
        ("3", "Assam", "7"),
        ("4", "Bihar", "16"),
        ("5", "Jharkhand", "6"),
        ("6", "Goa", "1"),
        ("7", "Gujarat", "11"),
        ("8", "Haryana", "5"),
        ("9", "Kerala", "9"),
        ("10", "Madhya Pradesh", "11"),
        ("11", "Chhattisgarh", "5"),
        ("12", "Tamil Nadu", "18"),
        ("13", "Maharashtra", "19"),
        ("14", "Karnataka", "12"),
        ("15", "Odisha", "10"),
        ("16", "Punjab", "7"),
        ("17", "Rajasthan", "10"),
        ("18", "Uttar Pradesh", "31"),
        ("19", "Uttarakhand", "3"),
        ("20", "West Bengal", "16"),
        ("21", "Nagaland", "1"),
        ("22", "Himachal Pradesh", "3"),
        ("23", "Manipur", "1"),
        ("24", "Tripura", "1"),
        ("25", "Meghalaya", "1"),
        ("26", "Sikkim", "1"),
        ("27", "Mizoram", "1"),
        ("28", "Arunachal Pradesh", "1"),
        ("29", "Delhi", "3"),
        ("30", "Puducherry", "1"),
        ("31", "Jammu and Kashmir", "4"),
        ("", "Total", "233"),
    ]
    return {
        "blocks": [
            h("Allocation of seats in the Council of States"),
            p("To each State or Union territory specified in the first column of the following table, there shall be allotted the number of seats specified in the second column thereof opposite to that State or that Union territory, as the case may be:"),
            three(rows),
        ],
        "notes": [
            "Fourth Schedule subs. by the Constitution (Seventh Amendment) Act, 1956, s. 3(2) (w.e.f. 1-11-1956), and amended as States were reorganised.",
        ],
    }


def fifth() -> dict:
    return {
        "blocks": [
            h("PART A — GENERAL"),
            sec("1", "Interpretation"),
            cl("1.", "In this Schedule, unless the context otherwise requires, the expression “State” does not include the States of Assam, Meghalaya, Tripura and Mizoram."),
            sec("2", "Executive power of a State in Scheduled Areas"),
            cl("2.", "Subject to the provisions of this Schedule, the executive power of a State extends to the Scheduled Areas therein."),
            sec("3", "Report by the Governor to the President regarding the administration of Scheduled Areas"),
            cl("3.", "The Governor of each State having Scheduled Areas therein shall annually, or whenever so required by the President, make a report to the President regarding the administration of the Scheduled Areas in that State and the executive power of the Union shall extend to the giving of directions to the State as to the administration of the said areas."),
            h("PART B — ADMINISTRATION AND CONTROL OF SCHEDULED AREAS AND SCHEDULED TRIBES"),
            sec("4", "Tribes Advisory Council"),
            cl("(1)", "There shall be established in each State having Scheduled Areas therein and, if the President so directs, also in any State having Scheduled Tribes but not Scheduled Areas therein, a Tribes Advisory Council consisting of not more than twenty members of whom, as nearly as may be, three-fourths shall be the representatives of the Scheduled Tribes in the Legislative Assembly of the State."),
            cl("(2)", "It shall be the duty of the Tribes Advisory Council to advise on such matters pertaining to the welfare and advancement of the Scheduled Tribes in the State as may be referred to them by the Governor."),
            sec("5", "Law applicable to Scheduled Areas"),
            cl("(1)", "Notwithstanding anything in this Constitution, the Governor may by public notification direct that any particular Act of Parliament or of the Legislature of the State shall not apply to a Scheduled Area or any part thereof in the State or shall apply to a Scheduled Area or any part thereof in the State subject to such exceptions and modifications as he may specify in the notification."),
            cl("(2)", "The Governor may make regulations for the peace and good government of any area in a State which is for the time being a Scheduled Area."),
            h("PART C — SCHEDULED AREAS"),
            sec("6", "Scheduled Areas"),
            cl("(1)", "In this Constitution, the expression “Scheduled Areas” means such areas as the President may by order declare to be Scheduled Areas."),
            cl("(2)", "The President may at any time by order—"),
            cl("(a)", "direct that the whole or any specified part of a Scheduled Area shall cease to be a Scheduled Area or a part of such an area;", 32),
            cl("(b)", "increase the area of any Scheduled Area in a State after consultation with the Governor of that State;", 32),
            cl("(c)", "alter, but only by way of rectification of boundaries, any Scheduled Area;", 32),
            cl("(d)", "on any alteration of the boundaries of a State or on the admission into the Union or the establishment of a new State, declare any territory not previously included in any State to be, or to form part of, a Scheduled Area;", 32),
            cl("(e)", "rescind, in relation to any State or States, any order or orders made under this paragraph, and in consultation with the Governor of the State concerned, make fresh orders redefining the areas which are to be Scheduled Areas;", 32),
            p("and any such order may contain such incidental and consequential provisions as the President may deem necessary and proper."),
            h("PART D — AMENDMENT OF THE SCHEDULE"),
            sec("7", "Amendment of the Schedule"),
            cl("(1)", "Parliament may from time to time by law amend by way of addition, variation or repeal any of the provisions of this Schedule and, when the Schedule is so amended, any reference to this Schedule in this Constitution shall be construed as a reference to such Schedule as so amended."),
            cl("(2)", "No such law as is mentioned in sub-paragraph (1) of this paragraph shall be deemed to be an amendment of this Constitution for the purposes of article 368."),
        ],
        "notes": [
            "Fifth Schedule: scheduled areas in States other than Assam, Meghalaya, Tripura and Mizoram (Art. 244(1)).",
        ],
    }


def sixth() -> dict:
    return {
        "blocks": [
            p("Provisions as to the Administration of Tribal Areas in the States of Assam, Meghalaya, Tripura and Mizoram."),
            sec("1", "Autonomous districts and autonomous regions"),
            cl("(1)", "Subject to the provisions of this paragraph, the tribal areas in each item of Parts I, II and IIA and in Part III of the table appended to paragraph 20 of this Schedule shall be an autonomous district."),
            cl("(2)", "If there are different Scheduled Tribes in an autonomous district, the Governor may, by public notification, divide the area or areas inhabited by them into autonomous regions."),
            cl("(3)", "The Governor may, by public notification,—"),
            cl("(a)", "include any area in any of the Parts of the said table;", 32),
            cl("(b)", "exclude any area from any of the Parts of the said table;", 32),
            cl("(c)", "create a new autonomous district;", 32),
            cl("(d)", "increase the area of any autonomous district;", 32),
            cl("(e)", "diminish the area of any autonomous district;", 32),
            cl("(f)", "unite two or more autonomous districts or parts thereof so as to form one autonomous district;", 32),
            cl("(ff)", "alter the name of any autonomous district;", 32),
            cl("(g)", "define the boundaries of any autonomous district:", 32),
            lead("Provided that", "no order shall be made by the Governor under clauses (c), (d), (e) and (f) of this sub-paragraph except after consideration of the report of a commission appointed under sub-paragraph (1) of paragraph 14 of this Schedule.", 32),
            sec("2", "Constitution of District Councils and Regional Councils"),
            cl("(1)", "There shall be a District Council for each autonomous district consisting of not more than thirty members, of whom not more than four persons shall be nominated by the Governor and the rest shall be elected on the basis of adult suffrage."),
            cl("(2)", "There shall be a separate Regional Council for each area constituted an autonomous region under sub-paragraph (2) of paragraph 1 of this Schedule."),
            cl("(3)", "Each District Council and each Regional Council shall be a body corporate by the name respectively of “the District Council of (name of district)” and “the Regional Council of (name of region)”, shall have perpetual succession and a common seal and shall by the said name sue and be sued."),
            sec("3", "Powers of the District Councils and Regional Councils to make laws"),
            cl("(1)", "The Regional Council for an autonomous region in respect of all areas within such region and the District Council for an autonomous district in respect of all areas within the district except those which are under the authority of Regional Councils, if any, within the district shall have power to make laws with respect to—"),
            cl("(a)", "the allotment, occupation or use, or the setting apart, of land, other than any land which is a reserved forest, for the purposes of agriculture or grazing or for residential or other non-agricultural purposes or for any other purpose likely to promote the interests of the inhabitants of any village or town;", 32),
            cl("(b)", "the management of any forest not being a reserved forest;", 32),
            cl("(c)", "the use of any canal or water-course for the purpose of agriculture;", 32),
            cl("(d)", "the regulation of the practice of jhum or other forms of shifting cultivation;", 32),
            cl("(e)", "the establishment of village or town committees or councils and their powers;", 32),
            cl("(f)", "any other matter relating to village or town administration, including village or town police and public health and sanitation;", 32),
            cl("(g)", "the appointment or succession of Chiefs or Headmen;", 32),
            cl("(h)", "the inheritance of property;", 32),
            cl("(i)", "marriage and divorce;", 32),
            cl("(j)", "social customs.", 32),
            sec("20", "Tribal areas"),
            cl("(1)", "The areas specified in Parts I, II, IIA and III of the table below shall be the tribal areas within the State of Assam, the State of Meghalaya, the State of Tripura and the State of Mizoram."),
            parts(
                [
                    ("Part I", "The North Cachar Hills District; The Karbi Anglong District; The Bodoland Territorial Area District."),
                    ("Part II", "Khasi Hills District; Jaintia Hills District; Garo Hills District."),
                    ("Part IIA", "Tripura Tribal Areas District."),
                    ("Part III", "The Chakma District; The Mara District; The Lai District."),
                ]
            ),
        ],
        "notes": [
            "Sixth Schedule: tribal areas of Assam, Meghalaya, Tripura and Mizoram (Arts. 244(2) and 275(1)). The full paragraph set (1–20B) is longer than this reading page; remaining paragraphs follow the official text.",
        ],
    }


def seventh() -> dict:
    data = json.loads((TABLES / "seventh.json").read_text())
    labels = [
        ("LIST I", "Union List", True),
        ("LIST II", "State List", False),
        ("LIST III", "Concurrent List", False),
    ]
    blocks = []
    for table, (eyebrow, title, open_) in zip(data.get("tables") or [], labels):
        items = []
        for row in table.get("rows") or []:
            if len(row) < 2:
                continue
            items.append({"n": str(row[0]), "s": str(row[1])})
        blocks.append(
            {
                "t": "list",
                "eyebrow": eyebrow,
                "title": title,
                "open": open_,
                "items": items,
            }
        )
    return {
        "blocks": blocks,
        "notes": [
            "Ins. by the Constitution (Forty-second Amendment) Act, 1976, s. 57 (w.e.f. 3-1-1977), and later amended.",
        ],
    }


def eighth() -> dict:
    notes = {
        "3": "Ins. by the Constitution (Ninety-second Amendment) Act, 2003, s. 2 (w.e.f. 7-1-2004).",
        "4": "Ins. by the Constitution (Ninety-second Amendment) Act, 2003, s. 2 (w.e.f. 7-1-2004).",
        "9": "Ins. by the Constitution (Seventy-first Amendment) Act, 1992, s. 2 (w.e.f. 31-8-1992). Entries 9 to 14 renumbered as entries 12 to 17 by the Constitution (Ninety-second Amendment) Act, 2003, s. 2 (w.e.f. 7-1-2004).",
        "10": "Ins. by the Constitution (Ninety-second Amendment) Act, 2003, s. 2 (w.e.f. 7-1-2004).",
        "12": "Ins. by the Constitution (Seventy-first Amendment) Act, 1992, s. 2 (w.e.f. 31-8-1992).",
        "14": "Ins. by the Constitution (Seventy-first Amendment) Act, 1992, s. 2 (w.e.f. 31-8-1992).",
        "15": "Subs. by the Constitution (Ninety-sixth Amendment) Act, 2011, s. 2, for “Oriya” (w.e.f. 23-9-2011).",
        "18": "Ins. by the Constitution (Ninety-second Amendment) Act, 2003, s. 2 (w.e.f. 7-1-2004).",
        "19": "Ins. by the Constitution (Twenty-first Amendment) Act, 1967, s. 2.",
    }
    added = {
        "3": "2003",
        "4": "2003",
        "9": "1992",
        "10": "2003",
        "12": "1992",
        "14": "1992",
        "18": "2003",
        "19": "1967",
    }
    items = []
    data = json.loads((TABLES / "languages.json").read_text())
    for row in (data.get("tables") or [{}])[0].get("rows") or []:
        n = str(row[0])
        item = {"n": n, "name": str(row[1])}
        if n in added:
            item["added"] = added[n]
        if n in notes:
            item["note"] = notes[n]
        items.append(item)
    return {"blocks": [{"t": "langs", "items": items}], "notes": []}


def ninth() -> dict:
    entries = [
        "The Bihar Land Reforms Act, 1950 (Bihar Act XXX of 1950).",
        "The Bombay Tenancy and Agricultural Lands Act, 1948 (Bombay Act LXVII of 1948).",
        "The Bombay Maleki Tenure Abolition Act, 1949 (Bombay Act LXI of 1949).",
        "The Bombay Taluqdari Tenure Abolition Act, 1949 (Bombay Act LXII of 1949).",
        "The Panch Mahals Mehwassi Tenure Abolition Act, 1949 (Bombay Act LXIII of 1949).",
        "The Bombay Khoti Abolition Act, 1950 (Bombay Act VI of 1950).",
        "The Bombay Paragana and Kulkarni Watan Abolition Act, 1950 (Bombay Act LX of 1950).",
        "The Madhya Pradesh Abolition of Proprietary Rights (Estates, Mahals, Alienated Lands) Act, 1950 (Madhya Pradesh Act I of 1951).",
        "The Madras Estates (Abolition and Conversion into Ryotwari) Act, 1948 (Madras Act XXVI of 1948).",
        "The Madras Estates (Abolition and Conversion into Ryotwari) Amendment Act, 1950 (Madras Act I of 1950).",
        "The Uttar Pradesh Zamindari Abolition and Land Reforms Act, 1950 (Uttar Pradesh Act I of 1951).",
        "The Hyderabad (Abolition of Jagirs) Regulation, 1358F (No. LXIX of 1358, Fasli).",
        "The Hyderabad Jagirs (Commutation) Regulation, 1359F (No. XXV of 1359, Fasli).",
        "The Bihar Displaced Persons Rehabilitation (Acquisition of Land) Act, 1950 (Bihar Act XXXVIII of 1950).",
        "The United Provinces Land Acquisition (Rehabilitation of Refugees) Act, 1948 (U.P. Act XXVI of 1948).",
        "The Resettlement of Displaced Persons (Land Acquisition) Act, 1948 (Act LX of 1948).",
        "Sections 52A to 52G of the Insurance Act, 1938 (Act IV of 1938), as inserted by section 42 of the Insurance (Amendment) Act, 1950 (Act XLVII of 1950).",
        "The Railway Companies (Emergency Provisions) Act, 1951 (Act LI of 1951).",
        "Chapter III-A of the Industries (Development and Regulation) Act, 1951 (Act LXV of 1951).",
        "The West Bengal Land Development and Planning Act, 1948 (West Bengal Act XXI of 1948), as amended by West Bengal Act XXIX of 1951.",
    ]
    units = json.loads((ROOT / "data" / "output" / "learning_units.json").read_text())
    extra = ""
    for u in units["units"]:
        if u.get("id") == "schedule-ninth":
            extra = u.get("text") or ""
            break
    seen = {e.lower() for e in entries}
    for line in extra.splitlines():
        line = line.strip()
        if not line or line.startswith("(") or line[0].isdigit() is False and not line[:3].lstrip("[").lstrip().lstrip("1234567890"):
            continue
        cleaned = line
        for prefix in range(1, 320):
            if cleaned.startswith(f"{prefix}."):
                cleaned = cleaned[len(str(prefix)) + 1 :].strip()
                break
            if cleaned.startswith(f"{prefix}. "):
                cleaned = cleaned[len(str(prefix)) + 2 :].strip()
                break
        if cleaned and cleaned.lower() not in seen and "Ninth Schedule" not in cleaned:
            if cleaned[0].isalpha() or cleaned[0] == "[":
                entries.append(cleaned)
                seen.add(cleaned.lower())
    blocks = [p(f"{i}. {text}") for i, text in enumerate(entries, start=1)]
    return {
        "blocks": blocks,
        "notes": [
            "Ninth Schedule (entries 1 to 13) added by the Constitution (First Amendment) Act, 1951, s. 14 (w.e.f. 18-6-1951).",
        ],
    }


def tenth() -> dict:
    return {
        "blocks": [
            h("Provisions as to disqualification on ground of defection"),
            sec("1", "Interpretation"),
            p("In this Schedule, unless the context otherwise requires,—"),
            cl("(a)", "“House” means either House of Parliament or the Legislative Assembly or, as the case may be, either House of the Legislature of a State;"),
            cl("(b)", "“legislature party”, in relation to a member of a House belonging to any political party in accordance with the provisions of paragraph 2 or *** paragraph 4, means the group consisting of all the members of that House for the time being belonging to that political party in accordance with the said provisions;"),
            cl("(c)", "“original political party”, in relation to a member of a House, means the political party to which he belongs for the purposes of sub-paragraph (1) of paragraph 2;"),
            cl("(d)", "“paragraph” means a paragraph of this Schedule."),
            sec("2", "Disqualification on ground of defection"),
            cl("(1)", "Subject to the provisions of paragraphs 4 and 5, a member of a House belonging to any political party shall be disqualified for being a member of the House—"),
            cl("(a)", "if he has voluntarily given up his membership of such political party; or", 32),
            cl("(b)", "if he votes or abstains from voting in such House contrary to any direction issued by the political party to which he belongs or by any person or authority authorised by it in this behalf, without obtaining, in either case, the prior permission of such political party, person or authority and such voting or abstention has not been condoned by such political party, person or authority within fifteen days from the date of such voting or abstention.", 32),
            lead("Explanation.—", "For the purposes of this sub-paragraph,—", 0),
            cl("(a)", "an elected member of a House shall be deemed to belong to the political party, if any, by which he was set up as a candidate for election as such member;", 32),
            cl("(b)", "a nominated member of a House shall, notwithstanding anything contained in sub-paragraph (1), be deemed to belong to the political party of which he becomes, or, as the case may be, first becomes, a member, before the expiry of six months from the date on which he takes his seat after being nominated.", 32),
            cl("(2)", "An elected member of a House who has been elected as such otherwise than as a candidate set up by any political party shall be disqualified for being a member of the House if he joins any political party after such election."),
            cl("(3)", "A nominated member of a House shall be disqualified for being a member of the House if he joins any political party after the expiry of six months from the date on which he takes his seat after being nominated."),
            cl("(4)", "Notwithstanding anything contained in the foregoing provisions of this paragraph, a person who, on the commencement of the Constitution (Fifty-second Amendment) Act, 1985, is a member of a House (whether elected or nominated as such) shall,—"),
            cl("(i)", "where he was a member of a political party immediately before such commencement, be deemed, for the purposes of sub-paragraph (1) of this paragraph, to have been elected as a member of such House as a candidate set up by such political party;", 32),
            cl("(ii)", "in any other case, be deemed to be an elected member of the House who has been elected as such otherwise than as a candidate set up by any political party for the purposes of sub-paragraph (2) of this paragraph or, as the case may be, be deemed to be a nominated member of the House for the purposes of sub-paragraph (3) of this paragraph.", 32),
            sec("4", "Disqualification on ground of defection not to apply in case of merger"),
            cl("(1)", "A member of a House shall not be disqualified under sub-paragraph (1) of paragraph 2 where his original political party merges with another political party and he claims that he and any other members of his original political party—"),
            cl("(a)", "have become members of such other political party or, as the case may be, of a new political party formed by such merger; or", 32),
            cl("(b)", "have not accepted the merger and opted to function as a separate group,", 32),
            p("and from the time of such merger, such other political party or new political party or group, as the case may be, shall be deemed to be the political party to which he belongs for the purposes of sub-paragraph (1) of paragraph 2 and to be his original political party for the purposes of this sub-paragraph."),
            cl("(2)", "For the purposes of sub-paragraph (1) of this paragraph, the merger of the original political party of a member of a House shall be deemed to have taken place if, and only if, not less than two-thirds of the members of the legislature party concerned have agreed to such merger."),
            sec("5", "Exemption"),
            p("Notwithstanding anything contained in this Schedule, a person who has been elected to the office of the Speaker or the Deputy Speaker of the House of the People or the Deputy Chairman of the Council of States or the Chairman or the Deputy Chairman of the Legislative Council of a State or the Speaker or the Deputy Speaker of the Legislative Assembly of a State, shall not be disqualified under this Schedule,—"),
            cl("(a)", "if he, by reason of his election to such office, voluntarily gives up the membership of the political party to which he belonged immediately before such election and does not, so long as he continues to hold such office thereafter, rejoin that political party or become a member of another political party; or"),
            cl("(b)", "if he, having given up by reason of his election to such office his membership of the political party to which he belonged immediately before such election, rejoins such political party after he ceases to hold such office."),
            sec("6", "Decision on questions as to disqualification on ground of defection"),
            cl("(1)", "If any question arises as to whether a member of a House has become subject to disqualification under this Schedule, the question shall be referred for the decision of the Chairman or, as the case may be, the Speaker of such House and his decision shall be final."),
            lead("Provided that", "where the question which has arisen is as to whether the Chairman or the Speaker of a House has become subject to such disqualification, the question shall be referred for the decision of such member of the House as the House may elect in this behalf and his decision shall be final."),
            cl("(2)", "All proceedings under sub-paragraph (1) of this paragraph in relation to any question as to disqualification of a member of a House under this Schedule shall be deemed to be proceedings in Parliament within the meaning of article 122 or, as the case may be, proceedings in the Legislature of a State within the meaning of article 212."),
            sec("7", "Bar of jurisdiction of courts"),
            p("Notwithstanding anything in this Constitution, no court shall have any jurisdiction in respect of any matter connected with the disqualification of a member of a House under this Schedule."),
            sec("8", "Rules"),
            cl("(1)", "Subject to the provisions of sub-paragraph (2) of this paragraph, the Chairman or the Speaker of a House may make rules for giving effect to the provisions of this Schedule, and in particular, and without prejudice to the generality of the foregoing, such rules may provide for—"),
            cl("(a)", "the maintenance of registers or other records as to the political parties, if any, to which different members of the House belong;", 32),
            cl("(b)", "the report which the leader of a legislature party in relation to a member of a House shall furnish with regard to any condonation of the nature referred to in clause (b) of sub-paragraph (1) of paragraph 2 in respect of such member, the time within which and the authority to whom such report shall be furnished;", 32),
            cl("(c)", "the reports which a political party shall furnish in relation to petitions to the Chairman or the Speaker in relation to any question as to disqualification;", 32),
            cl("(d)", "the procedure for deciding any question referred to in sub-paragraph (1) of paragraph 6 including the procedure for any inquiry which may be made for the purpose of deciding such question.", 32),
        ],
        "notes": [
            "Tenth Schedule added by the Constitution (Fifty-second Amendment) Act, 1985, s. 6 (w.e.f. 1-3-1985).",
            "Paragraph 3 omitted by the Constitution (Ninety-first Amendment) Act, 2003, s. 5 (w.e.f. 1-1-2004).",
            "Paragraph 7 was held unconstitutional in Kihoto Hollohan v. Zachillhu (1992); it is printed as in the source.",
        ],
    }


def eleventh() -> dict:
    rows = [
        ("1", "Agriculture, including agricultural extension."),
        ("2", "Land improvement, implementation of land reforms, land consolidation and soil conservation."),
        ("3", "Minor irrigation, water management and watershed development."),
        ("4", "Animal husbandry, dairying and poultry."),
        ("5", "Fisheries."),
        ("6", "Social forestry and farm forestry."),
        ("7", "Minor forest produce."),
        ("8", "Small scale industries, including food processing industries."),
        ("9", "Khadi, village and cottage industries."),
        ("10", "Rural housing."),
        ("11", "Drinking water."),
        ("12", "Fuel and fodder."),
        ("13", "Roads, culverts, bridges, ferries, waterways and other means of communication."),
        ("14", "Rural electrification, including distribution of electricity."),
        ("15", "Non-conventional energy sources."),
        ("16", "Poverty alleviation programme."),
        ("17", "Education, including primary and secondary schools."),
        ("18", "Technical training and vocational education."),
        ("19", "Adult and non-formal education."),
        ("20", "Libraries."),
        ("21", "Cultural activities."),
        ("22", "Markets and fairs."),
        ("23", "Health and sanitation, including hospitals, primary health centres and dispensaries."),
        ("24", "Family welfare."),
        ("25", "Women and child development."),
        ("26", "Social welfare, including welfare of the handicapped and mentally retarded."),
        ("27", "Welfare of the weaker sections, and in particular, of the Scheduled Castes and the Scheduled Tribes."),
        ("28", "Public distribution system."),
        ("29", "Maintenance of community assets."),
    ]
    return {
        "blocks": [two(rows)],
        "notes": [
            "Eleventh Schedule added by the Constitution (Seventy-third Amendment) Act, 1992, s. 4 (w.e.f. 24-4-1993).",
        ],
    }


def twelfth() -> dict:
    rows = [
        ("1", "Urban planning including town planning."),
        ("2", "Regulation of land-use and construction of buildings."),
        ("3", "Planning for economic and social development."),
        ("4", "Roads and bridges."),
        ("5", "Water supply for domestic, industrial and commercial purposes."),
        ("6", "Public health, sanitation conservancy and solid waste management."),
        ("7", "Fire services."),
        ("8", "Urban forestry, protection of the environment and promotion of ecological aspects."),
        ("9", "Safeguarding the interests of weaker sections of society, including the handicapped and mentally retarded."),
        ("10", "Slum improvement and upgradation."),
        ("11", "Urban poverty alleviation."),
        ("12", "Provision of urban amenities and facilities such as parks, gardens, playgrounds."),
        ("13", "Promotion of cultural, educational and aesthetic aspects."),
        ("14", "Burials and burial grounds; cremations, cremation grounds; and electric crematoriums."),
        ("15", "Cattle pounds; prevention of cruelty to animals."),
        ("16", "Vital statistics including registration of births and deaths."),
        ("17", "Public amenities including street lighting, parking lots, bus stops and public conveniences."),
        ("18", "Regulation of slaughter houses and tanneries."),
    ]
    return {
        "blocks": [two(rows)],
        "notes": [
            "Twelfth Schedule added by the Constitution (Seventy-fourth Amendment) Act, 1992, s. 4 (w.e.f. 1-6-1993).",
        ],
    }


def main() -> None:
    payload = {
        "first": first(),
        "second": second(),
        "third": third(),
        "fourth": fourth(),
        "fifth": fifth(),
        "sixth": sixth(),
        "seventh": seventh(),
        "eighth": eighth(),
        "ninth": ninth(),
        "tenth": tenth(),
        "eleventh": eleventh(),
        "twelfth": twelfth(),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
