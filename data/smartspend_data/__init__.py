"""Synthetic data for SmartSpend AI: transactions, receipts, budgets."""
from .generator import DEMO_ACCOUNTS, USER_ID, Txn, account_rows, budget_rows, generate_day, generate_range

__all__ = ["DEMO_ACCOUNTS", "USER_ID", "Txn", "account_rows", "budget_rows", "generate_day", "generate_range"]
