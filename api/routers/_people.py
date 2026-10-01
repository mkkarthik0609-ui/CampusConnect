"""Serializers shared by the faculty / chat / meetings / supporting routers (not a router itself)."""
from api.schemas import class_object_for_section, faculty_brief, profile_picture_url


class Cards:
    """Builds the student / faculty cards of the JSON API. One instance per request: it memoises the
    class object (branch -> department -> year -> section) of each section id."""

    def __init__(self):
        self._classes = {}

    def klass(self, section_id):
        if section_id not in self._classes:
            self._classes[section_id] = class_object_for_section(section_id)
        return self._classes[section_id]

    def student(self, *, id, usn, full_name, picture_path, section_id):
        """``{id, usn, full_name, profile_picture_url, class}`` (class is a class object or null)."""
        return {
            "id": id, "usn": usn, "full_name": full_name,
            "profile_picture_url": profile_picture_url(picture_path),
            "class": self.klass(section_id),
        }

    @staticmethod
    def faculty(*, id, faculty_code, department, full_name, picture_path):
        """``{id, faculty_code, department, full_name, profile_picture_url}``."""
        return faculty_brief({
            "id": id, "faculty_code": faculty_code, "department": department,
            "full_name": full_name, "profile_picture_path": picture_path,
        })
