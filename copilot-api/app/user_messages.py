"""User-facing copy for chat / insights responses (avoid leaking raw SQL errors)."""

# Shown when generated SQL fails at execution (syntax, bad column after retries, etc.).
USER_FRIENDLY_SQL_QUERY_FAILURE = (
    "We're still learning from this query. Please try another one."
)
