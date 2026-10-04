# -*- coding: utf-8 -*-
"""
سكربت تعبئة البيانات الأولية.   التشغيل:  python seed.py
تحذير: يحذف البيانات الحالية ويعيد إنشاء الجداول.
"""
import os
import sqlite3
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

import db as dbmod
from core import WEEKEND

DB_PATH = dbmod.DB_PATH


def run():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    dbmod.init_db(connection=conn)
    today = date.today()
    iso = lambda d: d.isoformat()

    # ---------------- الإدارات ----------------
    dept_names = ["الموارد البشرية", "تقنية المعلومات", "المالية", "العمليات والتشغيل",
                  "الصيانة", "الشؤون القانونية"]
    dept = {n: conn.execute("INSERT INTO departments (name) VALUES (?)", (n,)).lastrowid for n in dept_names}

    # ---------------- الموظفون ----------------
    emps = [
        ("EMP-1042", "هدى الفقيه", "هف", "الموارد البشرية", "مسؤول ملفات", date(2022, 3, 11), "دائم", None, "نشط", 2400, 300),
        ("EMP-1187", "أحمد الككلي", "أك", "تقنية المعلومات", "مبرمج أنظمة", date(2023, 9, 2), "مؤقت", today + timedelta(days=24), "نشط", 3200, 400),
        ("EMP-1233", "لمياء مسعود", "لم", "المالية", "محاسبة أولى", date(2025, 5, 20), "تجربة", today + timedelta(days=11), "إجازة", 2800, 250),
        ("EMP-0987", "طارق الزنتاني", "طز", "العمليات والتشغيل", "مشرف محطة تحصيل", date(2021, 1, 15), "دائم", None, "نشط", 3000, 500),
        ("EMP-1301", "محمد الطرابلسي", "من", "العمليات والتشغيل", "منسق مرور", date(2024, 11, 7), "دائم", None, "نشط", 2200, 300),
        ("EMP-1298", "سعاد العبيدي", "سع", "المالية", "موظفة تحصيل", date(2024, 6, 1), "دائم", None, "نشط", 2100, 250),
        ("EMP-1310", "يوسف بشير", "يب", "تقنية المعلومات", "مهندس شبكات", date(2023, 4, 18), "دائم", None, "نشط", 3400, 400),
        ("EMP-1150", "رانيا الغزالي", "رغ", "الشؤون القانونية", "مستشارة قانونية", date(2023, 2, 28), "دائم", None, "إجازة", 3600, 450),
        ("EMP-1322", "عمر المصراتي", "عم", "الصيانة", "فني صيانة طرق", date(2025, 1, 12), "دائم", None, "نشط", 2300, 350),
        ("EMP-1330", "فاطمة الورفلي", "فو", "الموارد البشرية", "أخصائية توظيف", date(2025, 8, 3), "تجربة", today + timedelta(days=27), "نشط", 2000, 200),
    ]
    eid = {}
    for code, name, ini, d, pos, hire, ctype, cend, st, sal, alw in emps:
        eid[name] = conn.execute(
            """INSERT INTO employees (employee_code, full_name, initials, department_id, position, hire_date,
               contract_type, contract_end_date, status, phone, email, base_salary, allowance)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (code, name, ini, dept[d], pos, iso(hire), ctype, iso(cend) if cend else None, st,
             "091-%07d" % (1000000 + len(eid) * 137), "emp%d@example.ly" % (len(eid) + 1), sal, alw)).lastrowid

    # ---------------- المستخدمون ----------------
    conn.execute("INSERT INTO users (username, password_hash, role, employee_id) VALUES (?,?,?,?)",
                 ("hoda.hr", generate_password_hash("Hr@12345"), "hr", eid["هدى الفقيه"]))
    conn.execute("INSERT INTO users (username, password_hash, role, employee_id) VALUES (?,?,?,?)",
                 ("admin", generate_password_hash("Admin@12345"), "admin", None))

    # ---------------- الإجازات (تواريخ نسبية لليوم) ----------------
    leaves = [
        ("محمد الطرابلسي", "سنوية", 5, 3, "pending"),
        ("سعاد العبيدي", "مرضية", 3, 1, "pending"),
        ("يوسف بشير", "طارئة", -10, 2, "approved"),
        ("رانيا الغزالي", "بدون راتب", 12, 5, "pending"),
        ("أحمد الككلي", "سنوية", -40, 7, "approved"),
        ("عمر المصراتي", "مرضية", -20, 2, "rejected"),
    ]
    for i, (n, t, off, days, st) in enumerate(leaves):
        s = today + timedelta(days=off)
        conn.execute(
            "INSERT INTO leave_requests (employee_id, leave_type, start_date, end_date, days, status, created_at) VALUES (?,?,?,?,?,?,?)",
            (eid[n], t, iso(s), iso(s + timedelta(days=days - 1)), days, st, iso(today - timedelta(days=len(leaves) - i))))

    # ---------------- الحضور (آخر 14 يوماً، بدون الجمعة والسبت) ----------------
    names = [e[1] for e in emps]
    st_of = {e[1]: e[8] for e in emps}
    rates = [0.9, 0.8, 0.95, 0.85, 0.9, 0.75, 0.92]
    for i in range(13, -1, -1):
        day = today - timedelta(days=i)
        if day.weekday() in WEEKEND:
            continue
        rate = rates[i % len(rates)]
        for idx, n in enumerate(names):
            if st_of[n] == "إجازة":
                conn.execute("INSERT INTO attendance (employee_id, day, status) VALUES (?,?,'leave')", (eid[n], iso(day)))
            elif ((idx * 7 + i * 3) % 10) / 10 < rate:
                late = (idx + i) % 6 == 1
                conn.execute(
                    "INSERT INTO attendance (employee_id, day, check_in, check_out, method, status) VALUES (?,?,?,?,?,?)",
                    (eid[n], iso(day), "08:41" if late else "08:02", None if i == 0 else "15:30",
                     "QR المكتب" if idx % 2 == 0 else "GPS ميداني", "late" if late else "present"))
            else:
                conn.execute("INSERT INTO attendance (employee_id, day, status) VALUES (?,?,'absent')", (eid[n], iso(day)))

    # ---------------- تقييمات الأداء ----------------
    q = "%d-Q%d" % (today.year, (today.month - 1) // 3 + 1)
    for n, sc, note in [("يوسف بشير", (5, 4, 5, 5), "أداء متميز في إدارة الشبكة."),
                        ("أحمد الككلي", (4, 4, 4, 3), "التزام جيد ويحتاج لتحسين مواعيد التسليم."),
                        ("سعاد العبيدي", (4, 5, 4, 4), "إنتاجية عالية في التحصيل."),
                        ("عمر المصراتي", (3, 3, 4, 3), "يحتاج لمزيد من التدريب الميداني.")]:
        conn.execute(
            "INSERT INTO performance_reviews (employee_id, period, quality, productivity, teamwork, commitment, overall, notes, reviewer, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)", (eid[n], q, *sc, round(sum(sc) / 4 * 20, 1), note, "hoda.hr", iso(today)))

    # ---------------- التوظيف ----------------
    j1 = conn.execute("INSERT INTO job_postings (title, department_id, openings, description, created_at) VALUES (?,?,?,?,?)",
                      ("موظف تحصيل رسوم", dept["العمليات والتشغيل"], 3, "العمل بنظام الورديات في محطات التحصيل.", iso(today - timedelta(days=9)))).lastrowid
    j2 = conn.execute("INSERT INTO job_postings (title, department_id, openings, description, created_at) VALUES (?,?,?,?,?)",
                      ("فني صيانة كاميرات", dept["الصيانة"], 1, "خبرة في أنظمة المراقبة.", iso(today - timedelta(days=4)))).lastrowid
    for job, name, stage in [(j1, "خالد المبروك", "interview"), (j1, "منى السنوسي", "new"), (j1, "إبراهيم القذافي", "offer"),
                             (j2, "عادل الشريف", "new"), (j2, "نجلاء البركي", "rejected")]:
        conn.execute("INSERT INTO candidates (job_id, full_name, phone, stage, created_at) VALUES (?,?,?,?,?)",
                     (job, name, "092-1234567", stage, iso(today - timedelta(days=3))))

    # ---------------- التدريب ----------------
    t1 = conn.execute("INSERT INTO trainings (title, trainer, location, start_date, end_date, seats, description) VALUES (?,?,?,?,?,?,?)",
                      ("السلامة المرورية وإدارة الحوادث", "م. سالم الأمين", "قاعة التدريب الرئيسية",
                       iso(today + timedelta(days=7)), iso(today + timedelta(days=9)), 15, "دورة إلزامية لمشرفي المحطات.")).lastrowid
    t2 = conn.execute("INSERT INTO trainings (title, trainer, location, start_date, end_date, seats, description) VALUES (?,?,?,?,?,?,?)",
                      ("أمن المعلومات الأساسي", "أ. نادية الهوني", "عن بُعد",
                       iso(today - timedelta(days=30)), iso(today - timedelta(days=28)), 20, "")).lastrowid
    for t, names_ in [(t1, ["طارق الزنتاني", "محمد الطرابلسي", "عمر المصراتي"]), (t2, ["أحمد الككلي", "يوسف بشير"])]:
        for n in names_:
            conn.execute("INSERT INTO training_enrollments (training_id, employee_id, status) VALUES (?,?,?)",
                         (t, eid[n], "completed" if t == t2 else "enrolled"))

    conn.commit()
    conn.close()
    print("تمت تعبئة قاعدة البيانات بنجاح.")
    print("  المستخدم: hoda.hr | كلمة المرور: Hr@12345")
    print("  المستخدم: admin   | كلمة المرور: Admin@12345")


if __name__ == "__main__":
    run()
