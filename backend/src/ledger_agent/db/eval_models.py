from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ledger_agent.db.base import Base


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    model_version: Mapped[str] = mapped_column(String, nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String, nullable=False)
    accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    escalation_precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    escalation_recall: Mapped[float | None] = mapped_column(Float, nullable=True)
