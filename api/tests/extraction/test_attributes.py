import uuid

import pytest

from api.extraction import attributes
from api.extraction.schemas import AttributeItem, AttributesOutput


class TestExtractAttributes:
    async def test_keeps_an_attribute_cited_to_a_real_context_page(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        contexts = [{"page": 12, "context": "Elizabeth, the second daughter, ..."}]

        async def fake(*a, **k):
            return AttributesOutput(
                attributes=[
                    AttributeItem(
                        key="family_role",
                        value="second daughter",
                        page=12,
                        quote="the second daughter",
                    )
                ]
            )

        monkeypatch.setattr(attributes, "structured_call", fake)

        result = await attributes.extract_attributes(
            "Elizabeth Bennet", contexts, book_id=uuid.uuid4()
        )

        assert result == {
            "family_role": {
                "value": "second daughter",
                "page": 12,
                "quote": "the second daughter",
            }
        }

    async def test_drops_an_attribute_cited_to_a_page_never_seen(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        contexts = [{"page": 12, "context": "Elizabeth spoke."}]

        async def fake(*a, **k):
            return AttributesOutput(
                attributes=[
                    AttributeItem(
                        key="occupation", value="governess", page=999, quote="x"
                    )
                ]
            )

        monkeypatch.setattr(attributes, "structured_call", fake)

        result = await attributes.extract_attributes(
            "Elizabeth Bennet", contexts, book_id=uuid.uuid4()
        )

        assert result == {}

    async def test_no_contexts_skips_the_call(self) -> None:
        result = await attributes.extract_attributes("Nobody", [], book_id=uuid.uuid4())

        assert result == {}
