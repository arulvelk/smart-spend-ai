"""Synthetic data for SmartSpend AI: transactions, receipts, budgets."""
from .generator import USER_ID, Txn, budget_rows, generate_day, generate_range

__all__ = ["USER_ID", "Txn", "budget_rows", "generate_day", "generate_range"]
