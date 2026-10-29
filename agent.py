
import sqlite3
from pathlib import Path
from datetime import date

DATABASE = Path(__file__).resolve().parent / "medicines.db"
LOW_STOCK_LIMIT = 5
EXPIRY_WARNING_DAYS = 30


def get_medicines():
    """Read saved medicines from the database."""
    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        medicines = conn.execute("""
            SELECT id, name, quantity, expiry_date
            FROM medicines
            ORDER BY expiry_date
        """).fetchall()

        return [dict(medicine) for medicine in medicines]


def get_days_left(expiry_date):
    """Calculate days remaining until expiry."""
    try:
        expiry = date.fromisoformat(expiry_date)
        return (expiry - date.today()).days
    except (ValueError, TypeError):
        return None


def check_expiry(expiry_date):
    """Return medicine expiry status."""
    days_left = get_days_left(expiry_date)

    if days_left is None:
        return "Invalid expiry date"
    if days_left < 0:
        return f"Expired {abs(days_left)} days ago."
    if days_left == 0:
        return "Expires today. Please check the package."
    if days_left <= EXPIRY_WARNING_DAYS:
        return f"Expiring soon! {days_left} days left."

    return f"Safe. {days_left} days left."


def get_expired_medicines(medicines):
    return [
        m for m in medicines
        if get_days_left(m["expiry_date"]) is not None
        and get_days_left(m["expiry_date"]) < 0
    ]


def get_expiring_medicines(medicines):
    return [
        m for m in medicines
        if get_days_left(m["expiry_date"]) is not None
        and 0 <= get_days_left(m["expiry_date"]) <= EXPIRY_WARNING_DAYS
    ]


def get_low_stock_medicines(medicines):
    return [
        m for m in medicines
        if m["quantity"] <= LOW_STOCK_LIMIT
    ]


def analyze_inventory(medicines):
    expired = get_expired_medicines(medicines)
    expiring = get_expiring_medicines(medicines)
    low_stock = get_low_stock_medicines(medicines)

    report = [
        "INVENTORY ANALYSIS",
        f"Total medicine records: {len(medicines)}",
        f"Expired medicines: {len(expired)}",
        f"Expiring within 30 days: {len(expiring)}",
        f"Low-stock medicines: {len(low_stock)}",
        "",
        "RECOMMENDATIONS:"
    ]

    if expired:
        report.append(
            "Check these expired medicines: "
            + ", ".join(m["name"] for m in expired)
        )

    if expiring:
        report.append(
            "Review expiry dates for: "
            + ", ".join(m["name"] for m in expiring)
        )

    if low_stock:
        report.append(
            "Review stock levels for: "
            + ", ".join(m["name"] for m in low_stock)
        )

    if not expired and not expiring and not low_stock:
        report.append(
            "No expiry or low-stock alerts based on current rules."
        )

    report.append(
        "Verify medicine expiry and stock before taking action."
    )

    return "\n".join(report)
 
def medicine_agent(question):
    """Answer questions using saved medicine data."""
    medicines = get_medicines()
    question = question.lower().strip()

    if not question:
        return "Please ask a question about your medicines."

    if not medicines:
        return "No medicines found. Please add medicines to your dashboard first."

    if any(word in question for word in (
    "analyze", "analysis", "summary", "recommendation", "report"
    )):
        return analyze_inventory(medicines)
    
    # Total medicine count
    if any(word in question for word in (
        "total", "count", "how many", "number of"
    )):
        return f"You have {len(medicines)} medicine records saved."

    # Low stock analysis
    if any(word in question for word in (
        "low stock", "stock low", "restock", "running out",
        "less quantity", "shortage"
    )):
        results = get_low_stock_medicines(medicines)

        if not results:
            return "No low-stock medicines found. All quantities are above 5."

        return "Low-stock medicines (quantity 5 or less):\n" + "\n".join(
            f'{m["name"]}: {m["quantity"]} left. Consider checking stock.'
            for m in results
        )

    # Expired medicines only
    if "expired" in question or "already expire" in question:
        results = get_expired_medicines(medicines)

        if not results:
            return "No expired medicines found."

        return "Expired medicines:\n" + "\n".join(
            f'{m["name"]}: {check_expiry(m["expiry_date"])}'
            for m in results
        )

    # Medicines expiring soon
    if any(word in question for word in (
        "expir", "expiry", "soon", "ending"
    )):
        results = get_expiring_medicines(medicines)

        if not results:
            return "No medicines are expiring within the next 30 days."

        return "Medicines needing an expiry check:\n" + "\n".join(
            f'{m["name"]}: {check_expiry(m["expiry_date"])}'
            for m in results
        )

    # Safe medicines
    if "safe" in question or "not expiring" in question:
        results = [
            m for m in medicines
            if get_days_left(m["expiry_date"]) is not None
            and get_days_left(m["expiry_date"]) > EXPIRY_WARNING_DAYS
        ]

        if not results:
            return "No medicines are currently beyond the 30-day expiry warning period."

        return "Medicines beyond the expiry warning period:\n" + "\n".join(
            f'{m["name"]}: {m["expiry_date"]}'
            for m in results
        )

    # Show all medicines
    if any(word in question for word in (
        "list", "show all", "all medicines", "inventory"
    )):
        return "Your medicine inventory:\n" + "\n".join(
            f'{m["name"]} — Quantity: {m["quantity"]}, '
            f'Expiry: {m["expiry_date"]}, '
            f'Status: {check_expiry(m["expiry_date"])}'
            for m in medicines
        )

    # Find a particular medicine by name
    matches = [
        m for m in medicines
        if m["name"].lower() in question
    ]

    if matches:
        return "\n".join(
            f'Name: {m["name"]}\n'
            f'Quantity: {m["quantity"]}\n'
            f'Expiry date: {m["expiry_date"]}\n'
            f'Expiry status: {check_expiry(m["expiry_date"])}\n'
            f'Stock status: {"Low stock" if m["quantity"] <= LOW_STOCK_LIMIT else "Stock above low-stock limit"}'
            for m in matches
        )

    return (
        "I could not understand that question yet.\n"
        "Try asking:\n"
        "- Show all medicines\n"
        "- How many medicines do I have?\n"
        "- Which medicines are expired?\n"
        "- Which medicines are expiring soon?\n"
        "- Show low-stock medicines\n"
        "- Tell me about [medicine name]"
    )


if __name__ == "__main__":
    print("=== MediTrack AI Agent ===")

    try:
        print(f"Medicine records: {len(get_medicines())}")
        while True:
            question = input("\nAsk a question (or type 'exit'): ")

            if question.strip().lower() == "exit":
                break

            print("\nAgent response:")
            print(medicine_agent(question))

    except sqlite3.Error as error:
        print("Database error:", error)
