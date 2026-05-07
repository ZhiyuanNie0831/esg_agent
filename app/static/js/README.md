# Frontend Structure

The frontend uses browser-native ES modules. There is no build step.

- `app.js`
  - Application composition and event wiring.
  - Keeps orchestration here; avoid adding rendering templates directly.
- `api/`
  - HTTP client functions for backend endpoints.
- `config/`
  - Static labels and display mappings.
- `core/`
  - Shared DOM lookup, HTML helpers, and workflow state.
- `components/`
  - Interactive UI units that own their local events.
- `views/`
  - Render-only modules for workflow results, chat summaries, confirmation, and final output.

When adding a feature:

1. Put request logic in `api/`.
2. Put durable client state in `core/workflow-state.js`.
3. Put repeated UI interactions in `components/`.
4. Put result rendering in `views/`.
5. Keep `app.js` as the coordinator between those pieces.
