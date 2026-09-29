"""Automated Reviewer for worker proposals."""

from dosimeter.evaluation.judge import Verdict, judge_claim
from dosimeter.graph.schemas import ReviewerVerdict
from dosimeter.graph.state import GraphState


def reviewer_node(state: GraphState) -> dict:
    """Review worker proposals for grounding, citations, and rule attribution."""

    iteration = state.get("reviewer_iterations", 0) + 1
    proposals = state.get("proposals") or {}
    retrieval_log = state.get("retrieval_log") or []
    rule_invocations = state.get("rule_invocations") or []

    verdicts = []

    for worker, proposal in proposals.items():

        # 1. Citation check
        if not proposal.citations:
            verdicts.append(
                ReviewerVerdict(
                    iteration=iteration,
                    worker=worker,
                    verdict="rejected",
                    reason="Worker proposal has no citations.",
                )
            )
            continue

        # 2. Rule attribution check
        if worker in {"notification", "written_report"}:
            if not proposal.payload.get("rule_results"):
                verdicts.append(
                    ReviewerVerdict(
                        iteration=iteration,
                        worker=worker,
                        verdict="rejected",
                        reason="Determination has no deterministic rule results.",
                    )
                )
                continue

            if not rule_invocations:
                verdicts.append(
                    ReviewerVerdict(
                        iteration=iteration,
                        worker=worker,
                        verdict="rejected",
                        reason="No recorded rule invocation supports the determination.",
                    )
                )
                continue

        # 3. Find cited source and check status/grounding
        approved = True
        reason = "Proposal passed automated review."

        for citation in proposal.citations:
            source = next(
                (
                    source
                    for entry in retrieval_log
                    for source in entry.get("sources", [])
                    if source.get("chunk_id") == citation
                ),
                None,
            )

            if source is None:
                approved = False
                reason = f"Citation could not be resolved: {citation}"
                break

            # Current determinations cannot rely on proposed rules.
            if source.get("status") == "proposed":
                approved = False
                reason = f"Determination relies on proposed material: {citation}"
                break

            judged = judge_claim(
                claim=proposal.payload.get("explanation", ""),
                chunk_id=citation,
                chunk_text=source.get("text", ""),
                settings=__import__(
                    "dosimeter.config.settings",
                    fromlist=["get_settings"],
                ).get_settings(),
            )

            if judged.verdict != Verdict.SUPPORTED:
                approved = False
                reason = judged.reason
                break

        verdicts.append(
            ReviewerVerdict(
                iteration=iteration,
                worker=worker,
                verdict="approved" if approved else "rejected",
                reason=reason,
            )
        )

    return {
        "reviewer_verdicts": verdicts,
        "reviewer_iterations": iteration,
    }


def route_after_reviewer(
    state: GraphState,
    iteration_cap: int,
) -> str:
    """Return to the Coordinator when any worker proposal is rejected."""

    verdicts = state.get("reviewer_verdicts") or []
    iterations = state.get("reviewer_iterations", 0)

    current = [
        verdict for verdict in verdicts
        if verdict.iteration == iterations
    ]

    if iterations >= iteration_cap:
        return "eligibility_check"

    if any(verdict.verdict == "rejected" for verdict in current):
        return "coordinator"

    return "eligibility_check"