import json
import pandas as pd
from dateutil import parser
import logging
import numpy as np
import xlsxwriter

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def read_geojson_file(filepath):
    with open(filepath, encoding='utf-8-sig') as f:
        return json.load(f)

def extract_properties(geojson):
    return [f['properties'] for f in geojson['features']]

def find_common_field(props1, props2):
    common = set(props1[0]).intersection(props2[0])
    return 'OBJECTID' if 'OBJECTID' in common else max(common, key=lambda f: len(set(str(p.get(f, '')) for p in props1) & set(str(p.get(f, '')) for p in props2)))

def convert_dates(df):
    date_like_cols = [col for col in df.columns if any(keyword in col.lower() for keyword in ['date', 'cutoff', 'time'])]

    for col in date_like_cols:
        if pd.api.types.is_numeric_dtype(df[col]):
            try:
                df[col] = pd.to_datetime(df[col], unit='ms', errors='coerce')
                overflow_mask = df[col].isna() & df[col].notna()
                df.loc[overflow_mask, col] = pd.NaT
            except (OverflowError, FloatingPointError):
                df[col] = pd.NaT
        elif df[col].dtype == object:
            try:
                df[col] = pd.to_datetime(df[col], errors='coerce', utc=True)
            except Exception:
                df[col] = pd.NaT

    return df

def geojson_to_df(geojson):
    return convert_dates(pd.DataFrame(extract_properties(geojson)))

def generate_grouped_comparison(df1, df2, key):
    df1['numeric_objectid'] = pd.to_numeric(df1[key], errors='coerce')
    df2['numeric_objectid'] = pd.to_numeric(df2[key], errors='coerce')

    merged = pd.merge(df1, df2, on=key, how='outer', suffixes=('_file1', '_file2'), indicator=True)

    records = []

    for _, row in merged.iterrows():
        numeric_id = row.get('numeric_objectid_file1') if pd.notnull(row.get('numeric_objectid_file1')) else row.get('numeric_objectid_file2')
        object_id = row[key]

        if row['_merge'] == 'left_only':
            records.append({'OBJECTID': object_id, 'NumericID': numeric_id, 'Status': 'Removed', 'Column': '', 'Previous': '', 'Modified': ''})

        elif row['_merge'] == 'right_only':
            records.append({'OBJECTID': object_id, 'NumericID': numeric_id, 'Status': 'Added', 'Column': '', 'Previous': '', 'Modified': ''})

        else:
            modified = False
            modifications = []
            for col in df1.columns:
                if col not in [key, 'numeric_objectid']:
                    val1 = row.get(col + '_file1')
                    val2 = row.get(col + '_file2')
                    if (pd.isnull(val1) and pd.isnull(val2)) or (val1 == val2):
                        continue
                    modified = True
                    modifications.append({'Column': col, 'Previous': val1, 'Modified': val2})

            if modified:
                for idx, mod in enumerate(modifications):
                    records.append({
                        'OBJECTID': object_id if idx == 0 else '',
                        'NumericID': numeric_id if idx == 0 else '',
                        'Status': 'Modified' if idx == 0 else '',
                        **mod
                    })
            else:
                records.append({'OBJECTID': object_id, 'NumericID': numeric_id, 'Status': 'None', 'Column': '', 'Previous': '', 'Modified': ''})

    grouped_df = pd.DataFrame(records)
    return grouped_df

def generate_summary_report(grouped_df):
    summary = grouped_df.groupby(['OBJECTID', 'Status']).size().reset_index(name='Count')
    summary.to_csv("summary_report.csv", index=False, encoding="utf-8-sig")

def generate_excel_with_formatting(grouped_df, filename="grouped_differences_report.xlsx"):
    with pd.ExcelWriter(filename, engine='xlsxwriter') as writer:
        grouped_df.to_excel(writer, index=False, sheet_name="Differences")
        workbook = writer.book
        worksheet = writer.sheets["Differences"]

        format_header = workbook.add_format({'bold': True, 'bg_color': '#D9E1F2', 'border': 1})
        for col_num, value in enumerate(grouped_df.columns.values):
            worksheet.write(0, col_num, value, format_header)
            worksheet.set_column(col_num, col_num, 20)

        format_added = workbook.add_format({'bg_color': '#C6EFCE', 'border': 1})
        format_removed = workbook.add_format({'bg_color': '#F4CCCC', 'border': 1})
        format_modified = workbook.add_format({'bg_color': '#FFEB9C', 'border': 1})

        current_objectid = None
        for row_num, row in grouped_df.iterrows():
            fmt = None
            if row['Status'] == 'Added':
                fmt = format_added
            elif row['Status'] == 'Removed':
                fmt = format_removed
            elif row['Status'] == 'Modified':
                fmt = format_modified

            if row['OBJECTID'] != '' and row['OBJECTID'] != current_objectid:
                current_objectid = row['OBJECTID']
                worksheet.set_row(row_num + 1, None, fmt, {'level': 1, 'hidden': False})
            else:
                worksheet.set_row(row_num + 1, None, fmt)

def validate_objectid_consistency(df1, df2, key):
    compare_cols = [col for col in df1.columns if col not in [key, 'numeric_objectid']]

    merged = pd.merge(df1[compare_cols + [key]], df2[compare_cols + [key]], on=compare_cols, how='inner', suffixes=('_file1', '_file2'))

    conflicts = merged[merged[f"{key}_file1"] != merged[f"{key}_file2"]]

    if not conflicts.empty:
        logging.warning("Conflicting OBJECTIDs detected for identical rows.")
        conflicts.to_csv("conflicting_objectids.csv", index=False, encoding="utf-8-sig")
        logging.info("Saved: conflicting_objectids.csv")

def main():
    file1_path = input("Enter path to first GeoJSON file: ").strip()
    file2_path = input("Enter path to second GeoJSON file: ").strip()

    g1 = read_geojson_file(file1_path)
    g2 = read_geojson_file(file2_path)

    df1, df2 = geojson_to_df(g1), geojson_to_df(g2)
    common_key = find_common_field(extract_properties(g1), extract_properties(g2))

    validate_objectid_consistency(df1, df2, common_key)

    grouped_df = generate_grouped_comparison(df1, df2, common_key)

    grouped_df.to_csv("grouped_differences_report.csv", index=False, encoding="utf-8-sig")
    generate_summary_report(grouped_df)
    generate_excel_with_formatting(grouped_df)

    print("\nReports generated:\n - grouped_differences_report.csv\n - summary_report.csv\n - grouped_differences_report.xlsx")

if __name__ == "__main__":
    main()

