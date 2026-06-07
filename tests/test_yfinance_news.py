from tradingagents.dataflows import yfinance_news


class _Search:
    def __init__(self, query, news_count, enable_fuzzy_query):
        self.news = [
            {
                "content": {
                    "title": "old macro story",
                    "summary": "outside window",
                    "provider": {"displayName": "Wire"},
                    "canonicalUrl": {"url": "https://example.test/old"},
                    "pubDate": "2026-05-01T10:00:00Z",
                }
            },
            {
                "content": {
                    "title": "current macro story",
                    "summary": "inside window",
                    "provider": {"displayName": "Wire"},
                    "canonicalUrl": {"url": "https://example.test/current"},
                    "pubDate": "2026-06-05T10:00:00Z",
                }
            },
        ]


def test_global_news_filters_articles_before_lookback(monkeypatch):
    monkeypatch.setattr(yfinance_news.yf, "Search", _Search)
    monkeypatch.setattr(yfinance_news, "yf_retry", lambda fn: fn())
    monkeypatch.setattr(
        yfinance_news,
        "get_config",
        lambda: {
            "global_news_queries": ["macro"],
            "global_news_lookback_days": 7,
            "global_news_article_limit": 10,
        },
    )

    out = yfinance_news.get_global_news_yfinance(
        curr_date="2026-06-06",
        look_back_days=7,
        limit=10,
    )

    assert "current macro story" in out
    assert "old macro story" not in out
