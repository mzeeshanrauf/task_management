import frappe
import calendar
from frappe.model.document import Document


class TaskKPISummary(Document):
    def before_save(self):
        self.set_employee_name()

    def set_employee_name(self):
        if self.employee and not self.employee_name:
            self.employee_name = frappe.db.get_value("Employee", self.employee, "employee_name")
        if self.employee and not self.department:
            self.department = frappe.db.get_value("Employee", self.employee, "department")
