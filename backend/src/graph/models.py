from __future__ import annotations

from datetime import date
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import Date, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db import Base

EMBED_DIM = 384


class Extraction(StrEnum):
    curated = "curated"
    parsed = "parsed"
    llm_extracted = "llm_extracted"


class NodeType(StrEnum):
    jurisdiction = "jurisdiction"
    court = "court"
    act = "act"
    provision = "provision"
    case = "case"
    principle = "principle"


class EdgeKind(StrEnum):
    IN_JURISDICTION = "IN_JURISDICTION"
    DECIDED_BY = "DECIDED_BY"
    APPEALS_TO = "APPEALS_TO"
    AUTHORISED_BY = "AUTHORISED_BY"
    AMENDS = "AMENDS"
    INTERPRETS = "INTERPRETS"
    CITES = "CITES"
    HELD_INCONSISTENT = "HELD_INCONSISTENT"
    ESTABLISHES = "ESTABLISHES"
    APPLIES = "APPLIES"
    EVOLVED_INTO = "EVOLVED_INTO"
    CODIFIES = "CODIFIES"


class ProvenanceMixin:
    source_url: Mapped[str | None] = mapped_column(Text)
    source_licence: Mapped[str | None] = mapped_column(String(64))
    extraction: Mapped[Extraction] = mapped_column(String(16), default=Extraction.parsed)


class Jurisdiction(Base):
    __tablename__ = "jurisdictions"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(8), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    level: Mapped[str] = mapped_column(String(16))  # Commonwealth|State|Territory


class Court(Base):
    __tablename__ = "courts"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)  # neutral-citation abbreviation
    name: Mapped[str] = mapped_column(String(128))
    jurisdiction_id: Mapped[int] = mapped_column(ForeignKey("jurisdictions.id"))
    tier: Mapped[int] = mapped_column(Integer)  # 1 = apex
    parent_court_id: Mapped[int | None] = mapped_column(ForeignKey("courts.id"))
    jurisdiction: Mapped[Jurisdiction] = relationship()
    parent_court: Mapped[Court | None] = relationship(remote_side=[id])


class Act(ProvenanceMixin, Base):
    __tablename__ = "acts"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    short_name: Mapped[str] = mapped_column(String(256), index=True)
    year: Mapped[int | None] = mapped_column(Integer)
    jurisdiction_id: Mapped[int] = mapped_column(ForeignKey("jurisdictions.id"))
    status: Mapped[str] = mapped_column(String(16), default="in_force")
    jurisdiction: Mapped[Jurisdiction] = relationship()
    versions: Mapped[list[ActVersion]] = relationship(back_populates="act")
    __table_args__ = (UniqueConstraint("title", "jurisdiction_id", name="uq_act_title_juris"),)


class ActVersion(Base):
    __tablename__ = "act_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    act_id: Mapped[int] = mapped_column(ForeignKey("acts.id"))
    version_id: Mapped[str] = mapped_column(String(64), unique=True)  # source's id
    in_force_from: Mapped[date | None] = mapped_column(Date)
    in_force_to: Mapped[date | None] = mapped_column(Date)
    source_url: Mapped[str | None] = mapped_column(Text)
    act: Mapped[Act] = relationship(back_populates="versions")
    provisions: Mapped[list[Provision]] = relationship(back_populates="act_version")


class Provision(Base):
    __tablename__ = "provisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    act_version_id: Mapped[int] = mapped_column(ForeignKey("act_versions.id"))
    identifier: Mapped[str] = mapped_column(String(64))  # "s51(xx)"
    heading: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    parent_provision_id: Mapped[int | None] = mapped_column(ForeignKey("provisions.id"))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM))
    tsv: Mapped[str | None] = mapped_column(TSVECTOR)
    act_version: Mapped[ActVersion] = relationship(back_populates="provisions")
    parent: Mapped[Provision | None] = relationship(remote_side=[id])
    __table_args__ = (
        UniqueConstraint("act_version_id", "identifier", name="uq_provision_ident"),
        Index("ix_provisions_tsv", "tsv", postgresql_using="gin"),
    )


class Case(ProvenanceMixin, Base):
    __tablename__ = "cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    neutral_citation: Mapped[str] = mapped_column(String(64), unique=True)
    court_id: Mapped[int] = mapped_column(ForeignKey("courts.id"))
    decided_on: Mapped[date | None] = mapped_column(Date)
    summary: Mapped[str | None] = mapped_column(Text)
    court: Mapped[Court] = relationship()
    judgments: Mapped[list[Judgment]] = relationship(back_populates="case")


class Judgment(Base):
    __tablename__ = "judgments"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"))
    judges: Mapped[str | None] = mapped_column(Text)
    disposition: Mapped[str] = mapped_column(String(16), default="majority")
    case: Mapped[Case] = relationship(back_populates="judgments")
    paragraphs: Mapped[list[Paragraph]] = relationship(back_populates="judgment")


class Paragraph(Base):
    __tablename__ = "paragraphs"
    id: Mapped[int] = mapped_column(primary_key=True)
    judgment_id: Mapped[int] = mapped_column(ForeignKey("judgments.id"))
    number: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM))
    tsv: Mapped[str | None] = mapped_column(TSVECTOR)
    judgment: Mapped[Judgment] = relationship(back_populates="paragraphs")
    __table_args__ = (
        UniqueConstraint("judgment_id", "number", name="uq_paragraph_number"),
        Index("ix_paragraphs_tsv", "tsv", postgresql_using="gin"),
    )


class Principle(ProvenanceMixin, Base):
    __tablename__ = "principles"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(256), unique=True)
    statement: Mapped[str] = mapped_column(Text)


class Edge(Base):
    __tablename__ = "edges"
    id: Mapped[int] = mapped_column(primary_key=True)
    src_type: Mapped[NodeType] = mapped_column(String(16))
    src_id: Mapped[int] = mapped_column(Integer)
    dst_type: Mapped[NodeType] = mapped_column(String(16))
    dst_id: Mapped[int] = mapped_column(Integer)
    kind: Mapped[EdgeKind] = mapped_column(String(24))
    treatment: Mapped[str | None] = mapped_column(String(16))
    source_url: Mapped[str | None] = mapped_column(Text)
    extraction: Mapped[Extraction] = mapped_column(String(16), default=Extraction.parsed)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    evidence_case_id: Mapped[int | None] = mapped_column(ForeignKey("cases.id"))
    __table_args__ = (
        UniqueConstraint("src_type", "src_id", "dst_type", "dst_id", "kind", name="uq_edge"),
        Index("ix_edges_src", "src_type", "src_id"),
        Index("ix_edges_dst", "dst_type", "dst_id"),
    )
