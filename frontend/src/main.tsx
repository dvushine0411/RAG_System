/**
 * System Role: Browser entry point mounting the React app into #root.
 * Inputs: index.html #root element.
 * Outputs: Rendered <App /> inside <AuthProvider> (StrictMode) with global styles.
 */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { AuthProvider } from "./hooks/useAuth";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </StrictMode>
);
