from api.extraction import collision


def _ctx(page: int, text: str) -> dict:
    return {"page": page, "context": text}


class TestCheck:
    def test_blocks_on_distinct_qualifier(self) -> None:
        found = collision.check(
            "Catherine Earnshaw",
            "Catherine Linton",
            [_ctx(10, "Catherine Earnshaw ran across the moor.")],
            [_ctx(200, "Catherine Linton sat by the window.")],
        )

        assert found is not None
        assert "surname or qualifier" in found.reason

    def test_does_not_block_a_nickname_pair(self) -> None:
        found = collision.check(
            "Elizabeth Bennet",
            "Lizzy Bennet",
            [_ctx(1, "Elizabeth Bennet walked to Netherfield.")],
            [_ctx(2, "Lizzy Bennet laughed at the joke.")],
        )

        assert found is None

    def test_blocks_on_generational_marker(self) -> None:
        found = collision.check(
            "Catherine",
            "Cathy",
            [_ctx(5, "young Catherine ran to her mother.")],
            [_ctx(6, "Cathy played in the garden.")],
        )

        assert found is not None
        assert "generational" in found.reason

    def test_blocks_on_kinship_phrase(self) -> None:
        found = collision.check(
            "Catherine Earnshaw",
            "Catherine",
            [_ctx(5, "Catherine Earnshaw grew ill.")],
            [_ctx(200, "her mother's name was Catherine Earnshaw.")],
        )

        assert found is not None
        assert "kinship" in found.reason

    def test_blocks_on_lifespan_disjointness(self) -> None:
        # Single-token names so the distinct-qualifier signal (checked first)
        # never fires — this isolates the lifespan check itself.
        found = collision.check(
            "Reynolds",
            "Fairfax",
            [
                _ctx(10, "Reynolds fell ill."),
                _ctx(120, "Reynolds died in the night."),
            ],
            [_ctx(200, "Fairfax grew up at the Grange.")],
        )

        assert found is not None
        assert "earlier death" in found.reason

    def test_no_signal_leaves_the_merge_open(self) -> None:
        found = collision.check(
            "Elizabeth Bennet",
            "Miss Bennet",
            [_ctx(1, "Elizabeth Bennet spoke first.")],
            [_ctx(2, "Miss Bennet smiled.")],
        )

        assert found is None
