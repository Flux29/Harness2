from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel


class Decision(BaseModel):
    answer: str
    confidence: float


def test_pydantic_ai_structured_output_smoke() -> None:
    agent = Agent(TestModel(), output_type=Decision)
    result = agent.run_sync("Return a concise test decision.")
    assert isinstance(result.output, Decision)
    assert result.output.answer
    assert 0 <= result.output.confidence <= 1
