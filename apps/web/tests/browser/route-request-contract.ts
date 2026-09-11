// Initial empty-installation request inventory. Interactive mutations, populated
// resource read-back, and explicit Debug expansion have separate contracts.
export const ROUTE_REQUESTS: Record<string, readonly string[]> = {
  "/": ["/runtime-settings"],
  "/manual": ["/runtime-settings"],
  "/settings": ["/runtime-settings"],
  "/model-usage": ["/runtime-settings", "/model-usage/stats"],
  "/plan": ["/runtime-settings", "/personas", "/documents", "/learning-plans", "/scene-library"],
  "/study": ["/runtime-settings", "/personas", "/documents", "/learning-plans", "/scene-library"],
  "/persona-spectrum": ["/runtime-settings", "/personas", "/persona-cards"],
  "/scene-setup": ["/runtime-settings", "/scene-library", "/reusable-scene-nodes"],
  "/sensory-tools": ["/runtime-settings", "/model-tools/config"],
  "/tavern": ["/runtime-settings", "/tavern/rooms", "/personas", "/scene-library"],
  "/not-a-real-page": ["/runtime-settings"],
};
