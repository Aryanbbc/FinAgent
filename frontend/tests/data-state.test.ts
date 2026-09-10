import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { DataState } from "../components/data-state";

test("empty and API-error terminal states present safe recovery copy", () => {
  const empty = renderToStaticMarkup(createElement(DataState, { empty: true }));
  const failure = renderToStaticMarkup(createElement(DataState, { error: "Dataset unavailable" }));
  assert.match(empty, /Fetch dataset/);
  assert.match(empty, /Run first experiment/);
  assert.match(failure, /Research data unavailable/);
  assert.doesNotMatch(failure, /stack trace/i);
});

test("dataset-only dashboard state is explicit and is not an API failure", () => {
  const markup = renderToStaticMarkup(createElement(DataState, {
    empty: true,
    emptyState: createElement("section", { className: "state" }, createElement("h2", null, "AAPL dataset is ready"), createElement("p", null, "Run the first experiment to populate research results."), createElement("p", null, "DATA-AUTO-AAPL-1D")),
  }));
  assert.match(markup, /AAPL dataset is ready/);
  assert.match(markup, /Run the first experiment to populate research results/);
  assert.match(markup, /DATA-AUTO-AAPL-1D/);
  assert.doesNotMatch(markup, /Research data unavailable/);
});
