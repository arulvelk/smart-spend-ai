from enum import Enum

# Kept in sync with data/smartspend_data/catalog.py (the generator's ground truth).
CATEGORIES = [
    "Groceries", "Dining", "Coffee", "Transportation", "Shopping",
    "Subscriptions", "Utilities", "Housing", "Healthcare", "Insurance",
    "Travel", "Entertainment", "Personal Care", "Fitness", "Fees",
    "Transfer", "Income",
]

Category = Enum("Category", {c.upper().replace(" ", "_"): c for c in CATEGORIES}, type=str)
