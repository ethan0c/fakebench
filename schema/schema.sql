-- Every finished round. One row per submission.
CREATE TABLE IF NOT EXISTS results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  test TEXT NOT NULL,
  mode TEXT NOT NULL,
  day TEXT,
  score INTEGER NOT NULL,
  total INTEGER NOT NULL,
  avg_ms INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_results_test_created ON results(test, created_at);

-- Score histogram per test. Percentiles come from here, so no table scans.
CREATE TABLE IF NOT EXISTS score_hist (
  test TEXT NOT NULL,
  score INTEGER NOT NULL,
  n INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (test, score)
);

-- Per-item fool rate. Which fakes fool the most people, which real photos get called AI.
CREATE TABLE IF NOT EXISTS item_stats (
  item_id TEXT PRIMARY KEY,
  shown INTEGER NOT NULL DEFAULT 0,
  wrong INTEGER NOT NULL DEFAULT 0
);

-- Daily accuracy rollup, written by the cron so the live stat is a single row read.
CREATE TABLE IF NOT EXISTS daily_rollup (
  test TEXT NOT NULL,
  day TEXT NOT NULL,
  rounds INTEGER NOT NULL,
  correct INTEGER NOT NULL,
  total INTEGER NOT NULL,
  PRIMARY KEY (test, day)
);

-- Pilot requests from /teams. Read them with:
--   npx wrangler d1 execute fakebench --remote --command "SELECT * FROM leads ORDER BY id DESC"
CREATE TABLE IF NOT EXISTS leads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  email TEXT NOT NULL,
  org TEXT NOT NULL,
  role TEXT,
  kind TEXT,
  size TEXT,
  plan TEXT,
  message TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
