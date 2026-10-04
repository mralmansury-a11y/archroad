# -*- coding: utf-8 -*-
"""وحدة الأداء: تقييمات دورية بأربعة معايير ونسبة إجمالية."""
from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash, session

import db
from core import login_required, employees_options

bp = Blueprint("performance", __name__, url_prefix="/performance")


def current_period():
    t = date.today()
    return "%d-Q%d" % (t.year, (t.month - 1) // 3 + 1)


@bp.app_template_filter("rating")
def rating(pct):
    if pct >= 90: return "ممتاز"
    if pct >= 75: return "جيد جداً"
    if pct >= 60: return "جيد"
    return "يحتاج تحسين"


@bp.app_template_filter("rating_class")
def rating_class(pct):
    return "good" if pct >= 75 else ("warn" if pct >= 60 else "bad")


@bp.route("/")
@login_required
def index():
    conn = db.get_db()
    period = request.args.get("period", "")
    periods = [r["period"] for r in conn.execute("SELECT DISTINCT period FROM performance_reviews ORDER BY period DESC")]
    sql = ("SELECT r.*, e.full_name, e.initials, e.position FROM performance_reviews r "
           "JOIN employees e ON e.id=r.employee_id")
    params = []
    if period:
        sql += " WHERE r.period=?"
        params.append(period)
    rows = conn.execute(sql + " ORDER BY r.overall DESC, r.id DESC", params).fetchall()
    avg = round(sum(r["overall"] for r in rows) / len(rows)) if rows else 0
    return render_template("performance/index.html", rows=rows, periods=periods, period=period, avg=avg)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    conn = db.get_db()
    form = {"period": current_period()}
    if request.method == "POST":
        f = request.form
        form = {k: f.get(k, "").strip() for k in ("employee_id", "period", "notes")}
        scores = {}
        for k in ("quality", "productivity", "teamwork", "commitment"):
            v = f.get(k, "")
            scores[k] = int(v) if v in ("1", "2", "3", "4", "5") else 0
            form[k] = scores[k]
        if not form["employee_id"].isdigit() or not form["period"] or 0 in scores.values():
            flash("أكمل الموظف والفترة وكل المعايير الأربعة", "error")
        else:
            overall = round(sum(scores.values()) / 4 * 20, 1)
            conn.execute(
                "INSERT INTO performance_reviews (employee_id, period, quality, productivity, teamwork, commitment, "
                "overall, notes, reviewer, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (int(form["employee_id"]), form["period"], scores["quality"], scores["productivity"],
                 scores["teamwork"], scores["commitment"], overall, form["notes"],
                 session.get("username"), date.today().isoformat()))
            conn.commit()
            flash("تم حفظ التقييم (%s%%)" % overall, "success")
            return redirect(url_for("performance.index"))
    return render_template("performance/form.html", form=form, emps=employees_options(conn))


@bp.route("/<int:rid>/delete", methods=["POST"])
@login_required
def delete(rid):
    conn = db.get_db()
    conn.execute("DELETE FROM performance_reviews WHERE id=?", (rid,))
    conn.commit()
    flash("تم حذف التقييم", "success")
    return redirect(url_for("performance.index"))
