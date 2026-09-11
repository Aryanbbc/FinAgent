import assert from "node:assert/strict";
import test from "node:test";
import { candidateChangeGroups, candidateChangeSummary } from "../lib/improvement-display";

test("formats nested execution controls and strategy weights as readable candidate rows", () => {
  const groups = candidateChangeGroups([
    {
      parameter: "execution_controls",
      previous_value: {},
      proposed_value: { minimum_holding_period_bars: 120, reentry_cooldown_bars: 40 },
    },
    {
      parameter: "strategy_weights",
      previous_value: {},
      proposed_value: { moving_average: 0.5, momentum: 0.25, mean_reversion: 0.25 },
    },
  ]);

  const execution = groups.find((group) => group.label === "Execution Controls");
  assert.deepEqual(execution?.rows, [
    { label: "Holding Period", previous: "0 bars", proposed: "120 bars" },
    { label: "Re-entry Cooldown", previous: "0 bars", proposed: "40 bars" },
  ]);

  const weights = groups.find((group) => group.label === "Strategy Weights");
  assert.deepEqual(weights?.rows.find((row) => row.label === "Moving Average"), {
    label: "Moving Average", previous: "0%", proposed: "50%",
  });
  assert.deepEqual(weights?.rows.find((row) => row.label === "Momentum"), {
    label: "Momentum", previous: "0%", proposed: "25%",
  });
  assert.deepEqual(weights?.rows.find((row) => row.label === "Mean Reversion"), {
    label: "Mean Reversion", previous: "0%", proposed: "25%",
  });
});

test("formats supported proportions, thresholds, booleans, and unknown parameters without serialized values", () => {
  const groups = candidateChangeGroups([
    { parameter: "maximum_position_size", previous_value: 0.25, proposed_value: 0.35 },
    { parameter: "risk_confidence_threshold", previous_value: 0.15, proposed_value: 0.5 },
    { parameter: "experimental_toggle", previous_value: false, proposed_value: true },
    { parameter: "future_nested_option", previous_value: { nested: 1 }, proposed_value: { nested: 2 } },
  ]);

  const risk = groups.find((group) => group.label === "Risk");
  assert.deepEqual(risk?.rows.find((row) => row.label === "Max Position Size"), {
    label: "Max Position Size", previous: "25%", proposed: "35%",
  });
  assert.deepEqual(risk?.rows.find((row) => row.label === "Risk Confidence"), {
    label: "Risk Confidence", previous: "0.15", proposed: "0.5",
  });
  const other = groups.find((group) => group.label === "Other Changes");
  assert.deepEqual(other?.rows.find((row) => row.label === "Experimental Toggle"), {
    label: "Experimental Toggle", previous: "Disabled", proposed: "Enabled",
  });
  assert.deepEqual(other?.rows.find((row) => row.label === "Nested"), {
    label: "Nested", previous: "1", proposed: "2",
  });

  const summary = candidateChangeSummary([
    { parameter: "strategy_weights", previous_value: {}, proposed_value: { moving_average: 0.5 } },
  ]);
  assert.doesNotMatch(summary, /[{}]/);
  assert.doesNotMatch(summary, /\"/);
  assert.match(summary, /Moving Average: 0% → 50%/);
});

test("omits unchanged leaves and groups with no actual candidate change", () => {
  const groups = candidateChangeGroups([
    {
      parameter: "execution_controls",
      previous_value: { minimum_holding_period_bars: 120, reentry_cooldown_bars: 40 },
      proposed_value: { minimum_holding_period_bars: 120, reentry_cooldown_bars: 40 },
    },
    { parameter: "momentum_window", previous_value: 21, proposed_value: 21 },
    {
      parameter: "regime_strategy_mappings",
      previous_value: { bull: { moving_average: 0.5 } },
      proposed_value: { bull: { moving_average: 0.5 }, bear: { mean_reversion: 0.25 } },
    },
  ]);

  assert.equal(groups.some((group) => group.label === "Execution Controls"), false);
  assert.equal(groups.some((group) => group.rows.some((row) => row.label === "Momentum Window")), false);
  const mapping = groups.find((group) => group.label === "Regime Mapping");
  assert.deepEqual(mapping?.rows, [{ label: "Mean Reversion", previous: "—", proposed: "0.25" }]);
});
