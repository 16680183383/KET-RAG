# Copyright (c) 2024 Microsoft Corporation.
# Licensed under the MIT License

"""
Query Engine API.

This API provides access to the query engine of graphrag, allowing external applications
to hook into graphrag and run queries over a knowledge graph generated by graphrag.

Contains the following functions:
 - global_search: Perform a global search.
 - global_search_streaming: Perform a global search and stream results back.
 - local_search: Perform a local search.
 - local_search_streaming: Perform a local search and stream results back.

WARNING: This API is under development and may undergo changes in future releases.
Backwards compatibility is not guaranteed at this time.
"""

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import validate_call

from graphrag.config import GraphRagConfig
from graphrag.logging import PrintProgressReporter
from graphrag.query.factories import (
    get_drift_search_engine,
    get_global_search_engine,
    get_local_search_engine,
)
from graphrag.query.indexer_adapters import (
    read_indexer_communities,
    read_indexer_covariates,
    read_indexer_entities,
    read_indexer_relationships,
    read_indexer_report_embeddings,
    read_indexer_reports,
    read_indexer_text_units,
)
from graphrag.query.structured_search.base import SearchResult  # noqa: TCH001
from graphrag.utils.cli import redact
from graphrag.vector_stores import VectorStoreFactory, VectorStoreType
from graphrag.vector_stores.base import BaseVectorStore

reporter = PrintProgressReporter("")


@validate_call(config={"arbitrary_types_allowed": True})
async def global_search(
    config: GraphRagConfig,
    nodes: pd.DataFrame,
    entities: pd.DataFrame,
    communities: pd.DataFrame,
    community_reports: pd.DataFrame,
    community_level: int | None,
    dynamic_community_selection: bool,
    response_type: str,
    query: str,
) -> tuple[
    str | dict[str, Any] | list[dict[str, Any]],
    str | list[pd.DataFrame] | dict[str, pd.DataFrame],
]:
    """Perform a global search and return the context data and response.

    Parameters
    ----------
    - config (GraphRagConfig): A graphrag configuration (from settings.yaml)
    - nodes (pd.DataFrame): A DataFrame containing the final nodes (from create_final_nodes.parquet)
    - entities (pd.DataFrame): A DataFrame containing the final entities (from create_final_entities.parquet)
    - communities (pd.DataFrame): A DataFrame containing the final communities (from create_final_communities.parquet)
    - community_reports (pd.DataFrame): A DataFrame containing the final community reports (from create_final_community_reports.parquet)
    - community_level (int): The community level to search at.
    - dynamic_community_selection (bool): Enable dynamic community selection instead of using all community reports at a fixed level. Note that you can still provide community_level cap the maximum level to search.
    - response_type (str): The type of response to return.
    - query (str): The user query to search for.

    Returns
    -------
    TODO: Document the search response type and format.

    Raises
    ------
    TODO: Document any exceptions to expect.
    """
    _communities = read_indexer_communities(communities, nodes, community_reports)
    reports = read_indexer_reports(
        community_reports,
        nodes,
        community_level=community_level,
        dynamic_community_selection=dynamic_community_selection,
    )
    _entities = read_indexer_entities(nodes, entities, community_level=community_level)
    search_engine = get_global_search_engine(
        config,
        reports=reports,
        entities=_entities,
        communities=_communities,
        response_type=response_type,
        dynamic_community_selection=dynamic_community_selection,
    )
    result: SearchResult = await search_engine.asearch(query=query)
    response = result.response
    context_data = _reformat_context_data(result.context_data)  # type: ignore
    return response, context_data


@validate_call(config={"arbitrary_types_allowed": True})
async def global_search_streaming(
    config: GraphRagConfig,
    nodes: pd.DataFrame,
    entities: pd.DataFrame,
    communities: pd.DataFrame,
    community_reports: pd.DataFrame,
    community_level: int | None,
    dynamic_community_selection: bool,
    response_type: str,
    query: str,
) -> AsyncGenerator:
    """Perform a global search and return the context data and response via a generator.

    Context data is returned as a dictionary of lists, with one list entry for each record.

    Parameters
    ----------
    - config (GraphRagConfig): A graphrag configuration (from settings.yaml)
    - nodes (pd.DataFrame): A DataFrame containing the final nodes (from create_final_nodes.parquet)
    - entities (pd.DataFrame): A DataFrame containing the final entities (from create_final_entities.parquet)
    - communities (pd.DataFrame): A DataFrame containing the final communities (from create_final_communities.parquet)
    - community_reports (pd.DataFrame): A DataFrame containing the final community reports (from create_final_community_reports.parquet)
    - community_level (int): The community level to search at.
    - dynamic_community_selection (bool): Enable dynamic community selection instead of using all community reports at a fixed level. Note that you can still provide community_level cap the maximum level to search.
    - response_type (str): The type of response to return.
    - query (str): The user query to search for.

    Returns
    -------
    TODO: Document the search response type and format.

    Raises
    ------
    TODO: Document any exceptions to expect.
    """
    _communities = read_indexer_communities(communities, nodes, community_reports)
    reports = read_indexer_reports(
        community_reports,
        nodes,
        community_level=community_level,
        dynamic_community_selection=dynamic_community_selection,
    )
    _entities = read_indexer_entities(nodes, entities, community_level=community_level)
    search_engine = get_global_search_engine(
        config,
        reports=reports,
        entities=_entities,
        communities=_communities,
        response_type=response_type,
        dynamic_community_selection=dynamic_community_selection,
    )
    search_result = search_engine.astream_search(query=query)

    # when streaming results, a context data object is returned as the first result
    # and the query response in subsequent tokens
    context_data = None
    get_context_data = True
    async for stream_chunk in search_result:
        if get_context_data:
            context_data = _reformat_context_data(stream_chunk)  # type: ignore
            yield context_data
            get_context_data = False
        else:
            yield stream_chunk


@validate_call(config={"arbitrary_types_allowed": True})
async def local_search(
    config: GraphRagConfig,
    nodes: pd.DataFrame,
    entities: pd.DataFrame,
    community_reports: pd.DataFrame,
    text_units: pd.DataFrame,
    relationships: pd.DataFrame,
    covariates: pd.DataFrame | None,
    community_level: int,
    response_type: str,
    query: str,
) -> tuple[
    str | dict[str, Any] | list[dict[str, Any]],
    str | list[pd.DataFrame] | dict[str, pd.DataFrame],
]:
    """Perform a local search and return the context data and response.

    Parameters
    ----------
    - config (GraphRagConfig): A graphrag configuration (from settings.yaml)
    - nodes (pd.DataFrame): A DataFrame containing the final nodes (from create_final_nodes.parquet)
    - entities (pd.DataFrame): A DataFrame containing the final entities (from create_final_entities.parquet)
    - community_reports (pd.DataFrame): A DataFrame containing the final community reports (from create_final_community_reports.parquet)
    - text_units (pd.DataFrame): A DataFrame containing the final text units (from create_final_text_units.parquet)
    - relationships (pd.DataFrame): A DataFrame containing the final relationships (from create_final_relationships.parquet)
    - covariates (pd.DataFrame): A DataFrame containing the final covariates (from create_final_covariates.parquet)
    - community_level (int): The community level to search at.
    - response_type (str): The response type to return.
    - query (str): The user query to search for.

    Returns
    -------
    TODO: Document the search response type and format.

    Raises
    ------
    TODO: Document any exceptions to expect.
    """
    config = _patch_vector_store(config, nodes, entities, community_level)

    # TODO: update filepath of lancedb (if used) until the new config engine has been implemented
    # TODO: remove the type ignore annotations below once the new config engine has been refactored
    vector_store_type = config.embeddings.vector_store.get("type")  # type: ignore
    vector_store_args = config.embeddings.vector_store
    if vector_store_type == VectorStoreType.LanceDB:
        db_uri = config.embeddings.vector_store["db_uri"]  # type: ignore
        lancedb_dir = Path(config.root_dir).resolve() / db_uri
        vector_store_args["db_uri"] = str(lancedb_dir)  # type: ignore

    reporter.info(f"Vector Store Args: {redact(vector_store_args)}")  # type: ignore

    description_embedding_store = _get_embedding_store(
        config_args=vector_store_args,  # type: ignore
        container_suffix="entity-description",
    )

    _entities = read_indexer_entities(nodes, entities, community_level)
    _covariates = read_indexer_covariates(covariates) if covariates is not None else []

    search_engine = get_local_search_engine(
        config=config,
        reports=read_indexer_reports(community_reports, nodes, community_level),
        text_units=read_indexer_text_units(text_units),
        entities=_entities,
        relationships=read_indexer_relationships(relationships),
        covariates={"claims": _covariates},
        description_embedding_store=description_embedding_store,  # type: ignore
        response_type=response_type,
    )

    result: SearchResult = await search_engine.asearch(query=query)
    response = result.response
    context_data = _reformat_context_data(result.context_data)  # type: ignore
    return response, context_data


@validate_call(config={"arbitrary_types_allowed": True})
async def local_search_streaming(
    config: GraphRagConfig,
    nodes: pd.DataFrame,
    entities: pd.DataFrame,
    community_reports: pd.DataFrame,
    text_units: pd.DataFrame,
    relationships: pd.DataFrame,
    covariates: pd.DataFrame | None,
    community_level: int,
    response_type: str,
    query: str,
) -> AsyncGenerator:
    """Perform a local search and return the context data and response via a generator.

    Parameters
    ----------
    - config (GraphRagConfig): A graphrag configuration (from settings.yaml)
    - nodes (pd.DataFrame): A DataFrame containing the final nodes (from create_final_nodes.parquet)
    - entities (pd.DataFrame): A DataFrame containing the final entities (from create_final_entities.parquet)
    - community_reports (pd.DataFrame): A DataFrame containing the final community reports (from create_final_community_reports.parquet)
    - text_units (pd.DataFrame): A DataFrame containing the final text units (from create_final_text_units.parquet)
    - relationships (pd.DataFrame): A DataFrame containing the final relationships (from create_final_relationships.parquet)
    - covariates (pd.DataFrame): A DataFrame containing the final covariates (from create_final_covariates.parquet)
    - community_level (int): The community level to search at.
    - response_type (str): The response type to return.
    - query (str): The user query to search for.

    Returns
    -------
    TODO: Document the search response type and format.

    Raises
    ------
    TODO: Document any exceptions to expect.
    """
    config = _patch_vector_store(config, nodes, entities, community_level)

    # TODO: must update filepath of lancedb (if used) until the new config engine has been implemented
    # TODO: remove the type ignore annotations below once the new config engine has been refactored
    vector_store_type = config.embeddings.vector_store.get("type")  # type: ignore
    vector_store_args = config.embeddings.vector_store
    if vector_store_type == VectorStoreType.LanceDB:
        db_uri = config.embeddings.vector_store["db_uri"]  # type: ignore
        lancedb_dir = Path(config.root_dir).resolve() / db_uri
        vector_store_args["db_uri"] = str(lancedb_dir)  # type: ignore

    reporter.info(f"Vector Store Args: {redact(vector_store_args)}")  # type: ignore

    description_embedding_store = _get_embedding_store(
        config_args=vector_store_args,  # type: ignore
        container_suffix="entity-description",
    )

    _entities = read_indexer_entities(nodes, entities, community_level)
    _covariates = read_indexer_covariates(covariates) if covariates is not None else []

    search_engine = get_local_search_engine(
        config=config,
        reports=read_indexer_reports(community_reports, nodes, community_level),
        text_units=read_indexer_text_units(text_units),
        entities=_entities,
        relationships=read_indexer_relationships(relationships),
        covariates={"claims": _covariates},
        description_embedding_store=description_embedding_store,  # type: ignore
        response_type=response_type,
    )
    search_result = search_engine.astream_search(query=query)

    # when streaming results, a context data object is returned as the first result
    # and the query response in subsequent tokens
    context_data = None
    get_context_data = True
    async for stream_chunk in search_result:
        if get_context_data:
            context_data = _reformat_context_data(stream_chunk)  # type: ignore
            yield context_data
            get_context_data = False
        else:
            yield stream_chunk


@validate_call(config={"arbitrary_types_allowed": True})
async def drift_search(
    config: GraphRagConfig,
    nodes: pd.DataFrame,
    entities: pd.DataFrame,
    community_reports: pd.DataFrame,
    text_units: pd.DataFrame,
    relationships: pd.DataFrame,
    community_level: int,
    query: str,
) -> tuple[
    str | dict[str, Any] | list[dict[str, Any]],
    str | list[pd.DataFrame] | dict[str, pd.DataFrame],
]:
    """Perform a DRIFT search and return the context data and response.

    Parameters
    ----------
    - config (GraphRagConfig): A graphrag configuration (from settings.yaml)
    - nodes (pd.DataFrame): A DataFrame containing the final nodes (from create_final_nodes.parquet)
    - entities (pd.DataFrame): A DataFrame containing the final entities (from create_final_entities.parquet)
    - community_reports (pd.DataFrame): A DataFrame containing the final community reports (from create_final_community_reports.parquet)
    - text_units (pd.DataFrame): A DataFrame containing the final text units (from create_final_text_units.parquet)
    - relationships (pd.DataFrame): A DataFrame containing the final relationships (from create_final_relationships.parquet)
    - community_level (int): The community level to search at.
    - query (str): The user query to search for.

    Returns
    -------
    TODO: Document the search response type and format.

    Raises
    ------
    TODO: Document any exceptions to expect.
    """
    config = _patch_vector_store(
        config, nodes, entities, community_level, with_reports=community_reports
    )

    # TODO: update filepath of lancedb (if used) until the new config engine has been implemented
    # TODO: remove the type ignore annotations below once the new config engine has been refactored
    vector_store_type = config.embeddings.vector_store.get("type")  # type: ignore
    vector_store_args = config.embeddings.vector_store
    if vector_store_type == VectorStoreType.LanceDB:
        db_uri = config.embeddings.vector_store["db_uri"]  # type: ignore
        lancedb_dir = Path(config.root_dir).resolve() / db_uri
        vector_store_args["db_uri"] = str(lancedb_dir)  # type: ignore

    reporter.info(f"Vector Store Args: {redact(vector_store_args)}")  # type: ignore

    description_embedding_store = _get_embedding_store(
        config_args=vector_store_args,  # type: ignore
        container_suffix="entity-description",
    )

    full_content_embedding_store = _get_embedding_store(
        config_args=vector_store_args,  # type: ignore
        container_suffix="community-full_content",
    )

    _entities = read_indexer_entities(nodes, entities, community_level)
    _reports = read_indexer_reports(community_reports, nodes, community_level)
    read_indexer_report_embeddings(_reports, full_content_embedding_store)

    search_engine = get_drift_search_engine(
        config=config,
        reports=_reports,
        text_units=read_indexer_text_units(text_units),
        entities=_entities,
        relationships=read_indexer_relationships(relationships),
        description_embedding_store=description_embedding_store,  # type: ignore
    )

    result: SearchResult = await search_engine.asearch(query=query)
    response = result.response
    context_data = _reformat_context_data(result.context_data)  # type: ignore

    # TODO: Map/reduce the response to a single string with a comprehensive answer including all follow-ups
    # For the time being, return highest scoring response (position 0) and context data
    match response:
        case dict():
            return response["nodes"][0]["answer"], context_data  # type: ignore
        case str():
            return response, context_data
        case list():
            return response, context_data


def _patch_vector_store(
    config: GraphRagConfig,
    nodes: pd.DataFrame,
    entities: pd.DataFrame,
    community_level: int,
    with_reports: pd.DataFrame | None = None,
) -> GraphRagConfig:
    # TODO: remove the following patch that checks for a vector_store prior to v1 release
    # TODO: this is a backwards compatibility patch that injects the default vector_store settings into the config if it is not present
    # Only applicable in situations involving a local vector_store (lancedb). The general idea:
    # if vector_store not in config:
    #     1. assume user is running local if vector_store is not in config
    #     2. insert default vector_store in config
    #     3 .create lancedb vector_store instance
    #     4. upload vector embeddings from the input dataframes to the vector_store
    if not config.embeddings.vector_store:
        from graphrag.query.input.loaders.dfs import (
            store_entity_semantic_embeddings,
        )
        from graphrag.vector_stores.lancedb import LanceDBVectorStore

        config.embeddings.vector_store = {
            "type": "lancedb",
            "db_uri": f"{Path(config.storage.base_dir)}/lancedb",
            "container_name": "default",
            "overwrite": True,
        }
        description_embedding_store = LanceDBVectorStore(
            db_uri=config.embeddings.vector_store["db_uri"],
            collection_name="default-entity-description",
            overwrite=config.embeddings.vector_store["overwrite"],
        )
        description_embedding_store.connect(
            db_uri=config.embeddings.vector_store["db_uri"]
        )
        # dump embeddings from the entities list to the description_embedding_store
        _entities = read_indexer_entities(nodes, entities, community_level)
        store_entity_semantic_embeddings(
            entities=_entities, vectorstore=description_embedding_store
        )

        if with_reports is not None:
            from graphrag.query.input.loaders.dfs import (
                store_reports_semantic_embeddings,
            )
            from graphrag.vector_stores.lancedb import LanceDBVectorStore

            community_reports = with_reports
            collection_name = (
                config.embeddings.vector_store.get("container_name", "default")
                if config.embeddings.vector_store
                else "default"
            )
            # Store report embeddings
            _reports = read_indexer_reports(
                community_reports,
                nodes,
                community_level,
                content_embedding_col="full_content_embedding",
                config=config,
            )

            full_content_embedding_store = LanceDBVectorStore(
                db_uri=config.embeddings.vector_store["db_uri"],
                collection_name=f"{collection_name}-community-full_content",
                overwrite=config.embeddings.vector_store["overwrite"],
            )
            full_content_embedding_store.connect(
                db_uri=config.embeddings.vector_store["db_uri"]
            )
            # dump embeddings from the reports list to the full_content_embedding_store
            store_reports_semantic_embeddings(
                reports=_reports, vectorstore=full_content_embedding_store
            )

    return config


def _get_embedding_store(
    config_args: dict,
    container_suffix: str,
) -> BaseVectorStore:
    """Get the embedding description store."""
    vector_store_type = config_args["type"]
    collection_name = (
        f"{config_args.get('container_name', 'default')}-{container_suffix}"
    )
    embedding_store = VectorStoreFactory.get_vector_store(
        vector_store_type=vector_store_type,
        kwargs={**config_args, "collection_name": collection_name},
    )
    embedding_store.connect(**config_args)
    return embedding_store


def _reformat_context_data(context_data: dict) -> dict:
    """
    Reformats context_data for all query responses.

    Reformats a dictionary of dataframes into a dictionary of lists.
    One list entry for each record. Records are grouped by original
    dictionary keys.

    Note: depending on which query algorithm is used, the context_data may not
          contain the same information (keys). In this case, the default behavior will be to
          set these keys as empty lists to preserve a standard output format.
    """
    final_format = {
        "reports": [],
        "entities": [],
        "relationships": [],
        "claims": [],
        "sources": [],
    }
    for key in context_data:
        records = (
            context_data[key].to_dict(orient="records")
            if context_data[key] is not None and not isinstance(context_data[key], dict)
            else context_data[key]
        )
        if len(records) < 1:
            continue
        final_format[key] = records
    return final_format
