"""Merchant catalog for the synthetic generator.

Each merchant has a clean name, a ground-truth category, a set of messy
bank-feed descriptor templates, and an amount model. Descriptor templates
use {n} for a random store/reference number and {city} for a city suffix.
The messiness is deliberate: it is what the Gemini categorizer has to clean up.
"""
from __future__ import annotations

from dataclasses import dataclass, field

CATEGORIES = [
    "Groceries", "Dining", "Coffee", "Transportation", "Shopping",
    "Subscriptions", "Utilities", "Housing", "Healthcare", "Insurance",
    "Travel", "Entertainment", "Personal Care", "Fitness", "Fees",
    "Transfer", "Income",
]

CITIES = ["OAKLAND CA", "SAN FRANCISCO CA", "BERKELEY CA", "EMERYVILLE CA", "SAN FRANCISC CA", "OAKLAND  CA"]


@dataclass(frozen=True)
class Merchant:
    name: str
    category: str
    descriptors: tuple[str, ...]
    amount: tuple[float, float]          # (low, high) before rounding
    channel: str = "card"
    account: str = "cc-001"
    items: tuple[tuple[str, float, float], ...] = field(default_factory=tuple)  # receipt line items (desc, low, high)
    tip: bool = False                    # restaurants add a tip on the receipt


# Recurring bills: (merchant, day_of_month, fixed amount or None for variable)
RECURRING = [
    (Merchant("Oakwood Apartments", "Housing", ("ONLINE PMT OAKWOOD APTS WEB ID {n}", "OAKWOOD APARTMENTS ACH DEBIT"), (2150, 2150), "ach", "chk-001"), 1),
    (Merchant("PG&E", "Utilities", ("PGANDE WEB ONLINE {n}", "PG&E/EZ-PAY {n}"), (70, 190), "ach", "chk-001"), 12),
    (Merchant("Comcast Xfinity", "Utilities", ("COMCAST CABLE COMM 800-COMCAST", "XFINITY MOBILE {n}"), (89.99, 89.99)), 8),
    (Merchant("T-Mobile", "Utilities", ("T-MOBILE*AUTO PAY {n}", "TMOBILE*POSTPAID WEB"), (75, 75)), 22),
    (Merchant("GEICO", "Insurance", ("GEICO *AUTO {n}", "GEICO  AUTO PMT"), (128.40, 128.40), "ach", "chk-001"), 5),
    (Merchant("Netflix", "Subscriptions", ("NETFLIX.COM 866-579-7172", "NETFLIX.COM LOS GATOS CA"), (15.49, 15.49)), 14),
    (Merchant("Spotify", "Subscriptions", ("SPOTIFY USA {n}", "Spotify P{n}"), (11.99, 11.99)), 3),
    (Merchant("Apple iCloud", "Subscriptions", ("APPLE.COM/BILL 866-712-7753", "APPLE.COM/BILL ONE APPLE PARK"), (2.99, 2.99)), 17),
    (Merchant("Planet Fitness", "Fitness", ("PLANET FITNESS CLUB FEES", "PLANET FIT {n} CLUB FEE"), (24.99, 24.99)), 17),
    (Merchant("Chase Card Autopay", "Transfer", ("CHASE CREDIT CRD AUTOPAY PPD ID: {n}",), (900, 2400), "ach", "chk-001"), 25),
]

# A subscription that appears part-way through the year (for "new subscription" alerts).
NEW_SUBSCRIPTION = (Merchant("Disney+", "Subscriptions", ("DISNEY PLUS {n} BURBANK CA", "DISNEYPLUS.COM"), (13.99, 13.99)), 9)

PAYROLL = Merchant("Acme Corp Payroll", "Income", ("ACME CORP PAYROLL PPD ID: {n}", "ACME CORP DIR DEP {n}"), (3850, 3850), "ach", "chk-001")

GROCERY_ITEMS = (
    ("ORG BANANAS", 1.5, 3.2), ("MILK 2% GAL", 4.2, 5.9), ("EGGS LG DOZ", 3.9, 6.5),
    ("SOURDOUGH LOAF", 4.5, 7.0), ("CHKN BREAST", 8.5, 14.0), ("BABY SPINACH", 3.0, 4.8),
    ("GREEK YOGURT", 5.0, 7.5), ("AVOCADOS 4CT", 4.5, 6.9), ("PASTA PENNE", 1.8, 3.2),
    ("OLIVE OIL", 8.9, 14.9), ("COFFEE BEANS", 9.9, 15.9), ("CHEDDAR BLK", 4.5, 7.5),
    ("SALMON FILLET", 11.0, 19.0), ("BLUEBERRIES", 3.5, 5.9), ("TORTILLA CHIPS", 3.2, 4.9),
    ("SPARKLING WTR 12PK", 5.5, 7.9), ("RICE JASMINE", 3.9, 6.9), ("TOMATOES", 2.5, 4.5),
)
DINING_ITEMS = (
    ("CARNITAS BURRITO", 11.0, 14.5), ("PAD THAI", 14.0, 17.5), ("MARGHERITA PIZZA", 16.0, 21.0),
    ("CAESAR SALAD", 11.0, 14.0), ("RAMEN TONKOTSU", 15.0, 18.5), ("FISH TACOS", 13.0, 16.0),
    ("IPA DRAFT", 7.0, 9.0), ("HOUSE WINE GLS", 11.0, 14.0), ("FRIES", 5.0, 7.0), ("ICED TEA", 3.5, 4.5),
)
SHOPPING_ITEMS = (
    ("USB-C CABLE", 9.99, 19.99), ("T-SHIRT", 14.99, 24.99), ("STORAGE BINS", 12.99, 29.99),
    ("PHONE CASE", 15.99, 39.99), ("DISH SOAP", 3.49, 5.99), ("PAPER TOWELS", 11.99, 19.99),
    ("HDMI ADAPTER", 12.99, 24.99), ("SOCKS 6PK", 9.99, 16.99),
)

# Frequent spending: (merchant, base events per day)
FREQUENT = [
    (Merchant("Safeway", "Groceries", ("SAFEWAY #{n} {city}", "SAFEWAY STORE {n}"), (0, 0), items=GROCERY_ITEMS), 0.10),
    (Merchant("Trader Joe's", "Groceries", ("TRADER JOE S #{n} {city}", "TRADER JOES {n}"), (0, 0), items=GROCERY_ITEMS), 0.09),
    (Merchant("Whole Foods Market", "Groceries", ("WHOLEFDS OAK {n}", "WHOLE FOODS MARKET #{n}"), (0, 0), items=GROCERY_ITEMS), 0.05),
    (Merchant("Costco", "Groceries", ("COSTCO WHSE #{n} {city}",), (90, 260)), 0.03),
    (Merchant("Tacos El Gordo", "Dining", ("SQ *TACOS EL GORDO {city}", "SQ *TACOS EL GOR"), (0, 0), items=DINING_ITEMS, tip=True), 0.07),
    (Merchant("Thai House", "Dining", ("DOORDASH*THAI HOUSE", "DD *DOORDASH THAIHOU"), (24, 48)), 0.07),
    (Merchant("Pizzeria Delfina", "Dining", ("TST* PIZZERIA DELFINA {city}", "TST*PIZZERIA DELF"), (0, 0), items=DINING_ITEMS, tip=True), 0.05),
    (Merchant("Chipotle", "Dining", ("CHIPOTLE {n}", "CHIPOTLE ONLINE {n}"), (11, 19)), 0.08),
    (Merchant("Uber Eats", "Dining", ("UBER *EATS PENDING", "UBER   *EATS HELP.UBER.COM"), (22, 55)), 0.06),
    (Merchant("Starbucks", "Coffee", ("STARBUCKS STORE {n}", "STARBUCKS {n} {city}"), (4.25, 8.95)), 0.30),
    (Merchant("Blue Bottle Coffee", "Coffee", ("SQ *BLUE BOTTLE COFFEE", "SQ *BLUE BOTTLE CO {n}"), (5.0, 9.5)), 0.12),
    (Merchant("Peet's Coffee", "Coffee", ("PEETS {n} {city}", "PEET'S COFFEE #{n}"), (3.95, 7.5)), 0.08),
    (Merchant("Shell", "Transportation", ("SHELL OIL {n}", "SHELL SERVICE STATION"), (38, 72)), 0.09),
    (Merchant("Chevron", "Transportation", ("CHEVRON {n}", "CHEVRON {n} {city}"), (35, 70)), 0.05),
    (Merchant("Uber", "Transportation", ("UBER *TRIP HELP.UBER.COM", "UBER   *TRIP {n}"), (9, 42)), 0.08),
    (Merchant("Lyft", "Transportation", ("LYFT   *RIDE SUN 8PM", "LYFT *RIDE {n}"), (8, 35)), 0.04),
    (Merchant("Clipper", "Transportation", ("CLIPPER SERVICE CONCORD CA", "CLIPPER CARD {n}"), (20, 40)), 0.03),
    (Merchant("Amazon", "Shopping", ("AMZN Mktp US*{n}", "AMAZON.COM*{n} AMZN.COM/BILL", "Amazon.com*{n}"), (12, 140)), 0.16),
    (Merchant("Target", "Shopping", ("TARGET 000{n}", "TARGET.COM * {n}"), (0, 0), items=SHOPPING_ITEMS), 0.06),
    (Merchant("Best Buy", "Shopping", ("BEST BUY 000{n}", "BESTBUY.COM {n}"), (25, 400)), 0.01),
    (Merchant("Uniqlo", "Shopping", ("UNIQLO USA {n}", "UNIQLO {city}"), (30, 120)), 0.015),
    (Merchant("CVS Pharmacy", "Healthcare", ("CVS/PHARMACY #{n}", "CVS/PHARM {n}-{city}"), (8, 60)), 0.04),
    (Merchant("Kaiser Permanente", "Healthcare", ("KAISER PERMANENTE {n}", "KP OAKLAND MED CTR"), (20, 60)), 0.01),
    (Merchant("AMC Theatres", "Entertainment", ("AMC {n} ONLINE", "AMC BAY STREET 16"), (14, 45)), 0.02),
    (Merchant("Ticketmaster", "Entertainment", ("TICKETMASTER* {n}", "TM *TICKETMASTER"), (45, 220)), 0.006),
    (Merchant("Steam", "Entertainment", ("STEAMGAMES.COM 4259522985", "STEAM PURCHASE {n}"), (5, 60)), 0.01),
    (Merchant("Great Clips", "Personal Care", ("GREAT CLIPS #{n}", "GREAT CLIPS {city}"), (22, 35)), 0.02),
    (Merchant("Sephora", "Personal Care", ("SEPHORA #{n}", "SEPHORA.COM {n}"), (18, 90)), 0.012),
    (Merchant("Venmo", "Transfer", ("VENMO PAYMENT {n}", "VENMO *J SMITH"), (15, 120), "ach", "chk-001"), 0.04),
    (Merchant("ATM Withdrawal", "Fees", ("ATM WITHDRAWAL {n} {city}", "NON-CHASE ATM FEE-WITH"), (3, 3.5), "atm", "chk-001"), 0.01),
]

# Two trips a year: (month, merchants)
TRAVEL = [
    Merchant("United Airlines", "Travel", ("UNITED 016{n}", "UNITED AIRLINES HOUSTON TX"), (240, 520)),
    Merchant("Marriott", "Travel", ("MARRIOTT {n} SEATTLE WA", "MARRIOTT HOTELS {n}"), (180, 420)),
    Merchant("Airbnb", "Travel", ("AIRBNB * HM{n}", "AIRBNB  HMXX{n}"), (300, 900)),
]
TRAVEL_MONTHS = (6, 10)

DEFAULT_BUDGETS = {
    "Groceries": 750, "Dining": 450, "Coffee": 120, "Shopping": 350,
    "Transportation": 300, "Entertainment": 120, "Subscriptions": 60,
    "Personal Care": 80, "Healthcare": 100,
}

MERCHANT_ADDRESSES = {
    "Safeway": "3747 Grand Ave, Oakland CA",
    "Trader Joe's": "5727 College Ave, Oakland CA",
    "Whole Foods Market": "230 Bay Pl, Oakland CA",
    "Tacos El Gordo": "1820 Telegraph Ave, Oakland CA",
    "Pizzeria Delfina": "2406 California St, San Francisco CA",
    "Target": "1555 40th St, Emeryville CA",
}
