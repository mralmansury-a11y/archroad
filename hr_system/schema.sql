DROP TABLE IF EXISTS employee_documents;
DROP TABLE IF EXISTS training_enrollments;
DROP TABLE IF EXISTS trainings;
DROP TABLE IF EXISTS candidates;
DROP TABLE IF EXISTS job_postings;
DROP TABLE IF EXISTS performance_reviews;
DROP TABLE IF EXISTS payroll;
DROP TABLE IF EXISTS attendance;
DROP TABLE IF EXISTS leave_requests;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS employees;
DROP TABLE IF EXISTS departments;

CREATE TABLE departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_code TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    initials TEXT NOT NULL,
    department_id INTEGER NOT NULL REFERENCES departments(id),
    position TEXT NOT NULL,
    hire_date TEXT NOT NULL,
    contract_type TEXT NOT NULL,
    contract_end_date TEXT,
    status TEXT NOT NULL DEFAULT 'نشط',
    phone TEXT,
    email TEXT,
    base_salary REAL NOT NULL DEFAULT 0,
    allowance REAL NOT NULL DEFAULT 0
);

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'hr',
    employee_id INTEGER REFERENCES employees(id)
);

CREATE TABLE leave_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    leave_type TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    days INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    reason TEXT
);

CREATE TABLE attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    day TEXT NOT NULL,
    check_in TEXT,
    check_out TEXT,
    method TEXT,
    status TEXT NOT NULL,
    UNIQUE(employee_id, day)
);

CREATE TABLE payroll (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    month TEXT NOT NULL,
    base_salary REAL NOT NULL DEFAULT 0,
    allowance REAL NOT NULL DEFAULT 0,
    bonus REAL NOT NULL DEFAULT 0,
    deductions REAL NOT NULL DEFAULT 0,
    net REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'draft',
    paid_at TEXT,
    UNIQUE(employee_id, month)
);

CREATE TABLE performance_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    period TEXT NOT NULL,
    quality INTEGER NOT NULL,
    productivity INTEGER NOT NULL,
    teamwork INTEGER NOT NULL,
    commitment INTEGER NOT NULL,
    overall REAL NOT NULL,
    notes TEXT,
    reviewer TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE job_postings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    department_id INTEGER NOT NULL REFERENCES departments(id),
    openings INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'open',
    description TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES job_postings(id),
    full_name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    stage TEXT NOT NULL DEFAULT 'new',
    notes TEXT,
    created_at TEXT NOT NULL,
    employee_id INTEGER REFERENCES employees(id)
);

CREATE TABLE trainings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    trainer TEXT,
    location TEXT,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    seats INTEGER NOT NULL DEFAULT 20,
    description TEXT
);

CREATE TABLE training_enrollments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    training_id INTEGER NOT NULL REFERENCES trainings(id),
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    status TEXT NOT NULL DEFAULT 'enrolled',
    UNIQUE(training_id, employee_id)
);

CREATE TABLE IF NOT EXISTS employee_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    doc_type TEXT NOT NULL,
    original_name TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    kind TEXT NOT NULL,
    size INTEGER NOT NULL DEFAULT 0,
    uploaded_at TEXT NOT NULL,
    uploaded_by TEXT
);
