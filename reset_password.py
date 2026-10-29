
import sqlite3
from pathlib import Path
from getpass import getpass
from werkzeug.security import generate_password_hash

db = Path(__file__).resolve().parent / "medicines.db"

email = input("Registered email: ").strip().lower()
password = getpass("Enter new password: ")
confirm = getpass("Confirm new password: ")

if password != confirm:
    print("Passwords do not match. Try again.")
    raise SystemExit

if len(password) < 8:
    print("Use at least 8 characters.")
    raise SystemExit

with sqlite3.connect(str(db)) as conn:
    user = conn.execute(
        "SELECT id, email FROM users WHERE lower(email) = ?",
        (email,)
    ).fetchone()

    if user is None:
        print("Account not found. Check your registered email.")
    else:
        conn.execute(
            "UPDATE users SET password = ? WHERE id = ?",
            (generate_password_hash(password), user[0])
        )
        print("Password reset successful! Login with your new password.")
