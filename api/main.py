from fastapi import FastAPI, UploadFile, WebSocket, status
from fastapi.responses import JSONResponse
from langchain_core.messages import HumanMessage
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from .db.engine import engine
from .db.models.document_model import Document
from .llm import get_agent

app = FastAPI()


@app.get("/ping")
async def pong():
    async with AsyncSession(engine) as session:
        statement = select(Document)
        results = await session.exec(statement)
        print(results.fetchall())

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
