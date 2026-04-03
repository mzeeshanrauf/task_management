import frappe
from frappe import _
from frappe.utils import getdate, today
import calendar

MONTH_NAMES = {
    1:"January", 2:"February", 3:"March",    4:"April",
    5:"May",     6:"June",     7:"July",      8:"August",
    9:"September",10:"October",11:"November",12:"December"
}
MONTH_SHORT = {
    1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
    7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"
}


def execute(filters=None):
    filters     = filters or {}
    year        = int(filters.get("year") or getdate(today()).year)
    show_future = filters.get("show_future_months")
    today_date  = getdate(today())

    # Fiscal year name
    fy_row = frappe.db.sql("""
        SELECT name FROM `tabFiscal Year`
        WHERE %(d)s BETWEEN year_start_date AND year_end_date AND disabled=0
        LIMIT 1
    """, {"d": f"{year}-01-01"}, as_dict=1)
    fy_name = fy_row[0].name if fy_row else str(year)

    # Get all active sales persons with employee link
    sales_persons = frappe.db.sql("""
        SELECT sp.name AS sales_person
        FROM `tabSales Person` sp
        WHERE sp.enabled = 1
          AND (
            (sp.custom_user IS NOT NULL AND sp.custom_user != '')
            OR (sp.employee IS NOT NULL AND sp.employee != '')
          )
    """, as_dict=1)

    if not sales_persons:
        return get_columns(), [], None, None, []

    # Get annual target + distribution per sales person
    sp_targets = {}
    total_annual = 0.0
    for sp in sales_persons:
        t_filters = {"parent": sp.sales_person, "parenttype": "Sales Person", "fiscal_year": fy_name}
        rows = frappe.db.get_all("Target Detail",
            filters=t_filters,
            fields=["target_amount", "distribution_id"])
        rows = [r for r in rows if float(r.target_amount or 0) > 0]
        annual  = sum(float(r.target_amount or 0) for r in rows)
        dist_id = rows[0].distribution_id if rows else None
        sp_targets[sp.sales_person] = {"annual": annual, "dist_id": dist_id}
        total_annual += annual

    # Build monthly data
    data       = []
    cum_target = 0.0
    cum_actual = 0.0

    for month in range(1, 13):
        month_name  = MONTH_NAMES[month]
        month_label = f"{MONTH_SHORT[month]} {year}"
        is_future   = (year > today_date.year) or \
                      (year == today_date.year and month > today_date.month)

        if is_future and not show_future:
            continue

        # Sum monthly target across all sales persons
        monthly_target = 0.0
        for sp in sales_persons:
            annual  = sp_targets[sp.sales_person]["annual"]
            dist_id = sp_targets[sp.sales_person]["dist_id"]
            if dist_id:
                dist = frappe.db.get_all("Monthly Distribution Percentage",
                    filters={"parent": dist_id, "month": month_name},
                    fields=["percentage_allocation"], limit=1)
                pct = float(dist[0].percentage_allocation or 8.333) / 100 if dist else (1/12)
            else:
                pct = 1 / 12
            monthly_target += annual * pct

        # Sum monthly actual across all sales persons
        if not is_future:
            month_end = calendar.monthrange(year, month)[1]
            res = frappe.db.sql("""
                SELECT COALESCE(SUM(st.allocated_amount), 0) AS total
                FROM `tabSales Order` so
                INNER JOIN `tabSales Team` st
                    ON st.parent = so.name AND st.parenttype = 'Sales Order'
                WHERE so.docstatus = 1
                  AND so.transaction_date BETWEEN %(fd)s AND %(td)s
            """, {
                "fd": f"{year}-{month:02d}-01",
                "td": f"{year}-{month:02d}-{month_end:02d}",
            }, as_dict=1)
            monthly_actual = float(res[0].total or 0) if res else 0.0
        else:
            monthly_actual = 0.0

        cum_target += monthly_target
        if not is_future:
            cum_actual += monthly_actual

        monthly_ach = round(monthly_actual / monthly_target * 100, 1) \
                      if (monthly_target > 0 and not is_future) else 0.0
        cum_ach     = round(cum_actual / cum_target * 100, 1) \
                      if (cum_target > 0 and not is_future) else 0.0
        gap         = round(cum_actual - cum_target, 2) if not is_future else None

        data.append({
            "month_label":        month_label,
            "monthly_target":     round(monthly_target, 2),
            "monthly_actual":     round(monthly_actual, 2) if not is_future else None,
            "monthly_ach_pct":    monthly_ach,
            "cumulative_target":  round(cum_target, 2),
            "cumulative_actual":  round(cum_actual, 2) if not is_future else None,
            "cumulative_ach_pct": cum_ach,
            "gap":                gap,
            "is_future":          1 if is_future else 0,
        })

    chart   = get_chart(data)
    summary = get_summary(data, total_annual)
    return get_columns(), data, None, chart, summary


def get_columns():
    return [
        {"fieldname": "month_label",        "label": _("Month"),               "fieldtype": "Data",     "width": 100},
        {"fieldname": "monthly_target",     "label": _("Monthly Target"),      "fieldtype": "Currency", "width": 140},
        {"fieldname": "monthly_actual",     "label": _("Monthly Actual"),      "fieldtype": "Currency", "width": 140},
        {"fieldname": "monthly_ach_pct",    "label": _("Monthly Ach %"),       "fieldtype": "Percent",  "width": 120},
        {"fieldname": "cumulative_target",  "label": _("Cumulative Target"),   "fieldtype": "Currency", "width": 150},
        {"fieldname": "cumulative_actual",  "label": _("Cumulative Actual"),   "fieldtype": "Currency", "width": 150},
        {"fieldname": "cumulative_ach_pct", "label": _("Cumulative Ach %"),    "fieldtype": "Percent",  "width": 130},
        {"fieldname": "gap",                "label": _("Gap (Actual-Target)"), "fieldtype": "Currency", "width": 150},
    ]


def get_summary(data, total_annual):
    if not data:
        return []
    actual_rows = [d for d in data if not d.get("is_future")]
    if not actual_rows:
        return []

    last       = actual_rows[-1]
    ytd_target = last["cumulative_target"]
    ytd_actual = last["cumulative_actual"] or 0
    ytd_ach    = round(ytd_actual / ytd_target * 100, 1) if ytd_target else 0
    best       = max(actual_rows, key=lambda x: x.get("monthly_ach_pct") or 0)
    worst      = min(actual_rows, key=lambda x: x.get("monthly_ach_pct") or 0)
    ahead      = len([d for d in actual_rows if (d.get("gap") or 0) >= 0])

    return [
        {"label": _("Annual Target"),         "value": frappe.utils.fmt_money(total_annual), "indicator": "blue"},
        {"label": _("YTD Target"),             "value": frappe.utils.fmt_money(ytd_target),   "indicator": "blue"},
        {"label": _("YTD Actual"),             "value": frappe.utils.fmt_money(ytd_actual),   "indicator": "green"},
        {"label": _("YTD Achievement %"),      "value": f"{ytd_ach}%",                        "indicator": "green" if ytd_ach >= 75 else "orange"},
        {"label": _("Best Month"),             "value": f"{best['month_label']} ({best['monthly_ach_pct']}%)",   "indicator": "green"},
        {"label": _("Worst Month"),            "value": f"{worst['month_label']} ({worst['monthly_ach_pct']}%)", "indicator": "red"},
        {"label": _("Months Ahead of Target"), "value": ahead,                                "indicator": "green" if ahead > 0 else "orange"},
    ]


def get_chart(data):
    if not data:
        return None
    labels  = [d["month_label"]       for d in data]
    targets = [d["cumulative_target"] for d in data]
    actuals = [d["cumulative_actual"] if not d.get("is_future") else None for d in data]
    return {
        "data": {
            "labels": labels,
            "datasets": [
                {"name": _("Cumulative Target"), "values": targets},
                {"name": _("Cumulative Actual"), "values": actuals},
            ]
        },
        "type": "line",
        "height": 320,
        "colors": ["#1565c0", "#2e7d32"],
        "title": _("Cumulative Target vs Actual Sales"),
        "lineOptions": {"regionFill": 1}
    }
