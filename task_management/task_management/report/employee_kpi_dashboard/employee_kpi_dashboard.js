frappe.query_reports["Employee KPI Dashboard"] = {
    filters: [
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
            reqd: 1,
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
            reqd: 1,
        },
        {
            fieldname: "employee",
            label: __("Employee"),
            fieldtype: "Link",
            options: "Employee",
        },
        {
            fieldname: "department",
            label: __("Department"),
            fieldtype: "Link",
            options: "Department",
        },
    ],
    formatter: function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (!data) return value;

        const gradeColors = {"A+": "green", "A": "green", "B": "blue", "C": "orange", "D": "red"};

        if (column.fieldname === "task_kpi_grade") {
            const c = gradeColors[data.task_kpi_grade] || "grey";
            return `<span class="badge badge-${c}">${data.task_kpi_grade || "—"}</span>`;
        }
        if (column.fieldname === "sales_kpi_grade") {
            if (!data.is_sales_dept) return `<span style="color:#aaa">—</span>`;
            const c = gradeColors[data.sales_kpi_grade] || "grey";
            return `<span class="badge badge-${c}">${data.sales_kpi_grade || "—"}</span>`;
        }
        if (column.fieldname === "sales_kpi_score" && !data.is_sales_dept) {
            return `<span style="color:#aaa">—</span>`;
        }
        if (column.fieldname === "period_achievement" && !data.is_sales_dept) {
            return `<span style="color:#aaa">—</span>`;
        }
        if (column.fieldname === "overall_achievement" && !data.is_sales_dept) {
            return `<span style="color:#aaa">—</span>`;
        }
        return value;
    }
};
