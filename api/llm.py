from operator import add
from pathlib import Path
from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langchain_openai import ChatOpenAI
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
from langgraph.graph import StateGraph
from pydantic import SecretStr
from sentence_transformers import SentenceTransformer
from sqlmodel import select

from .config import settings
from .db.engine import db_session
from .db.models.document_model import DocumentChunk

langfuse = Langfuse(
    public_key=settings.langfuse_public_key,
    secret_key=settings.langfuse_secret_key,
    host=settings.langfuse_base_url,
)

langfuse_handler = CallbackHandler()

llm = ChatOpenAI(
    model="Qwen/Qwen3-8B-AWQ",
    base_url="http://localhost:8080/v1/",
    api_key=SecretStr("not-needed"),
)


# Verify connection
try:
    if langfuse.auth_check():
        print("Langfuse client is authenticated and ready!")
    else:
        print("Authentication failed. Please check your credentials and host.")
except Exception as e:
    print(e)


class GraphState(TypedDict):
    messages: Annotated[list[AnyMessage], add]


async def responder(state: GraphState):
    user_query = state["messages"][-1]

    EMBEDDING_MODEL_ID = "BAAI/bge-m3"
    CACHE_DIR = Path("/home/prinzz/main/my-projects/traverse/api/.cache/")
    model = SentenceTransformer(
        EMBEDDING_MODEL_ID,
        device="cuda",
        cache_folder=str(CACHE_DIR),
        local_files_only=True,
    )

    user_query_embedded = model.encode(
        user_query.content,
        batch_size=16,
        normalize_embeddings=True,
        show_progress_bar=True,
    )

    distance_expr = DocumentChunk.text_embedding.cosine_distance(user_query_embedded)  # type: ignore
    similarity_score = (1 - distance_expr).label("similarity")
    db_statement = (
        select(DocumentChunk, similarity_score).order_by(distance_expr).limit(5)
    )

    async with db_session() as session:
        document_chunks = await session.exec(db_statement)
        document_chunks = [document[0].text for document in document_chunks.all()]

    llm_prompt = (
        f"context: {','.join(document_chunks)}, User Question - {user_query.content}"
    )

    response = await llm.ainvoke(
        input=[llm_prompt], config={"callbacks": [langfuse_handler]}
    )

    return {"messages": [response]}


def get_agent():
    graph = StateGraph(state_schema=GraphState)
    graph.add_node("responder", responder)
    graph.set_entry_point("responder")
    graph.set_finish_point("responder")

    return graph.compile()
