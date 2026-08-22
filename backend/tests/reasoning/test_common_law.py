from src.graph.models import NodeType
from src.reasoning.frameworks.common_law import CommonLawFramework
from src.reasoning.llm.client import FakeLLMClient
from src.retrieval.hybrid import Hit


def test_common_law_prompt_contains_constraints_and_context():
    fw = CommonLawFramework()
    hits = [Hit(NodeType.provision, 1, "Constitution s109", "When a law of a State…", 0.9, "fts"),
            Hit(NodeType.case, 2, "Mabo v Queensland (No 2) [1992] HCA 23", "x" * 2000, 0.5, "graph")]
    msgs = fw.build_messages("Does Commonwealth law prevail?", hits)
    assert msgs[0]["role"] == "system"
    sys_prompt = msgs[0]["content"]
    assert "not legal advice" in sys_prompt
    assert "ONLY" in sys_prompt and "CONTEXT" in sys_prompt
    assert "Precedent" in sys_prompt and "Distinguish" in sys_prompt and "Apply" in sys_prompt
    user = msgs[1]["content"]
    assert "### Constitution s109" in user
    assert "### Mabo v Queensland (No 2) [1992] HCA 23" in user
    assert len(user) < 4000  # truncation applied
    assert user.rstrip().endswith("Does Commonwealth law prevail?")


async def test_fake_llm_streams_and_records():
    llm = FakeLLMClient("alpha beta gamma")
    chunks = [c async for c in llm.stream([{"role": "user", "content": "hi"}])]
    assert "".join(chunks) == "alpha beta gamma"
    assert len(chunks) == 3
    assert llm.last_messages[0]["content"] == "hi"
