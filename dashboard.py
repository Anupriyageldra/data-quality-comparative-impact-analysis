import streamlit as st
import pandas as pd

@st.cache_data(show_spinner=False)
def load_report():
    return pd.read_csv("grouped_differences_report.csv")

@st.cache_data(show_spinner=False)
def load_summary():
    return pd.read_csv("summary_report.csv")

def main():
    st.set_page_config(layout="wide", page_title="GeoJSON Differences Dashboard")
    st.title("📊 GeoJSON Comparison Dashboard")

    st.sidebar.header("🔎 Filters")

    grouped_df = load_report()
    summary_df = load_summary()

    with st.expander("🔔 Summary of Changes", expanded=True):
        st.dataframe(summary_df, use_container_width=True, height=250)

    object_ids = grouped_df["OBJECTID"].dropna().unique().tolist()
    selected_ids = st.sidebar.multiselect("Filter by OBJECTID", object_ids, default=object_ids[:10])

    filtered_df = grouped_df[grouped_df["OBJECTID"].isin(selected_ids)] if selected_ids else grouped_df

    status_filter = st.sidebar.multiselect("Filter by Status", filtered_df["Status"].dropna().unique(), default=filtered_df["Status"].dropna().unique())

    filtered_df = filtered_df[filtered_df["Status"].isin(status_filter)]

    st.markdown("""
    <style>
        .stDataFrame {border-radius: 8px; overflow: hidden; border: 1px solid #ccc;}
    </style>
    """, unsafe_allow_html=True)

    st.subheader("📂 Detailed Differences")
    st.dataframe(filtered_df, use_container_width=True, height=600)

    col1, col2 = st.columns(2)
    with col1:
        st.download_button("⬇ Download Full CSV", data=grouped_df.to_csv(index=False).encode("utf-8-sig"), file_name="grouped_differences_report.csv")
    with col2:
        st.download_button("⬇ Download Summary CSV", data=summary_df.to_csv(index=False).encode("utf-8-sig"), file_name="summary_report.csv")

if __name__ == "__main__":
    main()