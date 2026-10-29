
import joblib
from datetime import date, datetime

model = joblib.load("medicine_model.pkl")

test_medicines = [
    {"name": "Medicine A", "quantity": 100, "expiry_date": "2027-05-01"},
    {"name": "Medicine B", "quantity": 20, "expiry_date": "2026-11-05"},
    {"name": "Medicine C", "quantity": 2, "expiry_date": "2027-05-01"},
    {"name": "Medicine D", "quantity": 50, "expiry_date": "2025-01-01"},
    
]

today = date.today()

for medicine in test_medicines:
    expiry = datetime.strptime(
        medicine["expiry_date"], "%Y-%m-%d"
    ).date()

    days_left = (expiry - today).days

    prediction = model.predict([[
        medicine["quantity"],
        days_left
    ]])[0]

    print("-" * 40)
    print("Medicine:", medicine["name"])
    print("Quantity:", medicine["quantity"])
    print("Days until expiry:", days_left)
    print("ML Prediction:", prediction)
    print("Prediction completed successfully!")
