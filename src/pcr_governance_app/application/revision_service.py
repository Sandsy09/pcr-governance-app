from pcr_governance_app.domain.enums import PCRStatus
from pcr_governance_app.domain.errors import PCRImmutableError
from pcr_governance_app.domain.pcr import PCR, PCRContent, PCRRevision

EDITABLE_STATUSES = frozenset({PCRStatus.DRAFT, PCRStatus.CHANGES_REQUIRED})


class PCRRevisionService:
    @staticmethod
    def ensure_editable(pcr: PCR) -> None:
        if pcr.status not in EDITABLE_STATUSES:
            raise PCRImmutableError(
                f"PCR '{pcr.pcr_code}' cannot be edited while in status '{pcr.status}'."
            )

    @classmethod
    def create_revision(
        cls,
        *,
        pcr: PCR,
        content: PCRContent,
        actor: str,
    ) -> PCR:
        cls.ensure_editable(pcr)
        revision_number = cls._next_revision_number(pcr)
        revision = PCRRevision(
            revision_number=revision_number,
            content=content.model_copy(deep=True),
            created_by=actor,
        )
        return pcr.model_copy(update={"revisions": (*pcr.revisions, revision)})

    @staticmethod
    def _next_revision_number(pcr: PCR) -> int:
        if not pcr.revisions:
            return 1

        return max(revision.revision_number for revision in pcr.revisions) + 1
