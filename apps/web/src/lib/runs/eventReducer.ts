export type RunEvent = {
  event_id: string;
  run_id: string;
  type: string;
  timestamp: string;
  payload: Record<string, unknown>;
};

export type RunEventState = {
  agentStatus: Record<string, string>;
  messages: Array<{ type: string; content: string; timestamp: string }>;
  reportSections: Record<string, string>;
  completed: boolean;
  failed?: string;
};

const initialState: RunEventState = {
  agentStatus: {},
  messages: [],
  reportSections: {},
  completed: false,
};

export function reduceRunEvent(state: RunEventState = initialState, event: RunEvent): RunEventState {
  if (event.type === "agent_status") {
    const agent = String(event.payload.agent);
    const status = String(event.payload.status);
    return { ...state, agentStatus: { ...state.agentStatus, [agent]: status } };
  }
  if (event.type === "message") {
    return {
      ...state,
      messages: [
        ...state.messages,
        {
          type: String(event.payload.type ?? "System"),
          content: String(event.payload.content ?? ""),
          timestamp: event.timestamp,
        },
      ],
    };
  }
  if (event.type === "report_section") {
    return {
      ...state,
      reportSections: {
        ...state.reportSections,
        [String(event.payload.section)]: String(event.payload.content ?? ""),
      },
    };
  }
  if (event.type === "completed") {
    return { ...state, completed: true };
  }
  if (event.type === "failed") {
    return { ...state, failed: String(event.payload.error ?? "Run failed") };
  }
  return state;
}
