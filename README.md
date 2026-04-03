# Task Management with KPI Evaluation — ERPNext Module

## Features
- Managers create and assign tasks to employees with deadlines and priority
- Employees add updates/progress logs on tasks
- Manager marks tasks as Completed
- Auto KPI evaluation: on-time completion rate, total tasks, overdue, avg completion time
- KPI Summary per employee per period (Monthly/Quarterly/Yearly)
- Reports: Task Performance, Employee KPI Dashboard, Overdue Tasks

## Installation
```bash
bench get-app task_management https://github.com/yourorg/task_management
bench --site your-site.local install-app task_management
bench --site your-site.local migrate
```

## Roles
- **Task Manager** – Create tasks, change status, view all reports
- **Task Employee** – View assigned tasks, add updates

## KPI Scoring
| Metric | Weight |
|--------|--------|
| On-Time Completion Rate | 50% |
| Task Completion Rate | 30% |
| Avg Days to Complete | 20% |
