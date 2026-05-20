import { describe, expect, it, vi } from "vitest";
import { ApiClient } from "./client";

describe("ApiClient", () => {
  it("adds bearer token to requests", async () => {
    const fetcher = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ authenticated: true }),
    });
    const client = new ApiClient("/api", () => "abc", fetcher as unknown as typeof fetch);

    await client.get("/auth/me");

    expect(fetcher).toHaveBeenCalledWith("/api/auth/me", {
      headers: { Authorization: "Bearer abc" },
    });
  });
});
