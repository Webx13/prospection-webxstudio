"""Socle multi-tenant : organisations, utilisateurs, appartenances.

Toute donnée métier future (projets, fichiers, exécutions…) référencera ``organizations.id``
pour que l'isolation par organisation soit imposée au niveau du schéma.
"""

from __future__ import annotations

import enum
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from blackforge_api.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class MemberRole(enum.StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(63), nullable=False, unique=True)

    memberships: Mapped[list[Membership]] = relationship(back_populates="organization")

    __table_args__ = (CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="slug_format"),)


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120))
    # Identifiant du sujet chez le fournisseur d'authentification (Supabase ``sub``).
    auth_subject: Mapped[str | None] = mapped_column(String(255), unique=True)
    locale: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'fr'"))
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))

    memberships: Mapped[list[Membership]] = relationship(back_populates="user")

    __table_args__ = (
        # Unicité insensible à la casse sans extension citext.
        Index("uq_users_email_lower", func.lower(email), unique=True),
    )


class Membership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "memberships"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)

    organization: Mapped[Organization] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")

    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_memberships_org_user"),
        CheckConstraint("role IN ('owner', 'admin', 'member', 'viewer')", name="role_allowed"),
        Index("ix_memberships_user_id", "user_id"),
    )
