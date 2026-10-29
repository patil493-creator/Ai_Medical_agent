
import csv
from datetime import date
from pathlib import Path

import joblib
from sklearn.tree import DecisionTreeClassifier

folder = Path(__file__).resolve().parent
csv_file = folder / "medicine_training_data.csv"
model_file = folder / "medicine_model.pkl"

X = []
y = []

today = date.today()

with open(csv_file, newline="", encoding="utf-8") as file:
    reader = csv.DictReader(file)

    for row in reader:
        quantity = int(row["quantity"])
        expiry = date.fromisoformat(row["expiry_date"])
        days_left = (expiry - today).days

        if days_left < 0:
            status = "Expired"
        elif quantity <= 5:
            status = "Low Stock"
        elif days_left <= 30:
            status = "Expiring Soon"
        else:
            status = "Safe"

        X.append([quantity, days_left])
        y.append(status)

model = DecisionTreeClassifier(random_state=42)
model.fit(X, y)

joblib.dump(model, model_file)

print("Model training completed!")
print("Training records:", len(X))
print("Saved model to:", model_file.name)
