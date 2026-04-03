import frappe
from frappe import _
from frappe.utils import getdate, today




def execute(filters=None):
    filters = filters or {}
    from_date = str(filters.get("from_date") or frappe.utils.add_months(today(), -1))
    to_date   = str(filters.get("to_date")   or today())
    columns  = get_columns()
    data     = get_data(filters, from_date, to_date)
    chart    = get_chart(data)
    summary  = get_summary(data)
    return columns, data, None, chart, summary


def get_columns():
    return [
        {"label": _("Employee"),          "fieldname": "employee",          "fieldtype": "Link",     "options": "Employee",   "width": 110},
        {"label": _("Name"),              "fieldname": "employee_name",     "fieldtype": "Data",                              "width": 150},
        {"label": _("Department"),        "fieldname": "department",        "fieldtype": "Link",     "options": "Department", "width": 130},
        # ── Task stats ──────────────────────────────────────────────────────
        {"label": _("Total Tasks"),       "fieldname": "total_tasks",       "fieldtype": "Int",                               "width": 85},
        {"label": _("Completed"),         "fieldname": "completed_tasks",   "fieldtype": "Int",                               "width": 85},
        {"label": _("Open"),              "fieldname": "open_tasks",        "fieldtype": "Int",                               "width": 65},
        {"label": _("On Time"),           "fieldname": "on_time_tasks",     "fieldtype": "Int",                               "width": 70},
        {"label": _("Overdue"),           "fieldname": "overdue_tasks",     "fieldtype": "Int",                               "width": 70},
        {"label": _("Completion %"),      "fieldname": "completion_rate",   "fieldtype": "Percent",                           "width": 100},
        {"label": _("On-Time %"),         "fieldname": "on_time_rate",      "fieldtype": "Percent",                           "width": 85},
        {"label": _("Quality (0-100)"),   "fieldname": "quality_score_100", "fieldtype": "Float",                             "width": 110},
        # ── Task KPI ────────────────────────────────────────────────────────
        {"label": _("Task KPI Score"),    "fieldname": "task_kpi_score",    "fieldtype": "Float",                             "width": 105},
        {"label": _("Task Grade"),        "fieldname": "task_kpi_grade",    "fieldtype": "Data",                              "width": 85},
        {"label": _("Task Rating"),       "fieldname": "task_kpi_rating",   "fieldtype": "Data",                              "width": 150},
        # ── Sales KPI ───────────────────────────────────────────────────────
        {"label": _("Period Target"),     "fieldname": "period_target",     "fieldtype": "Currency",                          "width": 110},
        {"label": _("Actual Sales"),      "fieldname": "actual_sales",      "fieldtype": "Currency",                          "width": 110},
        {"label": _("Period Ach %"),       "fieldname": "period_achievement",  "fieldtype": "Percent",                         "width": 105},
        {"label": _("Overall Ach %"),      "fieldname": "overall_achievement", "fieldtype": "Percent",                         "width": 105},
        {"label": _("Sales KPI Score"),    "fieldname": "sales_kpi_score",     "fieldtype": "Float",                           "width": 110},
        {"label": _("Sales Grade"),       "fieldname": "sales_kpi_grade",   "fieldtype": "Data",                              "width": 85},
        {"label": _("Sales Rating"),      "fieldname": "sales_kpi_rating",  "fieldtype": "Data",                              "width": 150},
    ]


GRADE_SCALE = [(90,"A+","Outstanding"),(75,"A","Exceeds Expectations"),
               (60,"B","Meets Expectations"),(40,"C","Needs Improvement"),(0,"D","Unsatisfactory")]

def get_grade(s):
    for t,g,_ in GRADE_SCALE:
        if s >= t: return g
    return "D"

def get_rating(s):
    for t,_,r in GRADE_SCALE:
        if s >= t: return r
    return "Unsatisfactory"


def get_data(filters, from_date, to_date):
    from task_management.task_management.doctype.employee_task.employee_task import (
        is_sales_department, get_sales_target_achievement
    )

    # ── Build employee conditions ────────────────────────────────────────────
    emp_conditions = "WHERE e.status = 'Active'"
    emp_args = {}
    if filters.get("employee"):
        emp_conditions += " AND e.name = %(employee)s"
        emp_args["employee"] = filters["employee"]
    if filters.get("department"):
        emp_conditions += " AND e.department = %(department)s"
        emp_args["department"] = filters["department"]

    employees = frappe.db.sql(f"""
        SELECT e.name, e.employee_name, e.department, e.user_id
        FROM `tabEmployee` e
        {emp_conditions}
        ORDER BY e.department, e.employee_name
    """, emp_args, as_dict=1)

    result = []
    for emp in employees:
        # ── Task stats for this employee in date range ───────────────────────
        task_rows = frappe.db.sql("""
            SELECT
                COUNT(*)                                                                AS total_tasks,
                SUM(CASE WHEN docstatus=1 AND status='Completed' THEN 1 ELSE 0 END)    AS completed_tasks,
                SUM(CASE WHEN docstatus=1 AND status IN ('Open','In Progress','Pending Review') THEN 1 ELSE 0 END) AS open_tasks,
                SUM(CASE WHEN docstatus=1 AND status='Completed' AND on_time=1 THEN 1 ELSE 0 END) AS on_time_tasks,
                SUM(CASE WHEN is_overdue=1 THEN 1 ELSE 0 END)                          AS overdue_tasks,
                AVG(CASE WHEN quality_score='5 - Excellent'     THEN 5
                         WHEN quality_score='4 - Good'          THEN 4
                         WHEN quality_score='3 - Average'       THEN 3
                         WHEN quality_score='2 - Below Average' THEN 2
                         WHEN quality_score='1 - Poor'          THEN 1
                         ELSE NULL END)                                                 AS avg_quality
            FROM `tabEmployee Task`
            WHERE assigned_to = %(emp)s
              AND docstatus != 2
              AND start_date BETWEEN %(from_date)s AND %(to_date)s
        """, {"emp": emp.name, "from_date": from_date, "to_date": to_date}, as_dict=1)

        t = task_rows[0] if task_rows else {}
        total      = int(t.total_tasks     or 0)
        completed  = int(t.completed_tasks or 0)
        open_t     = int(t.open_tasks      or 0)
        on_time_t  = int(t.on_time_tasks   or 0)
        overdue_t  = int(t.overdue_tasks   or 0)
        avg_q      = float(t.avg_quality   or 0)

        completion_rate   = round((completed / total    * 100) if total     else 0, 1)
        on_time_rate      = round((on_time_t / completed * 100) if completed else 0, 1)
        quality_score_100 = round(((avg_q - 1) / 4 * 100)       if avg_q    else 0, 1)

        # ── Task KPI — blank if no tasks at all ──────────────────────────────
        has_tasks = total > 0
        task_kpi = round(min(
            completion_rate   * 0.40 +
            on_time_rate      * 0.30 +
            quality_score_100 * 0.30,
            100
        ), 2) if has_tasks else 0.0

        # ── Sales KPI ────────────────────────────────────────────────────────
        dept = emp.department or ""
        period_target = actual_sales = period_achievement = overall_achievement = sales_kpi = 0.0
        annual_target = overall_actual = 0.0
        sales_grade = sales_rating = ""
        is_sales = is_sales_department(dept)

        if is_sales:
            period_target, actual_sales, period_achievement, annual_target, overall_actual, overall_achievement = \
                get_sales_target_achievement(emp.name, emp.user_id, from_date, to_date)
            sales_kpi    = round(min(period_achievement, 100), 2)
            sales_grade  = get_grade(sales_kpi) if annual_target > 0 else ""
            sales_rating = get_rating(sales_kpi) if annual_target > 0 else ""

        result.append({
            "employee":             emp.name,
            "employee_name":        emp.employee_name or "",
            "department":           dept,
            "is_sales_dept":        1 if is_sales else 0,
            "total_tasks":          total,
            "completed_tasks":      completed,
            "open_tasks":           open_t,
            "on_time_tasks":        on_time_t,
            "overdue_tasks":        overdue_t,
            "completion_rate":      completion_rate,
            "on_time_rate":         on_time_rate,
            "quality_score_100":    quality_score_100,
            "task_kpi_score":       task_kpi,
            "task_kpi_grade":       get_grade(task_kpi) if has_tasks else "",
            "task_kpi_rating":      get_rating(task_kpi) if has_tasks else "",
            "period_target":        round(period_target, 2),
            "actual_sales":         round(actual_sales, 2),
            "period_achievement":   round(period_achievement, 1) if is_sales else 0,
            "overall_achievement":  round(overall_achievement, 1) if is_sales else 0,
            "target_achievement":   round(period_achievement, 1) if is_sales else 0,
            "sales_kpi_score":      sales_kpi,
            "sales_kpi_grade":      sales_grade,
            "sales_kpi_rating":     sales_rating,
        })

    return result


def get_summary(data):
    if not data:
        return []
    sales_emps   = [d for d in data if d.get("is_sales_dept")]
    non_sales    = [d for d in data if not d.get("is_sales_dept")]

    avg_task_kpi  = round(sum(d["task_kpi_score"] for d in data) / len(data), 1) if data else 0
    avg_sales_kpi = round(sum(d["sales_kpi_score"] for d in sales_emps) / len(sales_emps), 1) if sales_emps else 0
    total_target  = sum(d["period_target"] for d in sales_emps)
    total_actual  = sum(d["actual_sales"]  for d in sales_emps)
    overall_ach   = round((total_actual / total_target * 100) if total_target else 0, 1)

    t_outstanding = len([d for d in data if d["task_kpi_score"] >= 90])
    t_exceeds     = len([d for d in data if 75 <= d["task_kpi_score"] < 90])
    t_meets       = len([d for d in data if 60 <= d["task_kpi_score"] < 75])
    t_below       = len([d for d in data if d["task_kpi_score"] < 60])

    return [
        {"label": _("Total Employees"),    "value": len(data),                                   "indicator": "blue"},
        {"label": _("Avg Task KPI"),        "value": avg_task_kpi,                                "indicator": "blue"},
        {"label": _("Outstanding Task"),    "value": t_outstanding,                               "indicator": "green"},
        {"label": _("Meets+ Task"),         "value": t_exceeds + t_meets,                         "indicator": "green"},
        {"label": _("Below Task"),          "value": t_below,                                     "indicator": "red"},
        {"label": _("Sales Employees"),     "value": len(sales_emps),                             "indicator": "blue"},
        {"label": _("Avg Sales KPI"),       "value": avg_sales_kpi,                               "indicator": "blue"},
        {"label": _("Overall SO Ach %"),    "value": f"{overall_ach}%",                           "indicator": "green" if overall_ach >= 75 else "orange"},
        {"label": _("Total Actual Sales"),  "value": frappe.utils.fmt_money(total_actual),        "indicator": "green"},
    ]


def get_chart(data):
    if not data:
        return None
    top = sorted(data, key=lambda x: x["task_kpi_score"], reverse=True)[:12]
    datasets = [{"name": _("Task KPI Score"), "values": [d["task_kpi_score"] for d in top]}]
    if any(d.get("is_sales_dept") for d in top):
        datasets.append({"name": _("Sales KPI Score"), "values": [d["sales_kpi_score"] for d in top]})
    return {
        "data": {
            "labels":   [d["employee_name"] or d["employee"] for d in top],
            "datasets": datasets,
        },
        "type":   "bar",
        "height": 300,
        "colors": ["#1565c0", "#2e7d32"],
        "title":  _("Employee KPI Scores"),
    }
