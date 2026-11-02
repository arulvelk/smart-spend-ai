resource "google_bigquery_dataset" "smartspend" {
  dataset_id    = var.dataset_id
  friendly_name = "SmartSpend AI"
  description   = "Financial data warehouse: transactions, receipts, budgets, alerts."
  location      = var.bq_location

  depends_on = [google_project_service.enabled]
}

resource "google_bigquery_table" "transactions" {
  dataset_id          = google_bigquery_dataset.smartspend.dataset_id
  table_id            = "transactions"
  description         = "Bank-feed transactions, categorized by Gemini."
  schema              = file("${path.module}/schemas/transactions.json")
  deletion_protection = var.deletion_protection
  clustering          = ["user_id", "category"]

  time_partitioning {
    type  = "MONTH"
    field = "txn_date"
  }
}

resource "google_bigquery_table" "accounts" {
  dataset_id          = google_bigquery_dataset.smartspend.dataset_id
  table_id            = "accounts"
  description         = "Bank accounts and cards. Demo accounts are fed by the daily synthetic job."
  schema              = file("${path.module}/schemas/accounts.json")
  deletion_protection = var.deletion_protection
}

resource "google_bigquery_table" "imports" {
  dataset_id          = google_bigquery_dataset.smartspend.dataset_id
  table_id            = "imports"
  description         = "Statement uploads (CSV or PDF) and what each one added."
  schema              = file("${path.module}/schemas/imports.json")
  deletion_protection = var.deletion_protection
}

resource "google_bigquery_table" "category_labels" {
  dataset_id          = google_bigquery_dataset.smartspend.dataset_id
  table_id            = "category_labels"
  description         = "Synthetic ground truth used to evaluate categorization accuracy."
  schema              = file("${path.module}/schemas/category_labels.json")
  deletion_protection = var.deletion_protection
}

resource "google_bigquery_table" "budgets" {
  dataset_id          = google_bigquery_dataset.smartspend.dataset_id
  table_id            = "budgets"
  schema              = file("${path.module}/schemas/budgets.json")
  deletion_protection = var.deletion_protection
}

resource "google_bigquery_table" "receipts" {
  dataset_id          = google_bigquery_dataset.smartspend.dataset_id
  table_id            = "receipts"
  description         = "Receipts parsed by Gemini multimodal."
  schema              = file("${path.module}/schemas/receipts.json")
  deletion_protection = var.deletion_protection
}

resource "google_bigquery_table" "alerts" {
  dataset_id          = google_bigquery_dataset.smartspend.dataset_id
  table_id            = "alerts"
  description         = "Proactive spending alerts written by the daily job."
  schema              = file("${path.module}/schemas/alerts.json")
  deletion_protection = var.deletion_protection

  time_partitioning {
    type  = "DAY"
    field = "created_at"
  }
}

resource "google_bigquery_table" "v_monthly_category_spend" {
  dataset_id          = google_bigquery_dataset.smartspend.dataset_id
  table_id            = "v_monthly_category_spend"
  deletion_protection = false

  view {
    use_legacy_sql = false
    query          = <<-SQL
      SELECT
        user_id,
        DATE_TRUNC(txn_date, MONTH) AS month,
        COALESCE(category, 'Uncategorized') AS category,
        SUM(amount) AS spend,
        COUNT(*) AS txn_count
      FROM `${var.project_id}.${var.dataset_id}.transactions`
      WHERE direction = 'debit' AND COALESCE(category, '') NOT IN ('Transfer', 'Income')
      GROUP BY user_id, month, category
    SQL
  }

  depends_on = [google_bigquery_table.transactions]
}

resource "google_bigquery_table" "v_budget_status" {
  dataset_id          = google_bigquery_dataset.smartspend.dataset_id
  table_id            = "v_budget_status"
  description         = "Current-month spend against each budget."
  deletion_protection = false

  view {
    use_legacy_sql = false
    query          = <<-SQL
      WITH latest_budget AS (
        SELECT * EXCEPT (rn) FROM (
          SELECT b.*, ROW_NUMBER() OVER (PARTITION BY user_id, category ORDER BY effective_from DESC) AS rn
          FROM `${var.project_id}.${var.dataset_id}.budgets` b
          WHERE effective_from <= CURRENT_DATE()
        ) WHERE rn = 1
      )
      SELECT
        b.user_id,
        b.category,
        b.monthly_limit,
        COALESCE(s.spend, 0) AS spend_month_to_date,
        SAFE_DIVIDE(COALESCE(s.spend, 0), b.monthly_limit) AS pct_used
      FROM latest_budget b
      LEFT JOIN `${var.project_id}.${var.dataset_id}.v_monthly_category_spend` s
        ON s.user_id = b.user_id
       AND s.category = b.category
       AND s.month = DATE_TRUNC(CURRENT_DATE(), MONTH)
    SQL
  }

  depends_on = [google_bigquery_table.budgets, google_bigquery_table.v_monthly_category_spend]
}
