"""
Minimal disjoint-set (union-find) over integer indices 0..n-1, shared by
exact dedup (records linked by ID or URL) and near-dup grouping (records
linked by LSH similarity).
"""

from __future__ import annotations


class UnionFind:
    def __init__(self, size: int) -> None:
        self._parent = list(range(size))

    def find(self, i: int) -> int:
        root = i
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[i] != root:  # path compression
            self._parent[i], i = root, self._parent[i]
        return root

    def union(self, a: int, b: int) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            # Smaller index becomes the root -- keeps groups deterministic.
            low, high = sorted((root_a, root_b))
            self._parent[high] = low

    def groups(self) -> list[list[int]]:
        """Every group as a sorted index list, ordered by its smallest member."""
        by_root: dict[int, list[int]] = {}
        for i in range(len(self._parent)):
            by_root.setdefault(self.find(i), []).append(i)
        return sorted(by_root.values(), key=lambda members: members[0])
