import "@testing-library/jest-dom/vitest";

import { server } from "./msw/server";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));

afterEach(() => {
  server.resetHandlers();
  window.localStorage.clear();
});

afterAll(() => server.close());
