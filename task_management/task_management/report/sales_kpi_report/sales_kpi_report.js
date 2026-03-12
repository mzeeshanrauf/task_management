frappe.query_reports["Sales KPI Report"] = {
    filters: [
        {
            fieldname: "filter_type",
            label: __("Filter By"),
            fieldtype: "Select",
            options: "Date Range\nQuarter\nYear",
            default: "Date Range",
            on_change: function() {
                const ft = frappe.query_report.get_filter_value("filter_type");
                // Date Range — show from/to, hide quarter/year
                frappe.query_report.toggle_filter_display("from_date", ft === "Date Range");
                frappe.query_report.toggle_filter_display("to_date",   ft === "Date Range");
                // Quarter — show quarter + year, hide from/to
                frappe.query_report.toggle_filter_display("quarter",   ft === "Quarter");
                frappe.query_report.toggle_filter_display("year",      ft === "Quarter" || ft === "Year");
            }
        },
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: frappe.datetime.year_start(),
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
            fieldname: "department",
            label: __("Department"),
            fieldtype: "Link",
            options: "Department",
        },
        {
            fieldname: "employee",
            label: __("Employee"),
            fieldtype: "Link",
            options: "Employee",
        },
        {
            fieldname: "sales_person",
            label: __("Sales Person"),
            fieldtype: "Link",
            options: "Sales Person",
        },
    ],
    formatter: function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (!data) return value;
        if (column.fieldname === "sales_kpi_grade") {
            const colors = {"A+": "green", "A": "green", "B": "blue", "C": "orange", "D": "red"};
            const color = colors[data.sales_kpi_grade] || "grey";
            value = `<span class="badge badge-${color}">${data.sales_kpi_grade || "—"}</span>`;
        }
        if (column.fieldname === "period_achievement") {
            const pct = parseFloat(data.period_achievement) || 0;
            const color = pct >= 100 ? "#2e7d32" : pct >= 75 ? "#1565c0" : pct >= 50 ? "#e65100" : "#c62828";
            const bar = `<div style="background:#eee;border-radius:4px;height:8px;margin-top:3px">
                <div style="background:${color};width:${Math.min(pct,100)}%;height:8px;border-radius:4px"></div></div>`;
            value = `<span style="color:${color};font-weight:bold">${pct.toFixed(1)}%</span>${bar}`;
        }
        if (column.fieldname === "overall_achievement") {
            const pct = parseFloat(data.overall_achievement) || 0;
            const color = pct >= 100 ? "#2e7d32" : pct >= 75 ? "#1565c0" : pct >= 50 ? "#e65100" : "#c62828";
            value = `<span style="color:${color};font-weight:bold">${pct.toFixed(1)}%</span>`;
        }
        return value;
    }
};
