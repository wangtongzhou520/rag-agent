import { RouterProvider } from "react-router-dom";

import { ErrorBoundary } from "@/app/ErrorBoundary";
import { AppProviders } from "@/app/providers";
import { router } from "@/app/router";

export function App() {
  return (
    <ErrorBoundary>
      <AppProviders>
        <RouterProvider router={router} />
      </AppProviders>
    </ErrorBoundary>
  );
}
