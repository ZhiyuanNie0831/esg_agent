# Workflow API Routes

The public API prefix is still mounted by `app.main` through `app.routes.workflow`.
This package only splits route ownership by responsibility.

- `catalog.py`: skill catalog endpoints.
- `uploads.py`: file upload and document normalization entrypoint.
- `planning.py`: plan and synchronous execute endpoints.
- `jobs.py`: background job lifecycle endpoints.
- `artifacts.py`: persisted artifact download endpoint.
- `sessions.py`: workflow session lifecycle endpoints.
- `errors.py`: route-level conversion from workflow service errors to HTTP errors.

Route modules should stay thin: validate HTTP inputs, call the workflow service or store, and translate expected service errors. Business behavior belongs under `app/services/workflow/`.
