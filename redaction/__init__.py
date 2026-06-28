"""
Redaction pipeline for sanitizing event data before storage or display.

This module provides a composable redaction system that can strip or mask
sensitive fields (API keys, credentials, PII) from trace events.

Usage::

    from redaction import RedactionPipeline

    pipeline = RedactionPipeline()
    pipeline.add_rule("api_key", mask="***")
    clean_data = pipeline.redact(event_data)

Currently used by ``api.services`` for sanitizing events before persistence.

This is an extension point — add custom rules to the pipeline for
organization-specific data sensitivity requirements.
"""
