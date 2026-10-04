# -*- coding: utf-8 -*-
"""وحدة التدريب والتطوير: الدورات، التسجيل، إتمام الدورة."""
from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort

import db
from core import login_required, safe_date

bp = Blueprint("training", __name__, url_prefix="/training")


def _state(t):
    today = date.today().isoformat()
    if t["end_date"] < today:
        return ("finished", "منتهية")
    if t["start_date"] > today:
        return ("upcoming", "قادمة")
    return ("ongoing", "جارية")


@bp.route("/")
@login_required
def index():
    conn = db.get_db()
    rows = conn.execute(
        """SELECT t.*, (SELECT COUNT(*) FROM training_enrollments te WHERE te.training_id=t.id) AS enrolled,
                  (SELECT COUNT(*) FROM training_enrollments te WHERE te.training_id=t.id AND te.status='completed') AS done
           FROM trainings t ORDER BY t.start_date DESC""").fetchall()
    items = [dict(r, state=_state(r)) for r in rows]
    return render_template("training/index.html", items=items)


def _read():
    f = request.form
    d = {k: f.get(k, "").strip() for k in ("title", "trainer", "location", "start_date", "end_date", "seats", "description")}
    errors = []
    if not d["title"]:
        errors.append("عنوان الدورة مطلوب")
    s, e = safe_date(d["start_date"]), safe_date(d["end_date"])
    if not s or not e:
        errors.append("التواريخ غير صالحة")
    elif e < s:
        errors.append("تاريخ النهاية يجب أن يكون بعد البداية")
    d["seats"] = int(d["seats"]) if d["seats"].isdigit() and int(d["seats"]) > 0 else 20
    return d, errors


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    form = {"seats": 20, "start_date": date.today().isoformat(), "end_date": date.today().isoformat()}
    if request.method == "POST":
        form, errors = _read()
        if not errors:
            conn = db.get_db()
            cur = conn.execute("INSERT INTO trainings (title, trainer, location, start_date, end_date, seats, description) "
                               "VALUES (?,?,?,?,?,?,?)", tuple(form[k] for k in ("title", "trainer", "location", "start_date", "end_date", "seats", "description")))
            conn.commit()
            flash("تمت إضافة الدورة", "success")
            return redirect(url_for("training.detail", tid=cur.lastrowid))
        for m in errors:
            flash(m, "error")
    return render_template("training/form.html", form=form, editing=False)


@bp.route("/<int:tid>/edit", methods=["GET", "POST"])
@login_required
def edit(tid):
    conn = db.get_db()
    t = conn.execute("SELECT * FROM trainings WHERE id=?", (tid,)).fetchone()
    if not t:
        abort(404)
    form = dict(t)
    if request.method == "POST":
        form, errors = _read()
        if not errors:
            conn.execute("UPDATE trainings SET title=?, trainer=?, location=?, start_date=?, end_date=?, seats=?, description=? WHERE id=?",
                         tuple(form[k] for k in ("title", "trainer", "location", "start_date", "end_date", "seats", "description")) + (tid,))
            conn.commit()
            flash("تم حفظ التعديلات", "success")
            return redirect(url_for("training.detail", tid=tid))
        for m in errors:
            flash(m, "error")
    return render_template("training/form.html", form=form, editing=True, tid=tid)


@bp.route("/<int:tid>")
@login_required
def detail(tid):
    conn = db.get_db()
    t = conn.execute("SELECT * FROM trainings WHERE id=?", (tid,)).fetchone()
    if not t:
        abort(404)
    people = conn.execute(
        """SELECT te.id AS enr_id, te.status, e.id, e.full_name, e.initials, e.position FROM training_enrollments te
           JOIN employees e ON e.id=te.employee_id WHERE te.training_id=? ORDER BY e.full_name""", (tid,)).fetchall()
    available = conn.execute(
        "SELECT id, full_name FROM employees WHERE status != 'منتهي' AND id NOT IN "
        "(SELECT employee_id FROM training_enrollments WHERE training_id=?) ORDER BY full_name", (tid,)).fetchall()
    return render_template("training/detail.html", t=t, state=_state(t), people=people, available=available)


@bp.route("/<int:tid>/enroll", methods=["POST"])
@login_required
def enroll(tid):
    conn = db.get_db()
    t = conn.execute("SELECT * FROM trainings WHERE id=?", (tid,)).fetchone()
    if not t:
        abort(404)
    eid = request.form.get("employee_id", "")
    count = conn.execute("SELECT COUNT(*) AS c FROM training_enrollments WHERE training_id=?", (tid,)).fetchone()["c"]
    if not eid.isdigit():
        flash("اختر موظفاً", "error")
    elif count >= t["seats"]:
        flash("اكتمل عدد المقاعد", "error")
    else:
        conn.execute("INSERT OR IGNORE INTO training_enrollments (training_id, employee_id) VALUES (?,?)", (tid, int(eid)))
        conn.commit()
        flash("تم تسجيل الموظف في الدورة", "success")
    return redirect(url_for("training.detail", tid=tid))


@bp.route("/enrollment/<int:enr_id>/<string:action>", methods=["POST"])
@login_required
def enrollment(enr_id, action):
    conn = db.get_db()
    row = conn.execute("SELECT training_id FROM training_enrollments WHERE id=?", (enr_id,)).fetchone()
    if not row or action not in ("complete", "remove"):
        abort(404)
    if action == "complete":
        conn.execute("UPDATE training_enrollments SET status='completed' WHERE id=?", (enr_id,))
    else:
        conn.execute("DELETE FROM training_enrollments WHERE id=?", (enr_id,))
    conn.commit()
    flash("تم التحديث", "success")
    return redirect(url_for("training.detail", tid=row["training_id"]))


@bp.route("/<int:tid>/delete", methods=["POST"])
@login_required
def delete(tid):
    conn = db.get_db()
    conn.execute("DELETE FROM training_enrollments WHERE training_id=?", (tid,))
    conn.execute("DELETE FROM trainings WHERE id=?", (tid,))
    conn.commit()
    flash("تم حذف الدورة", "success")
    return redirect(url_for("training.index"))
