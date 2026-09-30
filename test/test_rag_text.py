"""PII redaction + cleaning. The Python and Spark versions must agree."""

from rag.text import REDACTED, clean_text, clean_text_col, contains_pii

CASES = [
    ("Call me on +971 50 123 4567 today", f"Call me on {REDACTED} today"),
    ("email: sara.j@example.com or 0501234567", f"email: {REDACTED} or {REDACTED}"),
    ("Available 2026-12-15, size 120x80 cm", "Available 2026-12-15, size 120x80 cm"),
    ("  lots\n\n of   space  ", "lots of space"),
    ("   ", None),
    (None, None),
]


def test_clean_text_python():
    for raw, expected in CASES:
        assert clean_text(raw, 500) == expected, raw
    assert clean_text("abcdef", 3) == "abc"
    assert contains_pii("x@y.com") and not contains_pii("desk 120x80")


def test_spark_twin_agrees(spark):
    df = spark.createDataFrame([(raw,) for raw, _ in CASES], "t string")
    got = [r.c for r in df.select(clean_text_col(df.t, 500).alias("c")).collect()]
    assert got == [expected for _, expected in CASES]
