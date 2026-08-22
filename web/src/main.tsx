import { createRoot } from "react-dom/client";
import { App } from "./app";
import { DesignSystemProvider } from "./design-system/provider";

createRoot(document.getElementById("root")!).render(
  <DesignSystemProvider>
    <App />
  </DesignSystemProvider>,
);
