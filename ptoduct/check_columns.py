import pandas as pd
import numpy as np
pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)
pd.set_option('display.max_colwidth', 30)

def print_separator(title):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)

def analyze_dataframe(name, df):
    print_separator(f"{name} Analysis")
    print("Basic Information:")
    print(f"Total records: {len(df)}")
    print(f"Columns: {df.columns.tolist()}")
    
    print("\nFirst 3 rows of key columns:")
    key_columns = ['id', 'title', 'level', 'community']
    available_columns = [col for col in key_columns if col in df.columns]
    print(df[available_columns].head(3))
    
    print("\nData types:")
    print(df.dtypes)
    
    if 'community' in df.columns:
        print("\nCommunity column analysis:")
        print(f"Unique values: {df['community'].nunique()}")
        print(f"Null values: {df['community'].isnull().sum()}")
        print("\nValue counts:")
        print(df['community'].value_counts().head())

# 读取数据文件
print_separator("Loading Data Files")
df1 = pd.read_parquet('output/create_final_communities.parquet')
df1['community'] = df1['id']  # 添加community列，使用id列的值
print("Communities file loaded")

df2 = pd.read_parquet('output/create_final_nodes.parquet')
print("Nodes file loaded")

df3 = pd.read_parquet('output/create_final_community_reports.parquet')
print("Reports file loaded")

# 分析每个DataFrame
analyze_dataframe("Communities", df1)
analyze_dataframe("Nodes", df2)
analyze_dataframe("Reports", df3)

# 分析关系
print_separator("Relationship Analysis")
print("Community IDs in each file:")
print(f"Communities: {sorted(df1['community'].unique())}")
print(f"Nodes: {sorted(df2['community'].unique())}")
print(f"Reports: {sorted(df3['community'].unique())}")

print("\nCross-reference analysis:")
common_communities = set(df1['community'].unique()) & set(df2['community'].unique()) & set(df3['community'].unique())
print(f"Communities present in all files: {sorted(common_communities)}")

missing_in_communities = set(df2['community'].unique()) | set(df3['community'].unique()) - set(df1['community'].unique())
print(f"Communities missing from communities file: {sorted(missing_in_communities)}")

# 检查level分布
print("\nLevel distribution:")
print("Communities:")
print(df1['level'].value_counts().sort_index())
print("\nNodes:")
print(df2['level'].value_counts().sort_index())
print("\nReports:")
print(df3['level'].value_counts().sort_index()) 