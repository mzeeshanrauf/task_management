frappe.query_reports["Employee KPI Dashboard"] = {
    filters: [
        {
            fieldname: "filter_type",
            label: __("Filter By"),
            fieldtype: "Select",
            options: "Date Range\nQuarter\nYear\nMonth",
            default: "Date Range",
            on_change: function() {
                const ft = frappe.query_report.get_filter_value("filter_type");
                frappe.query_report.toggle_filter_display("from_date", ft === "Date Range");
                frappe.query_report.toggle_filter_display("to_date",   ft === "Date Range");
                frappe.query_report.toggle_filter_display("quarter",   ft === "Quarter");
                frappe.query_report.toggle_filter_display("year",      ft === "Quarter" || ft === "Year");
                frappe.query_report.toggle_filter_display("month",     ft === "Month");
                frappe.query_report.toggle_filter_display("month_year",ft === "Month");
            }
        },
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
        },
        {
            fieldname: "quarter",
            label: __("Quarter"),
            fieldtype: "Select",
            options: "\nQ1 (Jan-Mar)\nQ2 (Apr-Jun)\nQ3 (Jul-Sep)\nQ4 (Oct-Dec)",
            hidden: 1,
        },
        {
            fieldname: "year",
            label: __("Year"),
            fieldtype: "Int",
            default: new Date().getFullYear(),
            hidden: 1,
        },
        {
            fieldname: "month",
            label: __("Month"),
            fieldtype: "Select",
            options: "\nJanuary\nFebruary\nMarch\nApril\nMay\nJune\nJuly\nAugust\nSeptember\nOctober\nNovember\nDecember",
            hidden: 1,
        },
        {
            fieldname: "month_year",
            label: __("Year"),
            fieldtype: "Int",
            default: new Date().getFullYear(),
            hidden: 1,
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
        if (column.fieldname === "target_achievement" && !data.is_sales_dept) {
            return `<span style="color:#aaa">—</span>`;
        }
        return value;
    }
};
