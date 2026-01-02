import streamlit as st
import psycopg2
import pandas as pd
import os
from dotenv import load_dotenv
from pathlib import Path
import plotly.express as px
import plotly.graph_objects as go

# Load environment variables from .env file - try multiple locations
env_paths = ['/home/user/.env', '.env']
for env_path in env_paths:
    if Path(env_path).exists():
        load_dotenv(env_path)
        break
else:
    load_dotenv()  # Fallback to default behavior

st.set_page_config(page_title="Property Agent Dashboard", layout="wide")
st.title("🏡 Property & Agent Data Dashboard")

# Read credentials from environment variables
db_host = os.getenv("DB_HOST")
db_port = os.getenv("DB_PORT", "5432")
db_name = os.getenv("DB_NAME")
db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")
db_ssl_mode = os.getenv("DB_SSL_MODE", "require")  # SSL mode for cloud databases

# Debug: Show connection info (hidden in sidebar)
with st.sidebar.expander("Connection Info", expanded=False):
    st.write(f"Host: {db_host}")
    st.write(f"Port: {db_port}")
    st.write(f"Database: {db_name}")
    st.write(f"User: {db_user}")
    st.write(f"SSL Mode: {db_ssl_mode}")

if not all([db_host, db_name, db_user, db_password]):
    st.error("❌ Missing database credentials! Please check your .env file.")
    st.info("Required variables: DB_HOST, DB_NAME, DB_USER, DB_PASSWORD")
    st.stop()

# Get table names from environment
db_table_agent = os.getenv("DB_TABLE_AGENT")
db_table_property = os.getenv("DB_TABLE_PROPERTY")

if not all([db_table_agent, db_table_property]):
    st.error("❌ Missing table names! Please set DB_TABLE_AGENT and DB_TABLE_PROPERTY in your .env file.")
    st.stop()

@st.cache_data(ttl=300)  # Cache data for 5 minutes
def fetch_data(table_name, limit=1000):
    """Fetch data from database with a fresh connection. Connection is closed after fetch."""
    conn = None
    try:
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            database=db_name,
            user=db_user,
            password=db_password,
            sslmode=db_ssl_mode,
            connect_timeout=10
        )
        # Use double quotes for PostgreSQL case-sensitive table names
        df = pd.read_sql(f'SELECT * FROM "{table_name}" LIMIT {limit}', conn)
        return df
    except Exception as e:
        st.error(f"Error fetching {table_name}: {str(e)}")
        return pd.DataFrame()
    finally:
        if conn:
            conn.close()

try:
    # Fetch data for Agent and Property tables
    agent_df = fetch_data(db_table_agent)
    property_df = fetch_data(db_table_property)

    if agent_df.empty and property_df.empty:
        st.warning("⚠️ No data returned from either Agent or Property tables.")
        st.stop()
    elif agent_df.empty:
        st.warning("⚠️ No data returned from Agent table.")
    elif property_df.empty:
        st.warning("⚠️ No data returned from Property table.")

    st.success("✅ Connected to database and fetched data.")

    # --- Data Preprocessing and Merging ---
    if not agent_df.empty and not property_df.empty:
        # Select relevant columns from agent_df and rename for clarity before merge
        # This ensures 'companyName' from agent_df becomes 'agent_companyName' in merged_df
        agent_cols_to_merge = ['id', 'companyName', 'email', 'phoneNumber']
        # Filter agent_df to only include these columns to avoid suffixing other columns unnecessarily
        agent_df_selected = agent_df[agent_cols_to_merge].rename(columns={
            'id': 'agentId', # This is the merge key
            'companyName': 'agent_companyName', # Explicitly rename to avoid collision and be clear
            'email': 'agent_email',
            'phoneNumber': 'agent_phoneNumber'
        })

        # Merge dataframes on agentId (from Property) and id (from Agent, renamed to agentId)
        # Use a left merge to keep all properties, even if they don't have an agent assigned
        merged_df = pd.merge(property_df, agent_df_selected, on='agentId', how='left')

        # Fill NaN values for agent-related columns after merge
        merged_df['agent_companyName'] = merged_df['agent_companyName'].fillna('No Agent Assigned')
        merged_df['agent_email'] = merged_df['agent_email'].fillna('N/A')
        merged_df['agent_phoneNumber'] = merged_df['agent_phoneNumber'].fillna('N/A')

        st.subheader("Combined Property and Agent Data")
        st.dataframe(merged_df.head(), use_container_width=True)

        # --- Streamlit Sidebar Filters ---
        st.sidebar.header("Filters")

        # Property Type Filter
        property_types = ['All'] + list(merged_df['propertyType'].unique()) if 'propertyType' in merged_df.columns else ['All']
        selected_property_type = st.sidebar.selectbox("Select Property Type", property_types)

        # City Filter
        cities = ['All'] + list(merged_df['city'].unique()) if 'city' in merged_df.columns else ['All']
        selected_city = st.sidebar.selectbox("Select City", cities)

        # Agent Company Filter
        agent_companies = ['All'] + list(merged_df['agent_companyName'].unique()) if 'agent_companyName' in merged_df.columns else ['All']
        selected_agent_company = st.sidebar.selectbox("Select Agent Company", agent_companies)

        # Apply filters
        filtered_df = merged_df.copy()
        if selected_property_type != 'All':
            filtered_df = filtered_df[filtered_df['propertyType'] == selected_property_type]
        if selected_city != 'All':
            filtered_df = filtered_df[filtered_df['city'] == selected_city]
        if selected_agent_company != 'All':
            filtered_df = filtered_df[filtered_df['agent_companyName'] == selected_agent_company]

        st.subheader(f"Filtered Data ({len(filtered_df)} rows)")
        st.dataframe(filtered_df, use_container_width=True)

        # --- Streamlit Tabs for Visualizations ---
        tab1, tab2, tab3, tab4 = st.tabs(["Property Overview", "Agent Performance", "Location Analysis", "Raw Data"]) # Added a Raw Data tab

        with tab1:
            st.header("Property Overview")

            if not filtered_df.empty:
                # 1. Property Count by Type
                st.subheader("Property Count by Type")
                if 'propertyType' in filtered_df.columns:
                    property_type_counts = filtered_df['propertyType'].value_counts().reset_index()
                    property_type_counts.columns = ['Property Type', 'Count']
                    fig_type = px.bar(property_type_counts, x='Property Type', y='Count', title='Number of Properties by Type')
                    st.plotly_chart(fig_type, use_container_width=True)
                else:
                    st.info("No 'propertyType' column found for this visualization.")

                # 2. Average Price by Property Type
                st.subheader("Average Price by Property Type")
                if 'propertyType' in filtered_df.columns and 'price' in filtered_df.columns:
                    avg_price_by_type = filtered_df.groupby('propertyType')['price'].mean().reset_index()
                    avg_price_by_type.columns = ['Property Type', 'Average Price']
                    fig_avg_price = px.bar(avg_price_by_type, x='Property Type', y='Average Price', title='Average Property Price by Type', color='Property Type')
                    st.plotly_chart(fig_avg_price, use_container_width=True)
                else:
                    st.info("Missing 'propertyType' or 'price' column for this visualization.")

                # 3. Price Distribution
                st.subheader("Property Price Distribution")
                if 'price' in filtered_df.columns:
                    fig_price_dist = px.histogram(filtered_df, x='price', nbins=20, title='Distribution of Property Prices', marginal='box')
                    st.plotly_chart(fig_price_dist, use_container_width=True)
                else:
                    st.info("No 'price' column found for this visualization.")

                # 4. Area vs Price Scatter Plot
                st.subheader("Property Area vs. Price")
                if 'area' in filtered_df.columns and 'price' in filtered_df.columns:
                    fig_area_price = px.scatter(filtered_df, x='area', y='price', color='propertyType', hover_data=['title', 'city'], title='Property Area vs. Price')
                    st.plotly_chart(fig_area_price, use_container_width=True)
                else:
                    st.info("Missing 'area' or 'price' column for this visualization.")
            else:
                st.info("No data to display for Property Overview after filters.")

        with tab2:
            st.header("Agent Performance")

            if not filtered_df.empty:
                # 1. Number of Properties per Agent Company
                st.subheader("Number of Properties per Agent Company")
                if 'agent_companyName' in filtered_df.columns:
                    agent_property_counts = filtered_df['agent_companyName'].value_counts().reset_index()
                    agent_property_counts.columns = ['Agent Company', 'Number of Properties']
                    fig_agent_props = px.bar(agent_property_counts, x='Agent Company', y='Number of Properties', title='Properties Listed by Agent Company')
                    st.plotly_chart(fig_agent_props, use_container_width=True)
                else:
                    st.info("No 'agent_companyName' column found for this visualization.")

                # 2. Total Value of Properties per Agent Company
                st.subheader("Total Value of Properties per Agent Company")
                if 'agent_companyName' in filtered_df.columns and 'price' in filtered_df.columns:
                    agent_total_value = filtered_df.groupby('agent_companyName')['price'].sum().reset_index()
                    agent_total_value.columns = ['Agent Company', 'Total Property Value']
                    fig_agent_value = px.pie(agent_total_value, values='Total Property Value', names='Agent Company', title='Total Value of Properties by Agent Company')
                    st.plotly_chart(fig_agent_value, use_container_width=True)
                else:
                    st.info("Missing 'agent_companyName' or 'price' column for this visualization.")

                # 3. Average Property Price per Agent Company
                st.subheader("Average Property Price per Agent Company")
                if 'agent_companyName' in filtered_df.columns and 'price' in filtered_df.columns:
                    agent_avg_price = filtered_df.groupby('agent_companyName')['price'].mean().reset_index()
                    agent_avg_price.columns = ['Agent Company', 'Average Property Price']
                    fig_agent_avg_price = px.bar(agent_avg_price, x='Agent Company', y='Average Property Price', title='Average Property Price by Agent Company', color='Agent Company')
                    st.plotly_chart(fig_agent_avg_price, use_container_width=True)
                else:
                    st.info("Missing 'agent_companyName' or 'price' column for this visualization.")
            else:
                st.info("No data to display for Agent Performance after filters.")

        with tab3:
            st.header("Location Analysis")

            if not filtered_df.empty:
                # 1. Properties by City
                st.subheader("Properties by City")
                if 'city' in filtered_df.columns:
                    city_counts = filtered_df['city'].value_counts().reset_index()
                    city_counts.columns = ['City', 'Count']
                    fig_city = px.bar(city_counts, x='City', y='Count', title='Number of Properties by City')
                    st.plotly_chart(fig_city, use_container_width=True)
                else:
                    st.info("No 'city' column found for this visualization.")

                # 2. Average Price by City
                st.subheader("Average Price by City")
                if 'city' in filtered_df.columns and 'price' in filtered_df.columns:
                    avg_price_by_city = filtered_df.groupby('city')['price'].mean().reset_index()
                    avg_price_by_city.columns = ['City', 'Average Price']
                    fig_avg_price_city = px.bar(avg_price_by_city, x='City', y='Average Price', title='Average Property Price by City', color='City')
                    st.plotly_chart(fig_avg_price_city, use_container_width=True)
                else:
                    st.info("Missing 'city' or 'price' column for this visualization.")

                # 3. Property Locations (if x and y coordinates are available)
                st.subheader("Property Locations on Map")
                if 'x' in filtered_df.columns and 'y' in filtered_df.columns and not filtered_df[['x', 'y']].isnull().all().all():
                    fig_map = px.scatter_mapbox(filtered_df, lat='y', lon='x', hover_name='title', hover_data=['address', 'city', 'price', 'propertyType'],
                                                color='propertyType', zoom=8, height=500, title='Property Locations')
                    fig_map.update_layout(mapbox_style="open-street-map")
                    st.plotly_chart(fig_map, use_container_width=True)
                else:
                    st.info("Missing 'x' or 'y' coordinates for map visualization or all coordinates are null.")
            else:
                st.info("No data to display for Location Analysis after filters.")

        with tab4:
            st.header("Raw Data Tables")
            st.subheader("Agent Data")
            st.dataframe(agent_df, use_container_width=True)

            st.subheader("Property Data")
            st.dataframe(property_df, use_container_width=True)

            st.subheader("Merged Data")
            st.dataframe(merged_df, use_container_width=True)

    elif not agent_df.empty:
        st.subheader("Agent Data")
        st.dataframe(agent_df, use_container_width=True)
        st.info("Property data is empty, cannot perform merge or property-related visualizations.")
    elif not property_df.empty:
        st.subheader("Property Data")
        st.dataframe(property_df, use_container_width=True)
        st.info("Agent data is empty, cannot perform merge or agent-related visualizations.")

except Exception as e:
    st.error(f"❌ An unexpected error occurred: {str(e)}")
    if "SSL" in str(e):
        st.info("💡 Try setting DB_SSL_MODE=disable in your .env file if the database doesn't support SSL")