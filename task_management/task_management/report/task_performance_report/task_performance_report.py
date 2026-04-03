import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"fieldname": "employee",        "label": _("Employee ID"),      "fieldtype": "Link",    "options": "Employee", "width": 110},
        {"fieldname": "employee_name",   "label": _("Employee Name"),    "fieldtype": "Data",    "width": 150},
        {"fieldname": "department",      "label": _("Department"),       "fieldtype": "Data",    "width": 130},
        {"fieldname": "total_tasks",     "label": _("Total"),            "fieldtype": "Int",     "width": 65},
        {"fieldname": "open_tasks",      "label": _("Open"),             "fieldtype": "Int",     "width": 65},
        {"fieldname": "completed_tasks", "label": _("Completed"),        "fieldtype": "Int",     "width": 85},
        {"fieldname": "on_time",         "label": _("On Time"),          "fieldtype": "Int",     "width": 75},
        {"fieldname": "overdue_tasks",   "label": _("Overdue"),          "fieldtype": "Int",     "width": 75},
        {"fieldname": "completion_rate", "label": _("Completion %"),     "fieldtype": "Percent", "width": 105},
        {"fieldname": "on_time_rate",    "label": _("On-Time %"),        "fieldtype": "Percent", "width": 90},
        {"fieldname": "quality_score",   "label": _("Avg Quality"),      "fieldtype": "Float",   "width": 95},
        {"fieldname": "task_kpi_score",  "label": _("Task KPI"),         "fieldtype": "Float",   "width": 85},
        {"fieldname": "task_kpi_grade",  "label": _("Task Grade"),       "fieldtype": "Data",    "width": 85},
        {"fieldname": "sales_target",    "label": _("Sales Target"),     "fieldtype": "Currency","width": 110},
        {"fieldname": "actual_sales",    "label": _("Actual Sales"),     "fieldtype": "Currency","width": 110},
        {"fieldname": "target_ach",      "label": _("Target Ach %"),     "fieldtype": "Percent", "width": 100},
        {"fieldname": "sales_kpi_score", "label": _("Sales KPI"),        "fieldtype": "Float",   "width": 85},
        {"fieldname": "sales_kpi_grade", "label": _("Sales Grade"),      "fieldtype": "Data",    "width": 90},
    ]


def get_data(filters):
    conditions = "WHERE t.docstatus != 2"
    args = {}

    if filters.get("from_date"):
        conditions += " AND t.start_date >= %(from_date)s"
        args["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions += " AND t.start_date <= %(to_date)s"
        args["to_date"] = filters["to_date"]
    if filters.get("department"):
        conditions += " AND t.assigned_to_department = %(department)s"
        args["department"] = filters["department"]
    if filters.get("employee"):
        conditions += " AND t.assigned_to = %(employee)s"
        args["employee"] = filters["employee"]
    if filters.get("priority"):
        conditions += " AND t.priority = %(priority)s"
        args["priority"] = filters["priority"]
    if filters.get("category"):
        conditions += " AND t.category = %(category)s"
        args["category"] = filters["category"]
    if filters.get("status"):
        if filters["status"] == "Completed":
            conditions += " AND t.status = 'Completed' AND t.docstatus = 1"
        elif filters["status"] in ("Open", "In Progress", "Pending Review"):
            conditions += " AND t.status IN ('Open','In Progress','Pending Review') AND t.docstatus = 1"
        else:
            conditions += " AND t.status = %(status)s"
            args["status"] = filters["status"]

    rows = frappe.db.sql(f"""
        SELECT
            t.assigned_to                                                               AS employee,
            t.assigned_to_name                                                          AS employee_name,
            t.assigned_to_department                                                    AS department,
            COUNT(*)                                                                    AS total_tasks,
            SUM(CASE WHEN t.docstatus=1 AND t.status IN ('Open','In Progress','Pending Review') THEN 1 ELSE 0 END) AS open_tasks,
            SUM(CASE WHEN t.status='Completed' AND t.docstatus=1 THEN 1 ELSE 0 END)    AS completed_tasks,
            SUM(CASE WHEN t.status='Completed' AND t.docstatus=1 AND t.on_time=1 THEN 1 ELSE 0 END) AS on_time,
            SUM(CASE WHEN t.is_overdue=1 THEN 1 ELSE 0 END)                            AS overdue_tasks,
            AVG(CASE WHEN t.quality_score='5 - Excellent'     THEN 5
                     WHEN t.quality_score='4 - Good'          THEN 4
                     WHEN t.quality_score='3 - Average'       THEN 3
                     WHEN t.quality_score='2 - Below Average' THEN 2
                     WHEN t.quality_score='1 - Poor'          THEN 1
                     ELSE NULL END)                                                     AS avg_quality
        FROM `tabEmployee Task` t
        {conditions}
        GROUP BY t.assigned_to, t.assigned_to_name, t.assigned_to_department
        ORDER BY completed_tasks DESC
    """, args, as_dict=1)

    from task_management.task_management.doctype.employee_task.employee_task import (
        get_rating, get_grade, is_sales_department, get_sales_target_achievement
    )

    result = []
    for r in rows:
        total      = r.total_tasks or 0
        completed  = r.completed_tasks or 0
        on_time    = r.on_time or 0
        overdue    = r.overdue_tasks or 0
        open_t     = r.open_tasks or 0
        avg_q      = float(r.avg_quality or 0)

        completion_rate   = round((completed / total    * 100) if total     else 0, 1)
        on_time_rate      = round((on_time   / completed * 100) if completed else 0, 1)
        quality_score_100 = round(((avg_q - 1) / 4 * 100) if avg_q else 0, 1)

        # Task KPI — same for everyone, blank if no tasks
        has_tasks = total > 0
        task_kpi = round(min(
            completion_rate   * 0.40 +
            on_time_rate      * 0.30 +
            quality_score_100 * 0.30,
            100
        ), 2) if has_tasks else 0.0

        # Sales KPI — sales dept only
        dept = r.department or ""
        sales_target = actual_sales = target_ach = overall_ach = sales_kpi = 0.0
        sales_grade = ""

        if is_sales_department(dept):
            emp_user = frappe.db.get_value("Employee", r.employee, "user_id")
            sales_target, actual_sales, target_ach, annual_t, overall_s, overall_ach = \
                get_sales_target_achievement(r.employee, emp_user,
                    filters.get("from_date"), filters.get("to_date"))
            sales_kpi   = round(min(target_ach, 100), 2)
            sales_grade = get_grade(sales_kpi) if sales_kpi > 0 else ""

        result.append({
            "employee":        r.employee,
            "employee_name":   r.employee_name,
            "department":      dept,
            "total_tasks":     total,
            "open_tasks":      open_t,
            "completed_tasks": completed,
            "on_time":         on_time,
            "overdue_tasks":   overdue,
            "completion_rate": completion_rate,
            "on_time_rate":    on_time_rate,
            "quality_score":   round(avg_q, 2),
            "task_kpi_score":  task_kpi,
            "task_kpi_grade":  get_grade(task_kpi) if has_tasks else "",
            "sales_target":    round(sales_target, 2),
            "actual_sales":    round(actual_sales, 2),
            "target_ach":      round(target_ach, 1),
            "overall_ach":     round(overall_ach, 1),
            "sales_kpi_score": sales_kpi,
            "sales_kpi_grade": sales_grade,
        })

    return result
