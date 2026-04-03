import frappe
from frappe.model.document import Document

class DepartmentTaskManager(Document):
    def validate(self):
        self.validate_no_duplicate_managers()

    def validate_no_duplicate_managers(self):
        seen = []
        for row in (self.managers_section or []):
            if row.manager in seen:
                frappe.throw(f"Manager {row.manager_name} is listed more than once.")
            seen.append(row.manager)
