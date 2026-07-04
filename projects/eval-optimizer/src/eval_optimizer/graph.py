"""Workstream B: the pydantic-graph (2.x) orchestration substrate.

Stage flow (from Schema.txt):

    Plan -> Generate -> Criticize -> Rank -> Validate
                 ^                              |
                 └───────── regen (bounded) ────┘

The plan is produced ONCE and is immutable; regeneration loops back to Generate,
never to Plan. State is serializable (so pydantic-graph can persist/resume it);
the persistence side-channel lives in `deps`, not `state`.

NODE LOGIC IS STUBBED in Workstream B — deterministic, no LLM calls — so we can
verify the wiring, the regen edge, and Postgres persistence cheaply. Workstream C
replaces each `# TODO(C)` block with the real Planner / Generators / Critics.

pydantic-graph 2.x notes (verified against 2.1.0):
  * Each node is registered with `builder.add(builder.node(Cls))`; node->node and
    node->End edges are inferred from each run()'s return annotations.
  * Only the entry edge (start -> Plan) is declared explicitly.
  * `build(validate_graph_structure=False)` — the runtime navigates via the node
    instance each run() returns (End(...) terminates), so structural validation
    isn't required and its End-edge inference is stricter than we need.
  * The first node instance is passed at run time via `inputs=Plan()`.
  * Node class names MUST NOT collide with the schema model names (hence the
    node is `Criticize`, the model is `Critique`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic_graph import BaseNode, End, GraphBuilder, GraphRunContext

from .schema import (
    DIMENSION_WEIGHTS,
    DIMENSIONS,
    Candidate,
    Critique,
    ExecutionPlan,
    PipelineResult,
    RankedCandidate,
)

# A persister takes (node_name, state_snapshot_dict). Kept in deps so it never
# has to be serialized as part of graph state.
Persister = Callable[[str, dict[str, Any]], None]


@dataclass
class PipelineDeps:
    persister: Persister | None = None


@dataclass
class PipelineState:
    task: str
    beam_width: int = 3
    max_iterations: int = 3
    iteration: int = 0
    plan: ExecutionPlan | None = None
    candidates: list[Candidate] = field(default_factory=list)
    critiques: list[Critique] = field(default_factory=list)
    ranking: list[RankedCandidate] = field(default_factory=list)
    selected: Candidate | None = None
    failures: list[str] = field(default_factory=list)


def _snapshot(ctx: GraphRunContext[PipelineState, PipelineDeps], node: str) -> None:
    persister = ctx.deps.persister
    if persister is None:
        return
    st = ctx.state
    persister(
        node,
        {
            "task": st.task,
            "iteration": st.iteration,
            "node": node,
            "selected": st.selected.id if st.selected else None,
            "n_candidates": len(st.candidates),
            "failures": list(st.failures),
        },
    )


@dataclass
class Plan(BaseNode[PipelineState, PipelineDeps]):
    async def run(self, ctx: GraphRunContext[PipelineState, PipelineDeps]) -> Generate:
        # TODO(C): replace with the Planner agent (thinking="high") emitting an
        # ExecutionPlan from ctx.state.task.
        ctx.state.plan = ExecutionPlan(
            goal=ctx.state.task,
            steps=["analyze task", "design modules", "implement", "verify"],
            modules=["main"],
            functions=[],
        )
        _snapshot(ctx, "plan")
        return Generate()


@dataclass
class Generate(BaseNode[PipelineState, PipelineDeps]):
    async def run(self, ctx: GraphRunContext[PipelineState, PipelineDeps]) -> Criticize:
        ctx.state.iteration += 1
        # TODO(C): replace with N parallel Generator agents (thinking="low"/"medium")
        # producing diverse candidates from the immutable plan + prior feedback.
        approaches = ["recursive", "iterative-stack", "library-based"]
        ctx.state.candidates = [
            Candidate(
                id=f"cand-{ctx.state.iteration}-{i}",
                approach=approaches[i % len(approaches)],
                artifact=f"# stub artifact ({approaches[i % len(approaches)]}) for: {ctx.state.task}",
                generator=f"gen-{i}",
            )
            for i in range(ctx.state.beam_width)
        ]
        _snapshot(ctx, "generate")
        return Criticize()


@dataclass
class Criticize(BaseNode[PipelineState, PipelineDeps]):
    async def run(self, ctx: GraphRunContext[PipelineState, PipelineDeps]) -> Rank:
        # TODO(C): replace with three Debate Critics (thinking="high"):
        # Correctness / Architecture / Performance, each returning a Critique.
        critiques: list[Critique] = []
        for ci, cand in enumerate(ctx.state.candidates):
            for di, dim in enumerate(DIMENSIONS):
                # deterministic stub: later candidates stronger, and everything
                # improves on the 2nd iteration (exercises the regen edge).
                base = 5 + ci + (2 if ctx.state.iteration >= 2 else 0)
                score = max(0, min(10, base - di))
                critiques.append(
                    Critique(
                        candidate_id=cand.id,
                        dimension=dim,
                        passed=score >= 6,
                        score=score,
                        findings=[] if score >= 6 else [f"{dim}: stub finding"],
                    )
                )
        ctx.state.critiques = critiques
        _snapshot(ctx, "critique")
        return Rank()


@dataclass
class Rank(BaseNode[PipelineState, PipelineDeps]):
    async def run(self, ctx: GraphRunContext[PipelineState, PipelineDeps]) -> Validate:
        # Weighted scoring matrix over the critiques (real logic, not a stub).
        per_cand: dict[str, dict[str, int]] = {}
        for c in ctx.state.critiques:
            per_cand.setdefault(c.candidate_id, {})[c.dimension] = c.score

        ranking: list[RankedCandidate] = []
        for cand_id, dims in per_cand.items():
            total = sum(dims.get(d, 0) * DIMENSION_WEIGHTS.get(d, 0.0) for d in DIMENSIONS)
            ranking.append(
                RankedCandidate(candidate_id=cand_id, total_score=round(total, 3), per_dimension=dims)
            )
        ranking.sort(key=lambda r: r.total_score, reverse=True)
        ctx.state.ranking = ranking

        top_id = ranking[0].candidate_id if ranking else None
        ctx.state.selected = next((c for c in ctx.state.candidates if c.id == top_id), None)
        _snapshot(ctx, "rank")
        return Validate()


@dataclass
class Validate(BaseNode[PipelineState, PipelineDeps]):
    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps]
    ) -> Generate | End[PipelineResult]:
        # TODO(C): real validation — syntax -> static analysis -> unit tests ->
        # runtime execution INSIDE the pydantic-deep Docker sandbox.
        top = ctx.state.ranking[0].total_score if ctx.state.ranking else 0.0
        passed = top >= 7.0

        if passed:
            _snapshot(ctx, "validate:pass")
            return End(
                PipelineResult(
                    passed=True,
                    iterations=ctx.state.iteration,
                    selected=ctx.state.selected,
                    plan=ctx.state.plan,
                    ranking=ctx.state.ranking,
                    failures=ctx.state.failures,
                )
            )

        ctx.state.failures.append(f"iter {ctx.state.iteration}: top score {top:.2f} < 7.0")
        if ctx.state.iteration >= ctx.state.max_iterations:
            _snapshot(ctx, "validate:exhausted")
            return End(
                PipelineResult(
                    passed=False,
                    iterations=ctx.state.iteration,
                    selected=ctx.state.selected,
                    plan=ctx.state.plan,
                    ranking=ctx.state.ranking,
                    failures=ctx.state.failures,
                )
            )

        _snapshot(ctx, "validate:regen")
        return Generate()  # targeted regeneration; plan stays fixed


def _build_graph():
    """Assemble the pipeline graph (pydantic-graph 2.x GraphBuilder API)."""
    b = GraphBuilder(
        state_type=PipelineState,
        deps_type=PipelineDeps,
        output_type=PipelineResult,
    )
    for node_cls in (Plan, Generate, Criticize, Rank, Validate):
        b.add(b.node(node_cls))
    b.add(b.edge_from(b.start_node).to(Plan))
    # Runtime navigates via the node instance each run() returns; End(...) ends
    # the run. Structural validation isn't needed and is stricter than we want.
    return b.build(validate_graph_structure=False)


pipeline_graph = _build_graph()


async def run_pipeline(
    task: str,
    *,
    persister: Persister | None = None,
    beam_width: int = 3,
    max_iterations: int = 3,
) -> PipelineResult:
    """Run the full pipeline graph and return the terminal PipelineResult."""
    state = PipelineState(task=task, beam_width=beam_width, max_iterations=max_iterations)
    deps = PipelineDeps(persister=persister)
    return await pipeline_graph.run(inputs=Plan(), state=state, deps=deps)
