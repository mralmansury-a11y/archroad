# -*- coding: utf-8 -*-
"""
نظام إدارة الموارد البشرية - إدارة خدمات الطريق الدولي
Flask + SQLite (لا حزم خارجية غير Flask)

app.py: التهيئة، تسجيل الدخول/الخروج، لوحة التحكم، وتسجيل وحدات النظام
(الوحدات نفسها موجودة في مجلد modules/ كل وحدة في ملف مستقل).
"""
import os
from datetime import date, timedelta, timedelta as _td
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect, url_for, session, flash, abort
)
from werkzeug.security import check_password_hash

import db
import core
from core import login_required, parse_date, csrf_token, csrf_valid, safe_next

from modules import employees, attendance, leaves, payroll, performance, recruitment, training, users, documents

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["PERMANENT_SESSION_LIFETIME"] = _td(days=7)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["MAX_CONTENT_LENGTH"] = 26 * 1024 * 1024  # الحد الأقصى للطلب الواحد (عدة ملفات)

db.init_app(app)

for m in (employees, attendance, leaves, payroll, performance, recruitment, training, users, documents):
    app.register_blueprint(m.bp)

ARABIC_WEEKDAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

app.jinja_env.globals.update(
    csrf_token=csrf_token,
    ORG_NAME=core.ORG_NAME,
    ORG_NAME_EN=core.ORG_NAME_EN,
    ATT_LABELS={"present": "حاضر", "late": "متأخر", "absent": "غائب", "leave": "إجازة"},
    LEAVE_LABELS={"pending": "قيد المراجعة", "approved": "مقبولة", "rejected": "مرفوضة"},
)
app.jinja_env.filters["pairs"] = lambda L: [(x, x) for x in L]
def _filesize(n):
    n = n or 0
    return "%.1f MB" % (n / 1048576) if n >= 1048576 else "%d KB" % max(1, round(n / 1024))


app.jinja_env.filters["filesize"] = _filesize
app.jinja_env.filters["money"] = lambda v: "{:,.2f}".format(v or 0)


def get_current_user():
    """المستخدم الحالي مع بيانات الموظف المرتبط به (إن وجد)."""
    if "user_id" not in session:
        return None
    return db.get_db().execute(
        """
        SELECT u.id, u.username, u.role, u.employee_id,
               e.full_name, e.initials, e.position,
               d.name AS department_name
        FROM users u
        LEFT JOIN employees e ON e.id = u.employee_id
        LEFT JOIN departments d ON d.id = e.department_id
        WHERE u.id = ?
        """,
        (session["user_id"],),
    ).fetchone()


@app.context_processor
def inject_globals():
    ctx = {"current_user": None, "pending_badge": 0}
    if "user_id" in session:
        ctx["current_user"] = get_current_user()
        ctx["pending_badge"] = db.get_db().execute(
            "SELECT COUNT(*) AS c FROM leave_requests WHERE status = 'pending'"
        ).fetchone()["c"]
    return ctx


@app.before_request
def csrf_protect():
    if request.method == "POST" and not csrf_valid():
        abort(400)


@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(405)
@app.errorhandler(413)
def http_error(e):
    msgs = {400: "انتهت صلاحية الصفحة أو الطلب غير صالح. أعد تحميل الصفحة وحاول مجدداً.",
            404: "الصفحة المطلوبة غير موجودة.", 405: "الطريقة غير مسموحة.",
            413: "حجم الملفات المرفوعة كبير جداً. الحد الأقصى 5 ميجابايت للملف."}
    return render_template("error.html", code=e.code, message=msgs.get(e.code, "حدث خطأ")), e.code


# ---------------------------------------------------------------------------
# 1) تسجيل الدخول
# ---------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def index():
    return redirect(url_for("dashboard" if "user_id" in session else "login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))

        conn = db.get_db()
        user = conn.execute(
            "SELECT id, username, password_hash, role FROM users WHERE username = ?",
            (username,),
        ).fetchone()

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            session.permanent = remember
            return redirect(url_for("dashboard"))

        flash("اسم المستخدم أو كلمة المرور غير صحيحة", "error")
        return render_template("login.html", username=username), 401

    return render_template("login.html", username="")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# 2) لوحة التحكم
# ---------------------------------------------------------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    conn = db.get_db()
    today = date.today()
    today_str = today.isoformat()

    total_employees = conn.execute(
        "SELECT COUNT(*) AS c FROM employees WHERE status != 'منتهي'").fetchone()["c"]
    pending_leaves_count = conn.execute(
        "SELECT COUNT(*) AS c FROM leave_requests WHERE status = 'pending'").fetchone()["c"]
    present_today = conn.execute(
        "SELECT COUNT(*) AS c FROM attendance WHERE day = ? AND status IN ('present','late')",
        (today_str,)).fetchone()["c"]
    attendance_rate = round((present_today / total_employees) * 100) if total_employees else 0

    upcoming_limit = (today + timedelta(days=30)).isoformat()
    rows = conn.execute(
        """
        SELECT e.*, d.name AS department_name
        FROM employees e JOIN departments d ON d.id = e.department_id
        WHERE e.contract_end_date IS NOT NULL AND e.contract_end_date >= ? AND e.contract_end_date <= ?
        ORDER BY e.contract_end_date ASC
        """,
        (today_str, upcoming_limit),
    ).fetchall()
    contracts_ending = []
    for row in rows:
        end_date = parse_date(row["contract_end_date"])
        contracts_ending.append({
            "id": row["id"], "full_name": row["full_name"], "initials": row["initials"],
            "position": row["position"], "department_name": row["department_name"],
            "contract_type": row["contract_type"], "contract_end_date": end_date,
            "days_left": (end_date - today).days,
        })

    weekly_chart = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        present = conn.execute(
            "SELECT COUNT(*) AS c FROM attendance WHERE day = ? AND status IN ('present','late')",
            (day.isoformat(),)).fetchone()["c"]
        rate = round((present / total_employees) * 100) if total_employees else 0
        weekly_chart.append({"label": ARABIC_WEEKDAYS[day.weekday()], "rate": rate})

    pending_leaves = conn.execute(
        """
        SELECT lr.id, lr.leave_type, lr.days, e.full_name, e.initials
        FROM leave_requests lr JOIN employees e ON e.id = lr.employee_id
        WHERE lr.status = 'pending' ORDER BY lr.created_at DESC, lr.id DESC LIMIT 4
        """
    ).fetchall()

    dept_rows = conn.execute(
        """
        SELECT d.name, COUNT(e.id) AS c FROM departments d
        LEFT JOIN employees e ON e.department_id = d.id AND e.status != 'منتهي'
        GROUP BY d.id ORDER BY c DESC, d.name
        """
    ).fetchall()
    max_c = max([r["c"] for r in dept_rows] + [1])
    departments = [{"name": r["name"], "count": r["c"], "pct": round(r["c"] / max_c * 100)} for r in dept_rows]

    open_jobs = conn.execute("SELECT COUNT(*) AS c FROM job_postings WHERE status='open'").fetchone()["c"]
    upcoming_trainings = conn.execute(
        "SELECT COUNT(*) AS c FROM trainings WHERE end_date >= ?", (today_str,)).fetchone()["c"]

    return render_template(
        "dashboard.html",
        total_employees=total_employees, pending_leaves_count=pending_leaves_count,
        present_today=present_today, attendance_rate=attendance_rate,
        contracts_ending=contracts_ending, contracts_ending_count=len(contracts_ending),
        weekly_chart=weekly_chart, pending_leaves=pending_leaves, departments=departments,
        open_jobs=open_jobs, upcoming_trainings=upcoming_trainings, today=today,
    )


# قبول / رفض طلب إجازة من لوحة التحكم (المنطق في core.decide_leave)
@app.route("/leave-requests/<int:request_id>/<string:decision>", methods=["POST"])
@login_required
def decide_leave_request(request_id, decision):
    if decision not in ("approve", "reject"):
        flash("إجراء غير معروف", "error")
        return redirect(url_for("dashboard"))
    if core.decide_leave(db.get_db(), request_id, decision):
        flash("تم تحديث حالة الطلب بنجاح", "success")
    else:
        flash("الطلب غير موجود أو تمت معالجته مسبقاً", "error")
    return redirect(safe_next("dashboard"))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8000)
