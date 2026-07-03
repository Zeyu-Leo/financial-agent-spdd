"""Unit tests for the RAG v0 chunker (Task 2, Operation 5).

Pure-function tests, no I/O. Locks the fixed-size/overlap behaviour the
ingest path depends on before any DB code exists.
"""

import pytest

from data_pipelines.starter_corpus import chunk_text


def test_empty_input_yields_no_chunks() -> None:
    assert chunk_text("") == []


def test_input_shorter_than_size_is_a_single_chunk() -> None:
    text = "short passage"
    assert chunk_text(text, size=600, overlap=100) == [text]


def test_input_equal_to_size_is_a_single_chunk() -> None:
    text = "x" * 600
    assert chunk_text(text, size=600, overlap=100) == [text]


def test_consecutive_chunks_share_overlap_characters() -> None:
    text = "".join(str(i % 10) for i in range(1000))  # 1000 chars
    chunks = chunk_text(text, size=600, overlap=100)
    # First window is [0:600], next starts at size-overlap = 500.
    assert chunks[0] == text[0:600]
    assert chunks[1] == text[500:1000]
    # The 100-char overlap: tail of chunk 0 equals head of chunk 1.
    assert chunks[0][-100:] == chunks[1][:100]


def test_covers_entire_text_with_no_gaps() -> None:
    text = "".join(str(i % 10) for i in range(1450))
    chunks = chunk_text(text, size=600, overlap=100)
    # Reconstructing by taking each chunk's non-overlapping head (step
    # chars) plus the full final chunk must recover the original text.
    step = 600 - 100
    rebuilt = "".join(c[:step] for c in chunks[:-1]) + chunks[-1]
    assert rebuilt == text


def test_no_chunk_exceeds_size() -> None:
    text = "y" * 2500
    chunks = chunk_text(text, size=600, overlap=100)
    assert all(len(c) <= 600 for c in chunks)


@pytest.mark.parametrize("bad_size", [0, -1])
def test_non_positive_size_raises(bad_size: int) -> None:
    with pytest.raises(ValueError):
        chunk_text("abc", size=bad_size)


@pytest.mark.parametrize("bad_overlap", [-1, 600, 700])
def test_overlap_out_of_range_raises(bad_overlap: int) -> None:
    with pytest.raises(ValueError):
        chunk_text("abc", size=600, overlap=bad_overlap)
