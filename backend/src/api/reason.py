import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from src.api.deps import get_db, get_embedder, get_llm
from src.graph.models import NodeType
from src.graph.traversal import node_ref
from src.reasoning.frameworks.base import BaseFramework
from src.reasoning.frameworks.common_law import CommonLawFramework
from src.reasoning.modes.reverse_engineering import ReverseEngineeringMode

router = APIRouter(prefix="/reason", tags=["reason"])

FRAMEWORKS: dict[str, type[BaseFramework]] = {CommonLawFramework.name: CommonLawFramework}


class ReverseRequest(BaseModel):
    node_type: NodeType
    node_id: int
    framework: str = "common_law"


@router.get("/frameworks")
def list_frameworks() -> list[str]:
    return list(FRAMEWORKS)


@router.post("/reverse")
async def reverse(req: ReverseRequest, session: Session = Depends(get_db)):  # noqa: B008
    if req.framework not in FRAMEWORKS:
        raise HTTPException(422, f"unknown framework {req.framework}")
    if node_ref(session, req.node_type, req.node_id) is None:
        raise HTTPException(404, "node not found")
    mode = ReverseEngineeringMode()
    llm, embedder, framework = get_llm(), get_embedder(), FRAMEWORKS[req.framework]()

    async def gen():
        async for ev in mode.run(session, llm, framework, embedder,
                                 node_type=req.node_type, node_id=req.node_id):
            yield {"event": ev.kind, "data": json.dumps(ev.payload)}

    return EventSourceResponse(gen(), sep="\n")
