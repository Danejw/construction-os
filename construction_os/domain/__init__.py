"""
Domain models for Construction OS.

This module exports the core domain models used throughout the application.
Importing this package registers ObjectModel subclasses for polymorphic get().
"""

from construction_os.domain.artifact import Artifact, ArtifactTemplate, DefaultPrompts
from construction_os.domain.artifact_review import ArtifactReviewRun
from construction_os.domain.collection import Collection, CollectionItem
from construction_os.domain.base import ObjectModel, RecordModel
from construction_os.domain.chat_queue import (
    ChatQueue,
    ChatQueueItem,
    ChatQueueRepository,
    RunnerFinalizationResult,
)
from construction_os.domain.html_document import Document, HtmlTemplate
from construction_os.domain.knowledge_graph import (
    KgClaim,
    KgEntity,
    KgExtractionRun,
    KgMention,
    KgRelation,
)
from construction_os.domain.media_asset import MediaAsset
from construction_os.domain.opportunity import Opportunity, OpportunityChange, OpportunitySource
from construction_os.domain.opportunity_scoring_profile import OpportunityScoringSettings
from construction_os.domain.project import (
    Asset,
    ChatSession,
    Note,
    Project,
    ProjectArtifact,
    Source,
    SourceEmbedding,
    text_search,
    vector_search,
)

__all__ = [
    "Artifact",
    "ArtifactReviewRun",
    "ArtifactTemplate",
    "Asset",
    "ChatSession",
    "Collection",
    "CollectionItem",
    "ChatQueue",
    "ChatQueueItem",
    "ChatQueueRepository",
    "RunnerFinalizationResult",
    "DefaultPrompts",
    "Document",
    "HtmlTemplate",
    "MediaAsset",
    "KgClaim",
    "KgEntity",
    "KgExtractionRun",
    "KgMention",
    "KgRelation",
    "Note",
    "ObjectModel",
    "Opportunity",
    "OpportunityChange",
    "OpportunitySource",
    "OpportunityScoringSettings",
    "Project",
    "ProjectArtifact",
    "RecordModel",
    "Source",
    "SourceEmbedding",
    "text_search",
    "vector_search",
]
