"""Admin-controlled academic hierarchy: Branch > Department > Year > Section.

Only Admin routes call the mutating functions. Students and faculty only ever *select*
existing, active rows (validated by `resolve_section`)."""
import re

from models import academic_queries as aq
from models import admin_queries

DEFAULT_BRANCH = "CSE"
DEFAULT_DEPARTMENTS = ["AIML", "AIDE", "GenAI", "Cybersecurity", "Blockchain", "IoT"]
DEFAULT_YEARS = 4
DEFAULT_SECTIONS = ["A", "B", "C"]

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 &.\-]{0,39}$")
SECTION_RE = re.compile(r"^[A-Za-z]$")  # simple labels only: A, B, C ... (never "3A")
YEAR_RE = re.compile(r"^([1-9])(?:st|nd|rd|th)? ?(?:year)?$", re.IGNORECASE)
_ORDINAL = {1: "1st", 2: "2nd", 3: "3rd"}


class AcademicError(Exception):
    pass


class AcademicInUseError(AcademicError):
    """The item still has students or faculty assignments, so it cannot be deleted (API: 409 ``in_use``)."""


def year_label(number):
    return f"{_ORDINAL.get(number, f'{number}th')} Year"


def normalize_year(text):
    """'3', '3rd', '3rd year' -> ('3rd Year', 3). Raises AcademicError otherwise."""
    m = YEAR_RE.match((text or "").strip())
    if not m:
        raise AcademicError("Year must look like '1st Year', '2nd Year', '3rd Year' ... (1 to 9).")
    number = int(m.group(1))
    return year_label(number), number


def normalize_section(text):
    text = (text or "").strip()
    if not SECTION_RE.match(text):
        raise AcademicError("Section must be a single letter label such as A, B or C.")
    return text.upper()


def _clean_name(text, what):
    text = " ".join((text or "").split())
    if not NAME_RE.match(text):
        raise AcademicError(f"{what} name must be 1-40 characters (letters, digits, spaces, & . -).")
    return text


# ---------- seeding / legacy backfill ----------

def seed_default_structure():
    """First start only: create CSE with its six departments, four years and sections A-C.
    Admin can then edit everything; this never runs again once any branch exists."""
    if aq.list_branches():
        return
    branch_id = aq.create_branch(DEFAULT_BRANCH)
    for dept in DEFAULT_DEPARTMENTS:
        dept_id = aq.create_department(branch_id, dept)
        for n in range(1, DEFAULT_YEARS + 1):
            year_id = aq.create_year(dept_id, year_label(n), n)
            for sec in DEFAULT_SECTIONS:
                aq.create_section(year_id, sec)


def _legacy_combo(branch, department, year, section):
    try:
        year_name, _ = normalize_year(year)
    except AcademicError:
        return None
    sec = re.sub(r"[^A-Za-z]", "", section or "")[-1:].upper()  # '3A' -> 'A'
    if not sec:
        return None
    return aq.find_combo_by_names((branch or "").strip(), (department or "").strip(), year_name, sec)


def backfill_legacy_data():
    """Link pre-hierarchy students / faculty_classes rows to the new tables when their
    free-text values match an Admin structure. Unmatched rows are left untouched and show
    up as 'Unmapped' for Admin review. Idempotent."""
    from models.database import get_db
    db = get_db()
    for st in db.execute("SELECT * FROM students WHERE section_id IS NULL").fetchall():
        combo = _legacy_combo(st["branch"], st["department"], st["year"], st["section"])
        if combo:
            aq.set_student_section(st["id"], combo["section_id"], combo["branch_name"],
                                   combo["department_name"], combo["year_name"], combo["section_name"])
    for fc in db.execute("SELECT * FROM faculty_classes").fetchall():
        combo = _legacy_combo(fc["branch"], fc["department"], fc["year"], fc["section"])
        if combo and not aq.get_assignment_for(fc["faculty_id"], combo["section_id"]):
            aq.upsert_assignment(fc["faculty_id"], combo["section_id"], None)


# ---------- read helpers ----------

def get_tree(active_only=True, with_usage=False):
    """Nested structure used by signup / request forms (JSON) and the admin tree view.

    ``with_usage=True`` (admin view) adds ``student_count`` (every student row linked below the node,
    removed registrations included), ``assignment_count`` (every faculty assignment row, active or not)
    and ``can_delete`` (both zero) to every node: exactly the rule ``delete_unused`` enforces."""
    usage = admin_queries.usage_by_section() if with_usage else {}

    def _finish(node, children):
        if with_usage:
            node["student_count"] = sum(c["student_count"] for c in children)
            node["assignment_count"] = sum(c["assignment_count"] for c in children)
            node["can_delete"] = not node["student_count"] and not node["assignment_count"]
        return node

    tree = []
    for b in aq.list_branches():
        if active_only and not b["is_active"]:
            continue
        b_node = {"id": b["id"], "name": b["name"], "is_active": bool(b["is_active"]), "departments": []}
        for d in aq.list_departments(b["id"]):
            if active_only and not d["is_active"]:
                continue
            d_node = {"id": d["id"], "name": d["name"], "is_active": bool(d["is_active"]), "years": []}
            for y in aq.list_years(d["id"]):
                if active_only and not y["is_active"]:
                    continue
                y_node = {"id": y["id"], "name": y["name"], "is_active": bool(y["is_active"]), "sections": []}
                for s in aq.list_sections(y["id"]):
                    if active_only and not s["is_active"]:
                        continue
                    s_node = {"id": s["id"], "name": s["name"], "is_active": bool(s["is_active"])}
                    if with_usage:
                        counts = usage.get(s["id"], (0, 0))
                        s_node["student_count"], s_node["assignment_count"] = counts
                        s_node["can_delete"] = not counts[0] and not counts[1]
                    y_node["sections"].append(s_node)
                if y_node["sections"] or not active_only:
                    d_node["years"].append(_finish(y_node, y_node["sections"]))
            if d_node["years"] or not active_only:
                b_node["departments"].append(_finish(d_node, d_node["years"]))
        if b_node["departments"] or not active_only:
            tree.append(_finish(b_node, b_node["departments"]))
    return tree


def resolve_section(section_id):
    """Validate a client-supplied section id against the Admin structure. Returns the combo row."""
    try:
        section_id = int(section_id)
    except (TypeError, ValueError):
        raise AcademicError("Please select your Branch, Department, Year and Section.")
    combo = aq.get_combo(section_id)
    if not combo or not combo["chain_active"]:
        raise AcademicError("The selected class does not exist. Please choose from the list.")
    return combo


def combo_label(combo):
    return f"{combo['branch_name']} → {combo['department_name']} → {combo['year_name']} → {combo['section_name']}"


# ---------- Admin mutations ----------

def add_branch(name):
    name = _clean_name(name, "Branch")
    if aq.get_branch_by_name(name):
        raise AcademicError(f"Branch '{name}' already exists.")
    return aq.create_branch(name)


def add_department(branch_id, name):
    if not aq.get_branch(branch_id):
        raise AcademicError("Branch not found.")
    name = _clean_name(name, "Department")
    if any(d["name"].lower() == name.lower() for d in aq.list_departments(branch_id)):
        raise AcademicError(f"Department '{name}' already exists in this branch.")
    return aq.create_department(branch_id, name)


def add_year(department_id, text):
    if not aq.get_department(department_id):
        raise AcademicError("Department not found.")
    name, number = normalize_year(text)
    if any(y["name"].lower() == name.lower() for y in aq.list_years(department_id)):
        raise AcademicError(f"{name} already exists in this department.")
    return aq.create_year(department_id, name, number)


def add_sections(year_id, text):
    """Accepts 'A', 'A,B,C' or 'A B C'. Returns the list of newly created labels."""
    if not aq.get_year(year_id):
        raise AcademicError("Year not found.")
    labels = [normalize_section(p) for p in re.split(r"[\s,;]+", (text or "").strip()) if p]
    if not labels:
        raise AcademicError("Enter at least one section label (A, B, C ...).")
    existing = {s["name"].upper() for s in aq.list_sections(year_id)}
    created = []
    for label in dict.fromkeys(labels):
        if label in existing:
            continue
        aq.create_section(year_id, label)
        created.append(label)
    if not created:
        raise AcademicError("Those sections already exist for this year.")
    return created


_LEVEL_GETTERS = {
    "branch": aq.get_branch, "department": aq.get_department, "year": aq.get_year, "section": aq.get_section,
}


def set_active(level, row_id, active):
    if level not in _LEVEL_GETTERS or not _LEVEL_GETTERS[level](row_id):
        raise AcademicError("Item not found.")
    aq.set_level_active(level, row_id, active)


def delete_unused(level, row_id):
    if level not in _LEVEL_GETTERS or not _LEVEL_GETTERS[level](row_id):
        raise AcademicError("Item not found.")
    if aq.count_students_under(level, row_id) or aq.count_assignments_under(level, row_id):
        raise AcademicInUseError(
            "This item has students or faculty assignments; deactivate it instead of deleting.")
    aq.delete_level(level, row_id)
