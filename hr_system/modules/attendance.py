# -*- coding: utf-8 -*-
"""وحدة الحضور والانصراف: سجل يومي، تسجيل حضور/انصراف/غياب/إجازة، وتقرير شهري."""
from datetime import date, datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session

import db
from core import login_required, safe_date, valid_month, WEEKEND

bp = Blueprint("attendance", __name__, url_prefix="/attendance")
LATE_AFTER = "08:30"


def _day_arg(value):
    d = safe_date(value)
    return (d or date.today()).isoformat()


@bp.route("/")
@login_required
def index():
    conn = db.get_db()
    day = _day_arg(request.args.get("day"))
    rows = conn.execute(
        """
        SELECT e.id, e.full_name, e.initials, e.position, d.name AS dept,
               a.check_in, a.check_out, a.method, a.status
        FROM employees e JOIN departments d ON d.id = e.department_id
        LEFT JOIN attendance a ON a.employee_id = e.id AND a.day = ?
        WHERE e.status != 'منتهي' ORDER BY e.full_name
        """, (day,)).fetchall()
    counts = {"present": 0, "late": 0, "absent": 0, "leave": 0, "none": 0}
    for r in rows:
        counts[r["status"] or "none"] += 1
    is_weekend = safe_date(day).weekday() in WEEKEND
    return render_template("attendance/index.html", rows=rows, day=day, counts=counts,
                           is_weekend=is_weekend, today=date.today().isoformat())


@bp.route("/mark", methods=["POST"])
@login_required
def mark():
    conn = db.get_db()
    day = _day_arg(request.form.get("day"))
    action = request.form.get("action", "")
    emp_id = request.form.get("employee_id", "")
    back = redirect(url_for("attendance.index", day=day))
    if not emp_id.isdigit() or not conn.execute("SELECT 1 FROM employees WHERE id=?", (emp_id,)).fetchone():
        flash("الموظف غير موجود", "error")
        return back
    emp_id = int(emp_id)
    now = datetime.now().strftime("%H:%M")
    ex = conn.execute("SELECT * FROM attendance WHERE employee_id=? AND day=?", (emp_id, day)).fetchone()

    if action == "checkin":
        status = "late" if now > LATE_AFTER else "present"
        if ex:
            conn.execute("UPDATE attendance SET check_in=?, check_out=NULL, method='يدوي', status=? WHERE id=?",
                         (now, status, ex["id"]))
        else:
            conn.execute("INSERT INTO attendance (employee_id, day, check_in, method, status) VALUES (?,?,?,?,?)",
                         (emp_id, day, now, "يدوي", status))
    elif action == "checkout":
        if ex and ex["check_in"]:
            conn.execute("UPDATE attendance SET check_out=? WHERE id=?", (now, ex["id"]))
        else:
            flash("سجّل الحضور أولاً قبل الانصراف", "error")
            return back
    elif action in ("absent", "leave"):
        if ex:
            conn.execute("UPDATE attendance SET status=?, check_in=NULL, check_out=NULL, method=NULL WHERE id=?",
                         (action, ex["id"]))
        else:
            conn.execute("INSERT INTO attendance (employee_id, day, status) VALUES (?,?,?)", (emp_id, day, action))
    elif action == "reset":
        conn.execute("DELETE FROM attendance WHERE employee_id=? AND day=?", (emp_id, day))
    else:
        flash("إجراء غير معروف", "error")
        return back
    conn.commit()
    flash("تم تحديث سجل الحضور", "success")
    return back


@bp.route("/mark-all", methods=["POST"])
@login_required
def mark_all():
    """تسجيل حضور (08:00) لكل من ليس له سجل في اليوم المحدد."""
    conn = db.get_db()
    day = _day_arg(request.form.get("day"))
    emps = conn.execute(
        "SELECT id FROM employees WHERE status NOT IN ('منتهي','إجازة','موقوف') AND id NOT IN "
        "(SELECT employee_id FROM attendance WHERE day=?)", (day,)).fetchall()
    for e in emps:
        conn.execute("INSERT INTO attendance (employee_id, day, check_in, method, status) VALUES (?,?,?,?,?)",
                     (e["id"], day, "08:00", "يدوي", "present"))
    conn.commit()
    flash("تم تسجيل حضور %d موظف" % len(emps), "success")
    return redirect(url_for("attendance.index", day=day))


@bp.route("/report")
@login_required
def report():
    conn = db.get_db()
    month = valid_month(request.args.get("month"))
    rows = conn.execute(
        """
        SELECT e.id, e.full_name, e.initials, d.name AS dept,
          SUM(CASE WHEN a.status='present' THEN 1 ELSE 0 END) AS present,
          SUM(CASE WHEN a.status='late' THEN 1 ELSE 0 END) AS late,
          SUM(CASE WHEN a.status='absent' THEN 1 ELSE 0 END) AS absent,
          SUM(CASE WHEN a.status='leave' THEN 1 ELSE 0 END) AS leave
        FROM employees e JOIN departments d ON d.id = e.department_id
        LEFT JOIN attendance a ON a.employee_id = e.id AND a.day LIKE ?
        WHERE e.status != 'منتهي' GROUP BY e.id ORDER BY e.full_name
        """, (month + "-%",)).fetchall()
    return render_template("attendance/report.html", rows=rows, month=month)
