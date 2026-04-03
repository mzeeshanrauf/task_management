frappe.query_reports["Sales Cumulative Report"] = {
    filters: [
        {
            fieldname: "year",
            label: __("Year"),
            fieldtype: "Int",
            default: new Date().getFullYear(),
            reqd: 1,
        },
        {
            fieldname: "show_future_months",
            label: __("Show Future Months"),
            fieldtype: "Check",
            default: 0,
        },
    ],
    formatter: function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (!data) return value;

        if (column.fieldname === "gap") {
            const raw = data.gap || 0;
            const color = raw >= 0 ? "#2e7d32" : "#c62828";
            const sign  = raw >= 0 ? "+" : "";
            return `<span style="color:${color};font-weight:600">${sign}${frappe.format(raw, {fieldtype:'Currency'})}</span>`;
        }
        if (column.fieldname === "monthly_ach_pct") {
            if (data.is_future) return `<span style="color:#aaa">—</span>`;
            const pct = parseFloat(data.monthly_ach_pct) || 0;
            const color = pct >= 100 ? "#2e7d32" : pct >= 75 ? "#1565c0" : pct >= 50 ? "#e65100" : "#c62828";
            const bar = `<div style="background:#eee;border-radius:4px;height:6px;margin-top:3px">
                <div style="background:${color};width:${Math.min(pct,100)}%;height:6px;border-radius:4px"></div></div>`;
            return `<span style="color:${color};font-weight:600">${pct.toFixed(1)}%</span>${bar}`;
        }
        if (column.fieldname === "cumulative_ach_pct") {
            if (data.is_future) return `<span style="color:#aaa">—</span>`;
            const pct = parseFloat(data.cumulative_ach_pct) || 0;
            const color = pct >= 100 ? "#2e7d32" : pct >= 75 ? "#1565c0" : pct >= 50 ? "#e65100" : "#c62828";
            return `<span style="color:${color};font-weight:600">${pct.toFixed(1)}%</span>`;
        }
        if (data.is_future && ["monthly_actual","cumulative_actual"].includes(column.fieldname)) {
            return `<span style="color:#aaa">—</span>`;
        }
        return value;
    }
};
