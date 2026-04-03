"""PII detection regex patterns."""

import re

PII_PATTERNS: dict[str, re.Pattern] = {
    "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    # Phone: Require explicit + prefix or specific formats
    "phone": re.compile(r"\+?\d{1,4}[-\s]?\(?\d{1,4}\)?[-\s]?\d{1,4}[-\s]?\d{1,9}"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    "ip_address": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
}

SECRET_PATTERNS: dict[str, re.Pattern] = {
    # AWS Access Key ID (starts with AKIA, followed by 16 alphanumeric characters)
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    # AWS Secret Access Key (base64-like, 40 characters)
    "aws_secret_key": re.compile(r"\b[A-Za-z0-9/+=]{40}\b"),
    # GitHub Personal Access Token (classic): ghp_, gho_, ghu_, ghs_, or ghr_
    "github_token": re.compile(
        r"\bghp_[A-Za-z0-9_]{36}\b"
        r"|\bgho_[A-Za-z0-9_]{36}\b"
        r"|\bghu_[A-Za-z0-9_]{36}\b"
        r"|\bghs_[A-Za-z0-9_]{36}\b"
        r"|\bghr_[A-Za-z0-9_]{36}\b"
    ),
    # GitHub Fine-grained token: starts with github_pat_
    "github_pat": re.compile(r"\bgithub_pat_[0-9a-zA-Z_]{82}\b"),
    # Generic Bearer tokens (Authorization header values, JWT-like)
    "bearer_token": re.compile(r"\bBearer [A-Za-z0-9\-._~+/]+=*\b", re.IGNORECASE),
    # JWT tokens (two or three dot-separated base64url segments; unsigned JWT has 2)
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)?\b"),
    # Private keys (RSA, EC, OpenSSH, etc.)
    "private_key": re.compile(r"-----BEGIN [A-Z]+ PRIVATE KEY-----"),
    # Generic API keys (api_key=,apikey=, key= followed by secret)
    "generic_api_key": re.compile(
        r"(?:api[_-]?key|apikey|key|token|secret)[=:\s]+['\"]?[A-Za-z0-9_\-]{20,}['\"]?",
        re.IGNORECASE,
    ),
}

REPLACEMENT_MAP: dict[str, str] = {
    "email": "[EMAIL]",
    "phone": "[PHONE]",
    "ssn": "[SSN]",
    "credit_card": "[CREDIT_CARD]",
    "ip_address": "[IP_ADDRESS]",
}

SECRET_REPLACEMENT_MAP: dict[str, str] = {
    "aws_access_key": "[AWS_ACCESS_KEY]",
    "aws_secret_key": "[AWS_SECRET_KEY]",
    "github_token": "[GITHUB_TOKEN]",
    "github_pat": "[GITHUB_PAT]",
    "bearer_token": "[BEARER_TOKEN]",
    "jwt": "[JWT]",
    "private_key": "[PRIVATE_KEY]",
    "generic_api_key": "[API_KEY]",
}
