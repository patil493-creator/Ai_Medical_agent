
from flask import (
    Flask, render_template, request,
    redirect, url_for, flash, session
)
from functools import wraps
from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)
import sqlite3
import joblib
from datetime import date
from pathlib import Path
from threading import Lock

from agent import medicine_agent
from reminder_agent import check_medicine_reminders


# --------------------------------
# APP CONFIGURATION
# --------------------------------
app = Flask(__name__)
app.secret_key = "meditrack-local-secret-key"

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "medicines.db"
MODEL_FILE = BASE_DIR / "medicine_model.pkl"

reminder_lock = Lock()


# --------------------------------
# LOAD ML MODEL
# --------------------------------
try:
    ml_model = joblib.load(MODEL_FILE)
    app.logger.info("ML model loaded successfully.")
except Exception:
    ml_model = None
    app.logger.exception("ML model could not be loaded.")


# --------------------------------
# DATABASE CONNECTION
# --------------------------------
def get_connection():
    conn = sqlite3.connect(str(DATABASE), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


# --------------------------------
# CREATE / MIGRATE DATABASE
# --------------------------------
def create_database():
    with get_connection() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS medicines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                expiry_date TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                theme TEXT NOT NULL DEFAULT 'light',
                expiry_alerts INTEGER NOT NULL DEFAULT 1,
                reminder_days INTEGER NOT NULL DEFAULT 7,
                low_stock_alerts INTEGER NOT NULL DEFAULT 1,
                low_stock_limit INTEGER NOT NULL DEFAULT 5
            )
        """)

        conn.execute("""
            INSERT OR IGNORE INTO app_settings (id)
            VALUES (1)
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL
            )
        """)

        columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(medicines)"
            ).fetchall()
        }

        if "user_id" not in columns:
            conn.execute("""
                ALTER TABLE medicines
                ADD COLUMN user_id INTEGER
            """)


# --------------------------------
# LOGIN PROTECTION
# --------------------------------
def login_required(route_function):
    @wraps(route_function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return route_function(*args, **kwargs)
    return wrapper


# --------------------------------
# SETTINGS HELPERS
# --------------------------------
def get_settings():
    with get_connection() as conn:
        return conn.execute("""
            SELECT * FROM app_settings WHERE id = 1
        """).fetchone()


@app.context_processor
def inject_settings():
    return {"app_settings": get_settings()}


# --------------------------------
# REGISTER
# --------------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("Please fill in all fields.", "error")
            return redirect(url_for("register"))

        if len(password) < 8:
            flash(
                "Password must contain at least 8 characters.",
                "error"
            )
            return redirect(url_for("register"))

        with get_connection() as conn:
            existing = conn.execute(
                "SELECT id FROM users WHERE email = ?",
                (email,)
            ).fetchone()

            if existing:
                flash("This email is already registered.", "error")
                return redirect(url_for("register"))

            # Create account
            cursor = conn.execute("""
                INSERT INTO users (name, email, password)
                VALUES (?, ?, ?)
            """, (
                name,
                email,
                generate_password_hash(password)
            ))

            new_user_id = cursor.lastrowid

            # Assign old unassigned medicines to the first account only.
            # Later registrations must not claim existing records.
            user_count = conn.execute(
                "SELECT COUNT(*) AS total FROM users"
            ).fetchone()["total"]

            if user_count == 1:
                conn.execute("""
                    UPDATE medicines
                    SET user_id = ?
                    WHERE user_id IS NULL
                """, (new_user_id,))

        session.clear()
        session["user_id"] = new_user_id
        session["user_name"] = name
        session["user_email"] = email

        flash("Account created successfully!", "success")
        return redirect(url_for("home"))

    return render_template("register.html")


# --------------------------------
# LOGIN
# --------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        with get_connection() as conn:
            user = conn.execute("""
                SELECT id, name, email, password
                FROM users
                WHERE email = ?
            """, (email,)).fetchone()

        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["user_email"] = user["email"]
            return redirect(url_for("home"))

        flash("Invalid email or password.", "error")

    return render_template("login.html")


# --------------------------------
# LOGOUT
# --------------------------------
@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


# --------------------------------
# PROFILE
# --------------------------------
@app.route("/profile")
@login_required
def profile():
    return render_template(
        "profile.html",
        user_name=session.get("user_name", "MediTrack User"),
        user_email=session.get("user_email", "")
    )


# --------------------------------
# SETTINGS
# --------------------------------
@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        theme = request.form.get("theme", "light")

        if theme not in ("light", "dark"):
            theme = "light"

        expiry_alerts = int(
            request.form.get("expiry_alerts") == "on"
        )
        low_stock_alerts = int(
            request.form.get("low_stock_alerts") == "on"
        )

        try:
            reminder_days = int(
                request.form.get("reminder_days", 7)
            )
            low_stock_limit = int(
                request.form.get("low_stock_limit", 5)
            )

            if not 1 <= reminder_days <= 90:
                raise ValueError

            if not 0 <= low_stock_limit <= 100:
                raise ValueError

        except (ValueError, TypeError):
            flash("Enter valid reminder and stock values.", "error")
            return redirect(url_for("settings"))

        with get_connection() as conn:
            conn.execute("""
                UPDATE app_settings
                SET theme = ?,
                    expiry_alerts = ?,
                    reminder_days = ?,
                    low_stock_alerts = ?,
                    low_stock_limit = ?
                WHERE id = 1
            """, (
                theme,
                expiry_alerts,
                reminder_days,
                low_stock_alerts,
                low_stock_limit
            ))

        flash("Settings saved successfully!", "success")
        return redirect(url_for("settings"))

    return render_template(
        "settings.html",
        settings=get_settings()
    )


# --------------------------------
# REMINDER CHECK
# --------------------------------
def run_reminder_check():
    if reminder_lock.acquire(blocking=False):
        try:
            check_medicine_reminders()
        except Exception:
            app.logger.exception("Reminder check failed.")
        finally:
            reminder_lock.release()


# --------------------------------
# MEDICINE EXPIRY STATUS
# --------------------------------
def get_medicine_status(medicine):
    item = dict(medicine)

    try:
        expiry = date.fromisoformat(item["expiry_date"])
        item["days_left"] = (expiry - date.today()).days
    except (ValueError, TypeError):
        item["days_left"] = None
        item["status"] = "Invalid expiry date"
        return item

    if item["days_left"] < 0:
        item["status"] = "Expired"
    elif item["days_left"] <= 30:
        item["status"] = "Expiring Soon"
    else:
        item["status"] = "Safe"

    return item


# --------------------------------
# ML PREDICTION
# --------------------------------
def predict_medicine(medicine):
    medicine["ml_prediction"] = "Model not available"

    if ml_model is None:
        return medicine

    days_left = medicine.get("days_left")

    if days_left is None:
        medicine["ml_prediction"] = "Invalid expiry date"
        return medicine

    try:
        features = [[
            int(medicine["quantity"]),
            int(days_left)
        ]]
        prediction = ml_model.predict(features)[0]
        medicine["ml_prediction"] = str(prediction)
    except Exception:
        app.logger.exception(
            "Prediction failed for medicine ID %s",
            medicine.get("id")
        )

    return medicine


# --------------------------------
# DASHBOARD
# --------------------------------
@app.route("/")
@login_required
def home():
    settings_data = get_settings()

    # Reminder agent may use the shared database.
    # Review reminder_agent.py before using multiple accounts.
    run_reminder_check()

    user_id = session["user_id"]

    with get_connection() as conn:
        records = conn.execute("""
            SELECT id, name, quantity, expiry_date
            FROM medicines
            WHERE user_id = ?
            ORDER BY expiry_date ASC
        """, (user_id,)).fetchall()

    medicine_list = [
        predict_medicine(get_medicine_status(record))
        for record in records
    ]

    expiring_medicines = [
        m for m in medicine_list
        if m["days_left"] is not None
        and 0 <= m["days_left"] <= settings_data["reminder_days"]
    ]

    expired_medicines = [
        m for m in medicine_list
        if m["status"] == "Expired"
    ]

    safe_medicines = [
        m for m in medicine_list
        if m["status"] == "Safe"
    ]

    low_stock_medicines = [
        m for m in medicine_list
        if settings_data["low_stock_alerts"]
        and m["quantity"] <= settings_data["low_stock_limit"]
    ]

    expiry_alerts = []
    popup_alerts = []

    for medicine in medicine_list:
        name = medicine["name"]
        days_left = medicine["days_left"]
        quantity = medicine["quantity"]

        if settings_data["expiry_alerts"]:
            if medicine["status"] == "Expired":
                expiry_alerts.append(f"{name} has expired!")
                popup_alerts.append(f"{name} has expired!")
            elif (
                days_left is not None
                and 0 <= days_left <= settings_data["reminder_days"]
            ):
                message = f"{name} expires in {days_left} days."
                expiry_alerts.append(message)
                popup_alerts.append(message)

        if (
            settings_data["low_stock_alerts"]
            and quantity <= settings_data["low_stock_limit"]
        ):
            popup_alerts.append(
                f"Low stock: {name} has only {quantity} left."
            )

    agent_question = session.pop("agent_question", None)
    agent_answer = session.pop("agent_answer", None)

    return render_template(
        "index.html",
        medicines=medicine_list,
        expiring_medicines=expiring_medicines,
        expired_medicines=expired_medicines,
        safe_medicines=safe_medicines,
        total_medicines=len(medicine_list),
        expiry_alerts=expiry_alerts,
        low_stock_medicines=low_stock_medicines,
        popup_alerts=popup_alerts,
        agent_question=agent_question,
        agent_answer=agent_answer,
        reminders=[]
    )


# --------------------------------
# ADD MEDICINE
# --------------------------------
@app.route("/add_medicine", methods=["POST"])
@login_required
def add_medicine():
    name = request.form.get("name", "").strip()
    quantity_text = request.form.get("quantity", "").strip()
    expiry_text = request.form.get("expiry_date", "").strip()

    if not name:
        flash("Please enter a medicine name.", "error")
        return redirect(url_for("home") + "#add-medicine")

    try:
        quantity = int(quantity_text)
        if quantity < 0:
            raise ValueError
    except (ValueError, TypeError):
        flash("Please enter a valid quantity.", "error")
        return redirect(url_for("home") + "#add-medicine")

    try:
        expiry = date.fromisoformat(expiry_text)
    except (ValueError, TypeError):
        flash("Please enter a valid expiry date.", "error")
        return redirect(url_for("home") + "#add-medicine")

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO medicines
                (name, quantity, expiry_date, user_id)
            VALUES (?, ?, ?, ?)
        """, (
            name,
            quantity,
            expiry.isoformat(),
            session["user_id"]
        ))

    flash(f"{name} added successfully!", "success")
    return redirect(url_for("home"))


# --------------------------------
# EDIT MEDICINE
# --------------------------------
@app.route(
    "/edit_medicine/<int:medicine_id>",
    methods=["GET", "POST"]
)
@login_required
def edit_medicine(medicine_id):
    user_id = session["user_id"]

    with get_connection() as conn:
        medicine = conn.execute("""
            SELECT * FROM medicines
            WHERE id = ? AND user_id = ?
        """, (medicine_id, user_id)).fetchone()

        if medicine is None:
            flash("Medicine not found.", "error")
            return redirect(url_for("home"))

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            quantity_text = request.form.get("quantity", "").strip()
            expiry_text = request.form.get("expiry_date", "").strip()

            if not name:
                flash("Please enter a medicine name.", "error")
                return redirect(
                    url_for("edit_medicine", medicine_id=medicine_id)
                )

            try:
                quantity = int(quantity_text)
                if quantity < 0:
                    raise ValueError
            except (ValueError, TypeError):
                flash("Please enter a valid quantity.", "error")
                return redirect(
                    url_for("edit_medicine", medicine_id=medicine_id)
                )

            try:
                expiry = date.fromisoformat(expiry_text)
            except (ValueError, TypeError):
                flash("Please enter a valid expiry date.", "error")
                return redirect(
                    url_for("edit_medicine", medicine_id=medicine_id)
                )

            conn.execute("""
                UPDATE medicines
                SET name = ?, quantity = ?, expiry_date = ?
                WHERE id = ? AND user_id = ?
            """, (
                name,
                quantity,
                expiry.isoformat(),
                medicine_id,
                user_id
            ))

            flash(f"{name} updated successfully!", "success")
            return redirect(url_for("home"))

    return render_template("edit_medicine.html", medicine=medicine)


# --------------------------------
# DELETE MEDICINE
# --------------------------------
@app.route(
    "/delete_medicine/<int:medicine_id>",
    methods=["POST"]
)
@login_required
def delete_medicine(medicine_id):
    with get_connection() as conn:
        conn.execute("""
            DELETE FROM medicines
            WHERE id = ? AND user_id = ?
        """, (medicine_id, session["user_id"]))

    flash("Medicine deleted.", "success")
    return redirect(url_for("home"))


# --------------------------------
# AI ASSISTANT
# --------------------------------
@app.route("/ask_agent", methods=["POST"])
@login_required
def ask_agent():
    question = request.form.get("question", "").strip()

    if not question:
        session["agent_question"] = ""
        session["agent_answer"] = (
            "Please enter a question about your medicines."
        )
        return redirect(url_for("home") + "#assistant")

    try:
        # IMPORTANT:
        # medicine_agent must be updated to query only this user's
        # medicines. This call alone cannot enforce user filtering.
        answer = medicine_agent(question)

        if answer is None:
            raise ValueError("medicine_agent returned None")

        session["agent_question"] = question
        session["agent_answer"] = str(answer)

    except Exception as error:
        app.logger.exception("AI Agent failed.")
        session["agent_question"] = question
        session["agent_answer"] = (
            f"AI Agent failed ({type(error).__name__}). "
            "Please check the terminal for details."
        )

    return redirect(url_for("home") + "#assistant")


# --------------------------------
# INITIALIZE APPLICATION
# --------------------------------
create_database()


if __name__ == "__main__":
    app.run(debug=True)
