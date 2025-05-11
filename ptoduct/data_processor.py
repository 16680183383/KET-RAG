import pandas as pd
from typing import Tuple

def create_community_hierarchy(entity_df: pd.DataFrame) -> pd.DataFrame:
    """Create community hierarchy from entity DataFrame.
    
    Args:
        entity_df: DataFrame containing entity information
        
    Returns:
        DataFrame with community hierarchy information
    """
    # Create a copy of the entity DataFrame
    hierarchy_df = entity_df.copy()
    
    # Use top_level_node_id as community identifier if available
    if 'top_level_node_id' in hierarchy_df.columns:
        hierarchy_df['community'] = hierarchy_df['top_level_node_id'].fillna(hierarchy_df['id']).astype(str)
    else:
        hierarchy_df['community'] = hierarchy_df['id'].astype(str)
    
    # Create sub_community column
    hierarchy_df['sub_community'] = hierarchy_df['community']
    
    # Group by community and aggregate sub_communities
    community_hierarchy = (
        hierarchy_df.groupby('community')
        .agg({'sub_community': list})
        .reset_index()
        .rename(columns={'community': 'id', 'sub_community': 'sub_community_ids'})
    )
    
    return community_hierarchy

def prepare_data(input_dir: str) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Prepare data for global search.
    
    Args:
        input_dir: Directory containing the parquet files
        
    Returns:
        Tuple of (community_df, entity_df, report_df, entity_embedding_df)
    """
    # Load data
    community_df = pd.read_parquet(f"{input_dir}/create_final_communities.parquet")
    entity_df = pd.read_parquet(f"{input_dir}/create_final_nodes.parquet")
    report_df = pd.read_parquet(f"{input_dir}/create_final_community_reports.parquet")
    entity_embedding_df = pd.read_parquet(f"{input_dir}/create_final_entities.parquet")
    
    # Ensure all required columns exist and are properly formatted
    # For community_df
    community_df['id'] = community_df['id'].astype(str)
    community_df['level'] = community_df['level'].astype(str)
    community_df['community'] = community_df['id']  # Use id as community
    community_df['sub_community'] = community_df['id']  # Use id as sub_community
    
    # For entity_df
    entity_df['id'] = entity_df['id'].astype(str)
    entity_df['level'] = entity_df['level'].fillna('0').astype(str)
    if 'community' not in entity_df.columns:
        entity_df['community'] = entity_df['id']  # Use id as community
    entity_df['sub_community'] = entity_df['id']  # Use id as sub_community
    
    # For report_df
    report_df['id'] = report_df['id'].astype(str)
    report_df['level'] = report_df['level'].astype(str)
    if 'community' not in report_df.columns:
        report_df['community'] = report_df['id']  # Use id as community
    
    # Print data shapes and column information for verification
    print("\nData shapes:")
    print(f"Community DataFrame: {community_df.shape}")
    print(f"Entity DataFrame: {entity_df.shape}")
    print(f"Report DataFrame: {report_df.shape}")
    print(f"Entity Embedding DataFrame: {entity_embedding_df.shape}")
    
    print("\nColumn information:")
    print("Community DataFrame columns:", community_df.columns.tolist())
    print("Entity DataFrame columns:", entity_df.columns.tolist())
    print("Report DataFrame columns:", report_df.columns.tolist())
    
    print("\nSample data:")
    print("\nCommunity DataFrame sample:")
    print(community_df[['id', 'community', 'sub_community', 'level']].head())
    print("\nEntity DataFrame sample:")
    print(entity_df[['id', 'community', 'sub_community', 'level']].head())
    print("\nReport DataFrame sample:")
    print(report_df[['id', 'community', 'level']].head())
    
    return community_df, entity_df, report_df, entity_embedding_df 