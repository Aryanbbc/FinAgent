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
