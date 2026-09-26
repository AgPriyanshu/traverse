"""Prompt templates for reconciliation's structured LLM calls (S5.1 stage 5)."""

RECONCILE_ADJUDICATION_PROMPT = """You are reconciling a character roster across
a book series. Decide whether a name from a NEW book is the SAME character as
one the project already knows, or a DIFFERENT person.

The project already knows:
Name: "{target_name}"
Series role: {target_summary}
Contexts from earlier books:
{target_contexts}

The new book introduces:
Name: "{candidate_name}"
Contexts from this book:
{candidate_contexts}

Watch for evidence that they are different people even though the names look
related: a generational marker ("young", "the elder", "her mother's name
was"), a stated parent/child relationship, or one appearing to die before the
other is introduced. Any of these means DIFFERENT characters. A surface form
that plausibly evolves across a series (a nickname, a marriage or promotion
that changes how a character is addressed) is normal and does not by itself
mean different characters.

Reply with "same_person" (true/false), "confidence" (0.0-1.0), and "reason".
"""
