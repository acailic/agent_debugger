# Security Policy

## Supported Versions

We actively maintain security fixes for the following versions:

| Version | Supported |
|---------|-----------|
| Latest stable | Yes |
| Older releases | No — please upgrade |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

If you discover a security vulnerability in Peaky Peek, please report it responsibly:

1. **Email**: Send details to the maintainers via the contact listed on the [GitHub profile](https://github.com/acailic).
2. **Subject line**: `[SECURITY] Peaky Peek – <brief description>`
3. **Include**:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

We will acknowledge receipt within **48 hours** and aim to provide a fix or mitigation within **14 days** for critical issues.

## Scope

This policy covers:

- The `peaky-peek` SDK package
- The `peaky-peek-server` package and its REST API
- The Peaky Peek web UI

### In Scope

- Authentication and authorization flaws
- Data exposure (agent traces, session data, LLM inputs/outputs)
- SQL injection or other injection attacks
- Insecure defaults that expose sensitive data
- Dependency vulnerabilities with direct exploitability

### Out of Scope

- Issues in third-party frameworks (LangChain, OpenAI, etc.) — report those upstream
- Bugs without security impact
- Theoretical vulnerabilities without a realistic attack path

## Security Considerations for Self-Hosted Deployments

Peaky Peek is **local-first by default**. If you deploy the server publicly, take note:

- **API authentication**: Enable API key authentication (`AUTH_ENABLED=true`) — do not expose the server without auth
- **Trace data**: Agent traces may contain sensitive prompts, tool outputs, or PII — treat the database accordingly
- **Environment variables**: Never commit `.env` files containing secrets; use `.env.example` as a reference only
- **Network exposure**: Bind the server to `localhost` unless you intend public access; use a reverse proxy with TLS for production

## Disclosure Policy

We follow **coordinated disclosure**: we ask that you give us reasonable time to patch before any public disclosure. We will credit reporters in the release notes unless you prefer to remain anonymous.
