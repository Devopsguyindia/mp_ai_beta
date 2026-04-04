from app.sql_user_messages import SQL_QUERY_USER_FRIENDLY_ANSWER


def test_sql_query_user_friendly_answer_is_non_empty() -> None:
    assert isinstance(SQL_QUERY_USER_FRIENDLY_ANSWER, str)
    assert len(SQL_QUERY_USER_FRIENDLY_ANSWER.strip()) > 0
