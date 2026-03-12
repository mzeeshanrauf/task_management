import frappe
from frappe import _
from frappe.utils import today

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {"label": _("Task"), "fieldname": "name", "fieldtype": "Link", "options": "Employee Task", "width": 130},
        {"label": _("Title"), "fieldname": "task_title", "fieldtype": "Data", "width": 200},
        {"label": _("Employee"), "fieldname": "assigned_to_name", "fieldtype": "Data", "width": 150},
        {"label": _("Department"), "fieldname": "assigned_to_department", "fieldtype": "Link", "options": "Department", "width": 130},
        {"label": _("Priority"), "fieldname": "priority", "fieldtype": "Data", "width": 90},
        {"label": _("Due Date"), "fieldname": "due_date", "fieldtype": "Date", "width": 100},
        {"label": _("Overdue by (Days)"), "fieldname": "overdue_days", "fieldtype": "Int", "width": 130},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
        {"label": _("Progress %"), "fieldname": "completion_percentage", "fieldtype": "Percent", "width": 100},
        {"label": _("Assigned By"), "fieldname": "assigned_by_name", "fieldtype": "Data", "width": 140},
    ]

def get_data(filters):
    # Only draft tasks (docstatus=0) that are past due — submitted=completed, cancelled=excluded
    conditions = "AND t.due_date < %(today)s AND t.docstatus = 0 AND t.status NOT IN ('Cancelled')"
    args = {"today": today()}
    if filters:
        if filters.get("employee"):
            conditions += " AND t.assigned_to = %(employee)s"
            args["employee"] = filters["employee"]
        if filters.get("department"):
            conditions += " AND t.assigned_to_department = %(department)s"
            args["department"] = filters["department"]
        if filters.get("priority"):
            conditions += " AND t.priority = %(priority)s"
            args["priority"] = filters["priority"]

    return frappe.db.sql(f"""
        SELECT t.name, t.task_title, t.assigned_to_name, t.assigned_to_department,
               t.priority, t.due_date, t.overdue_days, t.status,
               t.completion_percentage, t.assigned_by_name
        FROM `tabEmployee Task` t
        WHERE 1=1 {conditions}
        ORDER BY t.overdue_days DESC, t.priority DESC
    """, args, as_dict=1)
