
import sqlite3
from pathlib import Path
from datetime import date
from apscheduler.schedulers.background import BackgroundScheduler

DATABASE = Path(__file__).resolve().parent / "medicines.db"

LOW_STOCK_LIMIT = 5
EXPIRY_WARNING_DAYS = 30


def check_medicine_reminders():
    """Check medicine expiry and stock periodically."""

    if not DATABASE.exists():
        print("Medicine database not found.")
        return

    today = date.today()

    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row

        medicines = conn.execute("""
            SELECT name, quantity, expiry_date
            FROM medicines
        """).fetchall()

    print("\n===== MediTrack AI Reminders =====")

    if not medicines:
        print("No medicines available.")
        print("==================================\n")
        return

    reminders_found = False

    for medicine in medicines:
        name = medicine["name"]
        quantity = medicine["quantity"]
        expiry_text = medicine["expiry_date"]

        try:
            expiry = date.fromisoformat(expiry_text)
            days_left = (expiry - today).days
        except (ValueError, TypeError):
            print(f"Check invalid expiry date for {name}.")
            reminders_found = True
            continue

        if days_left < 0:
            print(f"EXPIRY ALERT: {name} expired {-days_left} days ago.")
            reminders_found = True

        elif days_left <= EXPIRY_WARNING_DAYS:
            print(
                f"EXPIRY REMINDER: {name} expires in {days_left} days."
            )
            reminders_found = True

        if quantity <= LOW_STOCK_LIMIT:
            print(f"LOW STOCK ALERT: {name} has only {quantity} left.")
            reminders_found = True

    if not reminders_found:
        print("No expiry or low-stock reminders today.")

    print("==================================\n")


def start_reminder_agent():
    scheduler = BackgroundScheduler()

    # Check immediately when the agent starts.
    check_medicine_reminders()

    # Repeat the check every 24 hours.
    scheduler.add_job(
        check_medicine_reminders,
        trigger="interval",
        hours=24,
        id="medicine_reminder_check",
        replace_existing=True
    )

    scheduler.start()

    print("MediTrack background reminder agent started.")

    return scheduler


if __name__ == "__main__":
    scheduler = start_reminder_agent()

    try:
        # Keep the scheduler running.
        while True:
            import time
            time.sleep(1)

    except KeyboardInterrupt:
        scheduler.shutdown()
        print("Reminder agent stopped.")