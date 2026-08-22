import json
import logging

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

logger = logging.getLogger(__name__)

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
        # Any mid-stream failure must still terminate the SSE body with an explicit
        # `error` event: a truncated stream would leave the client holding unverified
        # `token` prose that looks identical to a verified answer.
        try:
            async for ev in mode.run(session, llm, framework, embedder,
                                     node_type=req.node_type, node_id=req.node_id):
                yield {"event": ev.kind, "data": json.dumps(ev.payload)}
        except Exception:
            logger.exception("reasoning stream failed for %s:%s", req.node_type, req.node_id)
            yield {"event": "error", "data": json.dumps(
                {"message": "reasoning failed before verification completed", "verified": False})}

    return EventSourceResponse(gen(), sep="\n")
