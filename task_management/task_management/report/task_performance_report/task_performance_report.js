frappe.query_reports["Task Performance Report"] = {
    filters: [
        {fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.get_today(), -1)},
        {fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today()},
        {fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee"},
        {fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department"},
        {fieldname: "status", label: __("Status"), fieldtype: "Select", options: "\nOpen\nIn Progress\nPending Review\nCompleted\nCancelled\nOverdue"},
        {fieldname: "priority", label: __("Priority"), fieldtype: "Select", options: "\nLow\nMedium\nHigh\nCritical"},
        {fieldname: "category", label: __("Category"), fieldtype: "Link", options: "Task Category"}
    ],
    formatter: function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (column.fieldname === "status") {
            const colors = {"Completed": "green", "Overdue": "red", "In Progress": "blue", "Open": "grey", "Cancelled": "dark"};
            const color = colors[data.status] || "grey";
            value = `<span class="badge badge-${color}">${data.status}</span>`;
        }
        if (column.fieldname === "priority") {
            const colors = {"Critical": "red", "High": "orange", "Medium": "blue", "Low": "grey"};
            const color = colors[data.priority] || "grey";
            value = `<span style="color:var(--${color})">${data.priority}</span>`;
        }
        if (column.fieldname === "on_time") {
            value = data.on_time ? '✅' : (data.status === "Completed" ? '❌' : '—');
        }
        return value;
    }
};
