import frappe
from frappe import _
from frappe.utils import getdate, today, date_diff

GRADE_SCALE = [
    (90, "A+", "Outstanding"),
    (75, "A",  "Exceeds Expectations"),
    (60, "B",  "Meets Expectations"),
    (40, "C",  "Needs Improvement"),
    (0,  "D",  "Unsatisfactory"),
]

def get_grade(score):
    for t, g, _ in GRADE_SCALE:
        if score >= t: return g
    return "D"

def get_rating(score):
    for t, _, r in GRADE_SCALE:
        if score >= t: return r
    return "Unsatisfactory"





def get_months_in_range(from_date, to_date):
    """Return list of (year, month) tuples covered by the date range."""
    start = getdate(from_date)
    end   = getdate(to_date)
    months = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months

MONTH_NAMES = {
    1:"January",2:"February",3:"March",4:"April",5:"May",6:"June",
    7:"July",8:"August",9:"September",10:"October",11:"November",12:"December"
}

def get_period_target(annual_target, distribution_id, from_date, to_date):
    """
    Sum monthly targets for each month in the date range.
    Uses Monthly Distribution percentages if available, else equal 1/12 per month.
    """
    months = get_months_in_range(from_date, to_date)
    total  = 0.0

    for (year, month) in months:
        month_name = MONTH_NAMES[month]
        if distribution_id:
            dist = frappe.db.get_all(
                "Monthly Distribution Percentage",
                filters={"parent": distribution_id, "month": month_name},
                fields=["percentage_allocation"], limit=1
            )
            pct = float(dist[0].percentage_allocation or 8.333) / 100 if dist else (1/12)
        else:
            pct = 1 / 12
        total += annual_target * pct

    return total


def execute(filters=None):
    filters   = filters or {}
    from_date = str(filters.get("from_date") or f"{getdate(today()).year}-01-01")
    to_date   = str(filters.get("to_date")   or today())
    columns   = get_columns()
    data      = get_data(filters, from_date, to_date)
    chart     = get_chart(data)
    summary   = get_summary(data)
    return columns, data, None, chart, summary


def get_columns():
    return [
        {"fieldname": "sales_person",       "label": _("Sales Person"),        "fieldtype": "Link",     "options": "Sales Person", "width": 140},
        {"fieldname": "employee",           "label": _("Employee"),             "fieldtype": "Link",     "options": "Employee",     "width": 110},
        {"fieldname": "employee_name",      "label": _("Employee Name"),        "fieldtype": "Data",                                "width": 150},
        {"fieldname": "department",         "label": _("Department"),           "fieldtype": "Link",     "options": "Department",   "width": 120},
        {"fieldname": "period_label",       "label": _("Period"),               "fieldtype": "Data",                                "width": 120},
        {"fieldname": "annual_target",      "label": _("Annual Target"),        "fieldtype": "Currency",                            "width": 120},
        {"fieldname": "period_target",      "label": _("Period Target"),        "fieldtype": "Currency",                            "width": 120},
        {"fieldname": "so_count",           "label": _("SO Count"),             "fieldtype": "Int",                                 "width": 80},
        {"fieldname": "actual_sales",       "label": _("Actual Sales (SO)"),    "fieldtype": "Currency",                            "width": 130},
        {"fieldname": "period_achievement", "label": _("Period Achievement %"), "fieldtype": "Percent",                             "width": 140},
        {"fieldname": "overall_achievement","label": _("Overall Achievement %"),"fieldtype": "Percent",                             "width": 150},
        {"fieldname": "sales_kpi_score",    "label": _("Sales KPI Score"),      "fieldtype": "Float",                               "width": 115},
        {"fieldname": "sales_kpi_grade",    "label": _("Grade"),                "fieldtype": "Data",                                "width": 65},
        {"fieldname": "sales_kpi_rating",   "label": _("Rating"),               "fieldtype": "Data",                                "width": 160},
    ]


def get_data(filters, from_date, to_date):
    period_label = f"{from_date} → {to_date}"

    # Fiscal year for target lookup
    fy_row = frappe.db.sql("""
        SELECT name FROM `tabFiscal Year`
        WHERE %(ref)s BETWEEN year_start_date AND year_end_date AND disabled=0
        LIMIT 1
    """, {"ref": from_date}, as_dict=1)
    fy_name = fy_row[0].name if fy_row else None

    # Full year range for overall achievement
    if fy_name:
        fy_dates = frappe.db.sql("""
            SELECT year_start_date, year_end_date FROM `tabFiscal Year`
            WHERE name = %(fy)s
        """, {"fy": fy_name}, as_dict=1)
        fy_start = str(fy_dates[0].year_start_date) if fy_dates else f"{getdate(from_date).year}-01-01"
        fy_end   = str(fy_dates[0].year_end_date)   if fy_dates else f"{getdate(from_date).year}-12-31"
    else:
        fy_start = f"{getdate(from_date).year}-01-01"
        fy_end   = f"{getdate(from_date).year}-12-31"

    # Build sales person filters
    sp_conditions, sp_args = "", {}
    if filters.get("department"):
        sp_conditions += " AND e.department = %(department)s"
        sp_args["department"] = filters["department"]
    if filters.get("employee"):
        sp_conditions += " AND sp.employee = %(employee)s"
        sp_args["employee"] = filters["employee"]
    if filters.get("sales_person"):
        sp_conditions += " AND sp.name = %(sales_person)s"
        sp_args["sales_person"] = filters["sales_person"]

    sales_persons = frappe.db.sql(f"""
        SELECT sp.name AS sales_person, sp.employee, e.employee_name, e.department
        FROM `tabSales Person` sp
        LEFT JOIN `tabEmployee` e ON e.name = sp.employee
        WHERE sp.enabled = 1 AND sp.employee IS NOT NULL AND sp.employee != ''
        {sp_conditions}
        ORDER BY sp.name
    """, sp_args, as_dict=1)

    result = []
    for sp in sales_persons:
        # Annual target
        t_filters = {"parent": sp.sales_person, "parenttype": "Sales Person"}
        if fy_name:
            t_filters["fiscal_year"] = fy_name
        target_rows = frappe.db.get_all("Target Detail",
            filters=t_filters,
            fields=["target_amount", "distribution_id"])
        target_rows = [r for r in target_rows if float(r.target_amount or 0) > 0]

        annual_target = sum(float(r.target_amount or 0) for r in target_rows)

        # Period target — sum monthly targets for each month in range
        period_target = 0.0
        for row in target_rows:
            period_target += get_period_target(
                float(row.target_amount or 0),
                row.distribution_id,
                from_date, to_date
            )

        # Actual sales in selected period
        period_so = frappe.db.sql("""
            SELECT COUNT(DISTINCT so.name) AS so_count,
                   COALESCE(SUM(st.allocated_amount), 0) AS actual_sales
            FROM `tabSales Order` so
            INNER JOIN `tabSales Team` st
                ON st.parent = so.name AND st.parenttype = 'Sales Order'
                AND st.sales_person = %(sp)s
            WHERE so.docstatus = 1
              AND so.transaction_date BETWEEN %(from_date)s AND %(to_date)s
        """, {"sp": sp.sales_person, "from_date": from_date, "to_date": to_date}, as_dict=1)

        so_count     = int(period_so[0].so_count    or 0) if period_so else 0
        actual_sales = float(period_so[0].actual_sales or 0) if period_so else 0

        # Overall actual sales (full fiscal year)
        overall_so = frappe.db.sql("""
            SELECT COALESCE(SUM(st.allocated_amount), 0) AS actual_sales
            FROM `tabSales Order` so
            INNER JOIN `tabSales Team` st
                ON st.parent = so.name AND st.parenttype = 'Sales Order'
                AND st.sales_person = %(sp)s
            WHERE so.docstatus = 1
              AND so.transaction_date BETWEEN %(fy_start)s AND %(fy_end)s
        """, {"sp": sp.sales_person, "fy_start": fy_start, "fy_end": fy_end}, as_dict=1)
        overall_actual = float(overall_so[0].actual_sales or 0) if overall_so else 0

        # Period achievement = actual in period / period target
        period_achievement  = round(min((actual_sales  / period_target  * 100), 999), 1) if period_target  > 0 else 0.0
        # Overall achievement = full year actual / annual target
        overall_achievement = round(min((overall_actual / annual_target * 100), 999), 1) if annual_target > 0 else 0.0

        # Sales KPI = period achievement (capped at 100)
        sales_kpi_score = round(min(period_achievement, 100), 2)

        result.append({
            "sales_person":        sp.sales_person,
            "employee":            sp.employee,
            "employee_name":       sp.employee_name or "",
            "department":          sp.department or "",
            "period_label":        period_label,
            "annual_target":       round(annual_target, 2),
            "period_target":       round(period_target, 2),
            "so_count":            so_count,
            "actual_sales":        round(actual_sales, 2),
            "period_achievement":  period_achievement,
            "overall_achievement": overall_achievement,
            "sales_kpi_score":     sales_kpi_score,
            "sales_kpi_grade":     get_grade(sales_kpi_score) if annual_target > 0 else "",
            "sales_kpi_rating":    get_rating(sales_kpi_score) if annual_target > 0 else "",
        })

    return result


def get_summary(data):
    if not data:
        return []
    total_sp      = len(data)
    total_target  = sum(d["period_target"]       or 0 for d in data)
    total_actual  = sum(d["actual_sales"]        or 0 for d in data)
    avg_period    = round(sum(d["period_achievement"]  or 0 for d in data) / total_sp, 1) if total_sp else 0
    avg_overall   = round(sum(d["overall_achievement"] or 0 for d in data) / total_sp, 1) if total_sp else 0
    outstanding   = len([d for d in data if d["sales_kpi_score"] >= 90])
    exceeds       = len([d for d in data if 75 <= d["sales_kpi_score"] < 90])
    meets         = len([d for d in data if 60 <= d["sales_kpi_score"] < 75])
    below         = len([d for d in data if 0 < d["sales_kpi_score"] < 60])
    return [
        {"label": _("Sales Persons"),          "value": total_sp,                             "indicator": "blue"},
        {"label": _("Period Target"),           "value": frappe.utils.fmt_money(total_target), "indicator": "blue"},
        {"label": _("Actual Sales (Period)"),   "value": frappe.utils.fmt_money(total_actual), "indicator": "green"},
        {"label": _("Avg Period Achievement"),  "value": f"{avg_period}%",                     "indicator": "green" if avg_period >= 75 else "orange"},
        {"label": _("Avg Overall Achievement"), "value": f"{avg_overall}%",                    "indicator": "green" if avg_overall >= 75 else "orange"},
        {"label": _("Outstanding (A+)"),        "value": outstanding,                          "indicator": "green"},
        {"label": _("Exceeds (A)"),             "value": exceeds,                              "indicator": "green"},
        {"label": _("Meets (B)"),               "value": meets,                                "indicator": "orange"},
        {"label": _("Below (C/D)"),             "value": below,                                "indicator": "red"},
    ]


def get_chart(data):
    if not data:
        return None
    data_sorted = sorted(data, key=lambda x: x["actual_sales"], reverse=True)
    return {
        "data": {
            "labels": [d["employee_name"] or d["sales_person"] for d in data_sorted],
            "datasets": [
                {"name": _("Period Target"),  "values": [d["period_target"]       for d in data_sorted]},
                {"name": _("Actual Sales"),   "values": [d["actual_sales"]        for d in data_sorted]},
            ]
        },
        "type": "bar", "height": 300,
        "colors": ["#1565c0", "#2e7d32"],
        "title": _("Sales Target vs Actual (Period)")
    }
