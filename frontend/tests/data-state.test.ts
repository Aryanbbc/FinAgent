import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { DataState } from "../components/data-state";
import { DashboardDatasetReadyState } from "../components/dashboard-empty-state";

test("empty and API-error terminal states present safe recovery copy", () => {
  const empty = renderToStaticMarkup(createElement(DataState, { empty: true }));
  const failure = renderToStaticMarkup(createElement(DataState, { error: "Dataset unavailable" }));
  assert.match(empty, /Fetch dataset/);
  assert.match(empty, /Run first experiment/);
  assert.match(failure, /Research data unavailable/);
  assert.doesNotMatch(failure, /stack trace/i);
});

test("dataset-only dashboard state is explicit and is not an API failure", () => {
  const dataset = {
    dataset_id: "DATA-AUTO-AAPL-1D", version_id: "DVER-000001", version_number: 1, provider: "twelve_data",
    symbol: "AAPL", asset_class: "equity", exchange: "NASDAQ", interval: "1d", start_date: "2022-01-01",
    end_date: "2023-01-01", row_count: 251, checksum: "checksum", created_at: "2026-09-07T00:00:00+00:00",
    last_refreshed_at: "2026-09-07T00:00:00+00:00", validation_status: "valid", quality_score: 1,
  };
  const markup = renderToStaticMarkup(createElement(DataState, {
    empty: true,
    emptyState: createElement(DashboardDatasetReadyState, { asset: "AAPL", dataset }),
  }));
  assert.match(markup, /AAPL dataset is ready/);
  assert.match(markup, /Run the first experiment to populate research results/);
  assert.match(markup, /DATA-AUTO-AAPL-1D/);
  assert.doesNotMatch(markup, /Research data unavailable/);
});
