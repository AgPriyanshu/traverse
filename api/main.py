from pathlib import Path

from fastapi import FastAPI, UploadFile, WebSocket, status
from fastapi.logger import logger
from fastapi.responses import JSONResponse
from langchain_core.messages import HumanMessage

from .document_pipeline.chunking import DocumentChunker
from .llm import get_agent

app = FastAPI()


@app.get("/ping")
async def pong():
    documentChunker = DocumentChunker()
    docling_document = documentChunker.load_document(
        Path("./sample_docs/before_the_coffee_gets_cold.pdf")
    )
    chunks = documentChunker.generate_chunks(docling_document)
    logger.debug(chunks)

    return {"message": "pong"}


@app.post("/generate-embeddings")
async def generate_embeddings(file: UploadFile):
    from .tasks import embed_file

    embed_file.delay(await file.read())
    return JSONResponse(
        {"message": "File accepted for embedding"}, status_code=status.HTTP_202_ACCEPTED
    )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    while True:
        data = await websocket.receive_text()
        await websocket.send_text(f"Message text was: {data}")
        agent = get_agent()
        answer = await agent.ainvoke({"messages": [HumanMessage(content=data)]})
        await websocket.send_text(f"LLM response: {answer['messages'][-1].content}")
