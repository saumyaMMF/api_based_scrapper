import pandas as pd
import json
from ast import literal_eval

# =========================
# CONFIG
# =========================
CSV_PATH = r"C:\Users\a\Downloads\jan20-jan27 Valleymeade.csv"
OUTPUT_JSON_PATH = "jan20-jan27_valley.json"
CANONICAL_BRAND = "Rhize Cannabis Company"

# =========================
# LOAD CSV
# =========================
df = pd.read_csv(CSV_PATH)

# =========================
# GENERATE JSON
# =========================
output = {}

for date, group in df.groupby("date"):
    products = []

    for _, row in group.iterrows():
        unit = row["Unit"]
        qty = int(row["Today's_Quantity_Total"])

        # # ---- Category rule ----
        # category = (
        #     "Concentrate"
        #     if str(row["Category"]).strip().lower() == "rosin"
        #     else row["Category"]
        # )

        # ---- Internal Product Type rule ----
        # internal_type = (
        #     "Rosin Jar"
        #     if str(row["Type"]).strip().lower() == "jar"
        #     else row["Type"]
        # )

        discount_price = (
            literal_eval(row["Discount_Price_Data"])
            if pd.notna(row["Discount_Price_Data"])
            else {unit: row["Price"]}
        )

        product = {
            "Product name": row["Product_Name"],
            "Category": row["Category"], # category,
            "Brand": CANONICAL_BRAND,
            "Price": {
                unit: row["Price"]
            },
            "Discount Price": discount_price,
            "THC": row["THC"],
            "Quantity Available": qty,
            "Quantity Per Option": {
                unit: qty
            },
            "Internal Product Name": row["Product_Name"],
            "Internal Product Type": row["Type"], # internal_type,
            "SKU": row["SKU"],
            "Days on Shelf": int(row["Days"])
        }

        products.append(product)

    output[str(date)] = products

# =========================
# WRITE JSON
# =========================
with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2)

print(f"✅ JSON generated at: {OUTPUT_JSON_PATH}")
