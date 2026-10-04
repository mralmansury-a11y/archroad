# -*- coding: utf-8 -*-
"""دوال مشتركة بين كل الوحدات (صلاحيات، تواريخ، حماية CSRF، منطق الإجازات...)."""
import re
import secrets
from datetime import datetime, date, timedelta
from functools import wraps

from flask import session, redirect, url_for, flash, request, abort

import db

ORG_NAME = "إدارة خدمات الطريق الدولي"
ORG_NAME_EN = "Toll Road Services Management"
WEEKEND = (4, 5)  # الجمعة والسبت (weekday(): الاثنين=0)
ANNUAL_QUOTA = 30


# ---------------- الجلسة والصلاحيات ----------------
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        uid = session.get("user_id")
        if not uid:
            return redirect(url_for("login"))
        ok = db.get_db().execute("SELECT 1 FROM users WHERE id = ?", (uid,)).fetchone()
        if not ok:
            session.clear()
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def role_required(*roles):
    def deco(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if session.get("role") not in roles:
                flash("ليست لديك صلاحية للوصول إلى هذه الصفحة", "error")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)
        return wrapped
    return deco


def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


def csrf_valid():
    sent = request.form.get("csrf_token", "").encode()
    real = session.get("_csrf", "").encode()
    return bool(sent) and bool(real) and secrets.compare_digest(sent, real)


def safe_next(default_endpoint="dashboard"):
    nxt = request.form.get("next") or ""
    if nxt.startswith("/") and not nxt.startswith("//"):
        return nxt
    return url_for(default_endpoint)


# ---------------- أدوات عامة ----------------
def parse_date(value):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def safe_date(value):
    try:
        return parse_date(value)
    except (ValueError, TypeError):
        return None


def to_float(value, default=0.0):
    try:
        v = float(str(value).replace(",", "").strip())
        return v if v >= 0 else default
    except (ValueError, TypeError):
        return default


def valid_month(value):
    if value and re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
        return value
    return date.today().strftime("%Y-%m")


def make_initials(name):
    parts = [p for p in name.split() if p]
    if not parts:
        return "؟"
    return (parts[0][0] + (parts[1][0] if len(parts) > 1 else "")).strip()


def next_employee_code(conn):
    row = conn.execute(
        "SELECT MAX(CAST(SUBSTR(employee_code, 5) AS INTEGER)) AS m FROM employees WHERE employee_code LIKE 'EMP-%'"
    ).fetchone()
    return "EMP-%d" % (((row["m"] or 1000)) + 1)


def employees_options(conn, include_inactive=False):
    sql = "SELECT id, full_name FROM employees"
    if not include_inactive:
        sql += " WHERE status != 'منتهي'"
    sql += " ORDER BY full_name"
    return [(r["id"], r["full_name"]) for r in conn.execute(sql).fetchall()]


def department_options(conn):
    return [(r["id"], r["name"]) for r in conn.execute("SELECT id, name FROM departments ORDER BY name").fetchall()]


# ---------------- منطق الإجازات ----------------
def decide_leave(conn, request_id, decision):
    """قبول/رفض طلب إجازة معلّق. عند القبول تُسجَّل أيام الإجازة في الحضور."""
    lv = conn.execute("SELECT * FROM leave_requests WHERE id = ?", (request_id,)).fetchone()
    if not lv or lv["status"] != "pending":
        return False
    new_status = "approved" if decision == "approve" else "rejected"
    conn.execute("UPDATE leave_requests SET status = ? WHERE id = ?", (new_status, request_id))
    if new_status == "approved":
        d, end, n = parse_date(lv["start_date"]), parse_date(lv["end_date"]), 0
        while d <= end and n < 90:
            if d.weekday() not in WEEKEND:
                ex = conn.execute(
                    "SELECT id FROM attendance WHERE employee_id = ? AND day = ?",
                    (lv["employee_id"], d.isoformat()),
                ).fetchone()
                if ex:
                    conn.execute(
                        "UPDATE attendance SET status='leave', check_in=NULL, check_out=NULL, method=NULL WHERE id = ?",
                        (ex["id"],),
                    )
                else:
                    conn.execute(
                        "INSERT INTO attendance (employee_id, day, status) VALUES (?, ?, 'leave')",
                        (lv["employee_id"], d.isoformat()),
                    )
            d += timedelta(days=1)
            n += 1
    conn.commit()
    return True


def annual_used(conn, employee_id, year=None):
    year = year or date.today().year
    row = conn.execute(
        "SELECT COALESCE(SUM(days),0) AS s FROM leave_requests "
        "WHERE employee_id = ? AND leave_type = 'سنوية' AND status = 'approved' AND start_date LIKE ?",
        (employee_id, "%d-%%" % year),
    ).fetchone()
    return row["s"]
