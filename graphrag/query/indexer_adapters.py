# Copyright (c) 2024 Microsoft Corporation.
# Licensed under the MIT License
"""Indexing-Engine to Query Read Adapters.

The parts of these functions that do type adaptation, renaming, collating, etc. should eventually go away.
Ideally this is just a straight read-through into the object model.
"""

import logging
from typing import cast

import pandas as pd

from graphrag.config.models.graph_rag_config import GraphRagConfig
from graphrag.index.operations.summarize_communities import restore_community_hierarchy
from graphrag.model import (
    Community,
    CommunityReport,
    Covariate,
    Entity,
    Relationship,
    TextUnit,
)
from graphrag.query.factories import get_text_embedder
from graphrag.query.input.loaders.dfs import (
    read_communities,
    read_community_reports,
    read_covariates,
    read_entities,
    read_relationships,
    read_text_units,
)
from graphrag.query.llm.oai.embedding import OpenAIEmbedding
from graphrag.vector_stores.base import BaseVectorStore

log = logging.getLogger(__name__)


def read_indexer_text_units(final_text_units: pd.DataFrame) -> list[TextUnit]:
    """Read in the Text Units from the raw indexing outputs."""
    return read_text_units(
        df=final_text_units,
        short_id_col=None,
        # expects a covariate map of type -> ids
        covariates_col=None,
    )


def read_indexer_covariates(final_covariates: pd.DataFrame) -> list[Covariate]:
    """Read in the Claims from the raw indexing outputs."""
    covariate_df = final_covariates
    covariate_df["id"] = covariate_df["id"].astype(str)
    return read_covariates(
        df=covariate_df,
        short_id_col="human_readable_id",
        attributes_cols=[
            "object_id",
            "status",
            "start_date",
            "end_date",
            "description",
        ],
        text_unit_ids_col=None,
    )


def read_indexer_relationships(final_relationships: pd.DataFrame) -> list[Relationship]:
    """Read in the Relationships from the raw indexing outputs."""
    return read_relationships(
        df=final_relationships,
        short_id_col="human_readable_id",
        description_embedding_col=None,
        document_ids_col=None,
        attributes_cols=["rank"],
    )


def read_indexer_reports(
    final_community_reports: pd.DataFrame,
    final_nodes: pd.DataFrame,
    community_level: int | None,
    dynamic_community_selection: bool = False,
    content_embedding_col: str = "full_content_embedding",
    config: GraphRagConfig | None = None,
) -> list[CommunityReport]:
    """Read in the Community Reports from the raw indexing outputs.

    If not dynamic_community_selection, then select reports with the max community level that an entity belongs to.
    """
    report_df = final_community_reports
    entity_df = final_nodes
    if community_level is not None:
        entity_df = _filter_under_community_level(entity_df, community_level)
        report_df = _filter_under_community_level(report_df, community_level)

    if not dynamic_community_selection:
        # perform community level roll up
        entity_df.loc[:, "community"] = entity_df["community"].fillna(-1)
        entity_df.loc[:, "community"] = entity_df["community"].astype(int)

        entity_df = entity_df.groupby(["title"]).agg({"community": "max"}).reset_index()
        entity_df["community"] = entity_df["community"].astype(str)
        filtered_community_df = entity_df["community"].drop_duplicates()

        report_df = report_df.merge(filtered_community_df, on="community", how="inner")

    if config and (
        content_embedding_col not in report_df.columns
        or report_df.loc[:, content_embedding_col].isna().any()
    ):
        embedder = get_text_embedder(config)
        report_df = embed_community_reports(
            report_df, embedder, embedding_col=content_embedding_col
        )

    return read_community_reports(
        df=report_df,
        id_col="id",
        short_id_col="community",
        summary_embedding_col=None,
        content_embedding_col=content_embedding_col,
    )


def read_indexer_report_embeddings(
    community_reports: list[CommunityReport],
    embeddings_store: BaseVectorStore,
):
    """Read in the Community Reports from the raw indexing outputs."""
    for report in community_reports:
        report.full_content_embedding = embeddings_store.search_by_id(report.id).vector


def read_indexer_entities(
    final_nodes: pd.DataFrame,
    final_entities: pd.DataFrame,
    community_level: int | None,
) -> list[Entity]:
    """Read in the Entities from the raw indexing outputs."""
    entity_df = final_nodes
    entity_embedding_df = final_entities

    if community_level is not None:
        entity_df = _filter_under_community_level(entity_df, community_level)

    entity_df = cast(pd.DataFrame, entity_df[["title", "degree", "community"]]).rename(
        columns={"title": "name", "degree": "rank"}
    )

    entity_df["community"] = entity_df["community"].fillna(-1)
    entity_df["community"] = entity_df["community"].astype(int)
    entity_df["rank"] = entity_df["rank"].astype(int)

    # group entities by name and rank and remove duplicated community IDs
    entity_df = (
        entity_df.groupby(["name", "rank"]).agg({"community": set}).reset_index()
    )
    entity_df["community"] = entity_df["community"].apply(lambda x: [str(i) for i in x])
    entity_df = entity_df.merge(
        entity_embedding_df, on="name", how="inner"
    ).drop_duplicates(subset=["name"])

    # read entity dataframe to knowledge model objects
    return read_entities(
        df=entity_df,
        id_col="id",
        title_col="name",
        type_col="type",
        short_id_col="human_readable_id",
        description_col="description",
        community_col="community",
        rank_col="rank",
        name_embedding_col=None,
        description_embedding_col="description_embedding",
        graph_embedding_col=None,
        text_unit_ids_col="text_unit_ids",
        document_ids_col=None,
    )


def read_indexer_communities(
    final_communities: pd.DataFrame,
    final_nodes: pd.DataFrame,
    final_community_reports: pd.DataFrame,
) -> list[Community]:
    """Read in the Communities from the raw indexing outputs.

    Reconstruct the community hierarchy information and add to the sub-community field.
    """
    community_df = final_communities
    node_df = final_nodes
    report_df = final_community_reports

    # ensure communities matches community reports
    missing_reports = community_df[
        ~community_df.id.isin(report_df.community.unique())
    ].id.to_list()
    if len(missing_reports):
        log.warning("Missing reports for communities: %s", missing_reports)
        community_df = community_df.loc[
            community_df.id.isin(report_df.community.unique())
        ]
        node_df = node_df.loc[node_df.community.isin(report_df.community.unique())]

    # reconstruct the community hierarchy
    # note that restore_community_hierarchy only return communities with sub communities
    community_hierarchy = restore_community_hierarchy(input=node_df)
    community_hierarchy = (
        community_hierarchy.groupby(["community"])
        .agg({"sub_community": list})
        .reset_index()
        .rename(columns={"community": "id", "sub_community": "sub_community_ids"})
    )
    # add sub community IDs to community DataFrame
    community_df = community_df.merge(community_hierarchy, on="id", how="left")
    # replace NaN sub community IDs with empty list
    community_df.sub_community_ids = community_df.sub_community_ids.apply(
        lambda x: x if isinstance(x, list) else []
    )

    return read_communities(
        community_df,
        id_col="id",
        short_id_col="id",
        title_col="title",
        level_col="level",
        entities_col=None,
        relationships_col=None,
        covariates_col=None,
        sub_communities_col="sub_community_ids",
        attributes_cols=None,
    )


def embed_community_reports(
    reports_df: pd.DataFrame,
    embedder: OpenAIEmbedding,
    source_col: str = "full_content",
    embedding_col: str = "full_content_embedding",
) -> pd.DataFrame:
    """Embed a source column of the reports dataframe using the given embedder."""
    if source_col not in reports_df.columns:
        error_msg = f"Reports missing {source_col} column"
        raise ValueError(error_msg)

    if embedding_col not in reports_df.columns:
        reports_df[embedding_col] = reports_df.loc[:, source_col].apply(
            lambda x: embedder.embed(x)
        )

    return reports_df


def _filter_under_community_level(
    df: pd.DataFrame, community_level: int
) -> pd.DataFrame:
    return cast(
        pd.DataFrame,
        df[df.level <= community_level],
    )
