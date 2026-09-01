import { http, HttpResponse } from "msw";

export const handlers = [
  http.get("*/health", () =>
    HttpResponse.json({ code: "0", message: "ok", data: { status: "UP" } }),
  ),
];
