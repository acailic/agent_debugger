# File Templates

Templates for common file patterns in Peaky Peek.

## Usage

Copy a template and replace placeholders:

- `<resource>` → your resource name (lowercase, plural)
- `<resource_tag>` → tag name for API router (usually lowercase, plural)
- `<route_description>` → what the route does (e.g., "Session management")
- `<schema_description>` → what the schema defines (e.g., "Alert and anomaly")
- `<description>` → brief description for schema class docstring
- `ComponentName` → your component name (PascalCase)
- `ResourceSchema` → your schema name (PascalCase)

## Templates

### `api_route.py.template`
New API route module following FastAPI patterns used in the repo.

**Pattern matches:**
- `api/trace_routes.py` - route structure, dependencies, error handling
- `api/schemas.py` - import patterns, type hints

**Usage:**
```bash
cp templates/api_route.py.template api/my_resource_routes.py
# Replace: <resource> → "sessions", <route_description> → "Session query and management"
```

### `frontend_component.tsx.template`
New React component with TypeScript patterns.

**Pattern matches:**
- `frontend/src/components/EmptyState.tsx` - props interface, functional component
- `frontend/src/components/AnalyticsPanel.tsx` - state management patterns

**Usage:**
```bash
cp templates/frontend_component.tsx.template frontend/src/components/MyPanel.tsx
# Replace: ComponentName → MyPanel
```

### `pydantic_schema.py.template`
New Pydantic schema model for API contracts.

**Pattern matches:**
- `api/schemas.py` - BaseModel usage, Field descriptions, ConfigDict
- Type hints with `|` union syntax (Python 3.10+)

**Usage:**
```bash
cp templates/pydantic_schema.py.template api/schemas/my_resource.py
# Replace: ResourceSchema → MyResourceSchema
```

## Conventions

- **API routes**: Use `async def`, include type hints, use `Depends(get_repository)`
- **Frontend**: Use functional components, TypeScript interfaces, CSS modules
- **Schemas**: Use `model_config = ConfigDict(use_enum_values=True)` for enums
- **Type hints**: Use `X | None` syntax (not `Optional[X]`) for Python 3.10+
