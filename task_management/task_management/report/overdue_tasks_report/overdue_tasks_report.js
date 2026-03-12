frappe.query_reports["Overdue Tasks Report"] = {
    filters: [
        {fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee"},
        {fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department"},
        {fieldname: "priority", label: __("Priority"), fieldtype: "Select", options: "\nLow\nMedium\nHigh\nCritical"}
    ],
    formatter: function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (column.fieldname === "overdue_days") {
            const days = data.overdue_days || 0;
            const color = days > 14 ? "red" : days > 7 ? "orange" : "yellow";
            value = `<b style="color:var(--${color})">${days} days</b>`;
        }
        return value;
    }
};
