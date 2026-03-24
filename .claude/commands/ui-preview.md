# Quick Visual Preview

Build the frontend and take screenshots for visual review, optionally with UX feedback.

**Target route or view:** $ARGUMENTS

## Workflow

### Step 1: Build the frontend

Run the production build to ensure everything is up to date:

```
cd frontend && npm run build
```

If the build fails, report the errors and stop. Do not proceed with a broken build.

### Step 2: Start the preview server

Start the Vite preview server in the background:

```
cd frontend && npm run preview
```

The default preview URL is `http://localhost:4173`. Wait a few seconds for the server to be ready.

### Step 3: Take screenshots

Use the `playwright` skill to capture the current state of the UI:

1. Navigate to `http://localhost:4173`
2. Take a screenshot of the main/default view
3. If the application has multiple panels or views visible on the main page, capture the full page

### Step 4: Navigate to specific views if requested

If `$ARGUMENTS` specifies a particular route, page, or component:

1. Navigate to the specified route (e.g., `http://localhost:4173/#/sessions` or whatever routing pattern the app uses)
2. Take a screenshot of that specific view
3. If `$ARGUMENTS` names a component rather than a route, navigate to wherever that component is rendered and capture it

If `$ARGUMENTS` is empty, capture the default landing view and any other major views you can navigate to.

### Step 5: Optional UX feedback

If quick UX feedback would help, run the `critique` skill on the rendered view to identify obvious issues. Skip this for simple screenshot-only requests.

### Step 6: Present results

Display the screenshots inline so the user can see the current visual state of the frontend. Add brief notes about:
- What view/route each screenshot shows
- Any obvious visual issues spotted
- Build warnings if there were any

### Step 7: Clean up

Kill the Vite preview server process to free the port. Use the PID from the background process to terminate it cleanly.
