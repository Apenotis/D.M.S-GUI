"""
Tests for the 4-column Doom map distribution logic in refresh_data().

The distribution must spread n maps across 4 columns as evenly as possible,
leaving NO column empty as long as there is at least one map per column.

Run:
    python -m pytest Test/test_column_distribution.py -v
"""

import pytest


def distribute(maps: list) -> dict[int, list]:
    """Mirror of the distribution logic in Gui.py refresh_data()."""
    n = len(maps)
    q, r = divmod(n, 4)
    blocks = {}
    idx = 0
    for col in range(1, 5):
        size = q + (1 if col <= r else 0)
        blocks[col] = maps[idx : idx + size]
        idx += size
    return blocks


# ---------------------------------------------------------------------------
# Basic correctness
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n", range(0, 21))
def test_total_count_preserved(n):
    maps = list(range(n))
    blocks = distribute(maps)
    assert sum(len(v) for v in blocks.values()) == n


@pytest.mark.parametrize("n", range(4, 21))
def test_all_four_columns_filled(n):
    """With >=4 maps every column must have at least one entry (the original bug)."""
    maps = list(range(n))
    blocks = distribute(maps)
    for col in range(1, 5):
        assert len(blocks[col]) >= 1, (
            f"Column {col} is empty for n={n} maps – distribution bug!"
        )


@pytest.mark.parametrize("n", range(0, 21))
def test_columns_differ_by_at_most_one(n):
    maps = list(range(n))
    blocks = distribute(maps)
    sizes = [len(blocks[c]) for c in range(1, 5)]
    assert max(sizes) - min(sizes) <= 1


def test_order_preserved():
    maps = list(range(12))
    blocks = distribute(maps)
    merged = blocks[1] + blocks[2] + blocks[3] + blocks[4]
    assert merged == maps


# ---------------------------------------------------------------------------
# Regression: the specific case that was broken before the fix
# ---------------------------------------------------------------------------

def test_regression_6_maps_no_empty_column():
    """6 maps: old code gave [2,2,2,0], fixed code gives [2,2,1,1]."""
    blocks = distribute(list(range(6)))
    assert len(blocks[4]) >= 1, "Column 4 must not be empty for 6 maps (regression)"


def test_regression_3_maps_single_columns():
    """With fewer maps than columns some columns may be empty – that is OK."""
    blocks = distribute(list(range(3)))
    non_empty = sum(1 for c in range(1, 5) if blocks[c])
    assert non_empty == 3
