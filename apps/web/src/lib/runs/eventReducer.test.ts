import { describe, expect, it } from "vitest";
import { reduceRunEvent } from "./eventReducer";

describe("reduceRunEvent", () => {
  it("tracks agent status and report sections", () => {
    let state = reduceRunEvent(undefined, {
      event_id: "evt_1",
      run_id: "run_1",
      type: "agent_status",
      timestamp: "2026-05-19T00:00:00Z",
      payload: { agent: "Market Analyst", status: "running" },
    });
    state = reduceRunEvent(state, {
      event_id: "evt_2",
      run_id: "run_1",
      type: "report_section",
      timestamp: "2026-05-19T00:00:01Z",
      payload: { section: "market_report", content: "Market report" },
    });

    expect(state.agentStatus["Market Analyst"]).toBe("running");
    expect(state.reportSections.market_report).toBe("Market report");
  });
});
