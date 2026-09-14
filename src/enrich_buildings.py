# src/enrich_buildings.py
import json
import os
from pathlib import Path
from src.cadastre_service import generate_land_ulpin, generate_cts_no, get_cadastral_division

def enrich_geojson_file(filepath: Path):
    if not filepath.exists():
        print(f"Skipping non-existent: {filepath}")
        return
    print(f"Enriching {filepath}...")
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    count = 0
    for feat in data.get("features", []):
        props = feat.get("properties", {})
        spatial_id = props.get("spatial_id", "")
        street = props.get("street", "")
        
        # Approximate centroid from geometry
        geom = feat.get("geometry", {})
        coords = []
        if geom.get("type") == "Polygon":
            coords = geom.get("coordinates", [[]])[0]
        elif geom.get("type") == "MultiPolygon":
            coords = geom.get("coordinates", [[[]]])[0][0]

        lon = sum(c[0] for c in coords) / max(len(coords), 1) if coords else 72.8270
        lat = sum(c[1] for c in coords) / max(len(coords), 1) if coords else 18.9280

        division = get_cadastral_division(street, lat, lon)
        props["cadastral_division"] = division
        props["land_ulpin"] = generate_land_ulpin(spatial_id, lat, lon)
        props["cts_no"] = generate_cts_no(spatial_id, division)
        count += 1

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print(f"[OK] Successfully enriched {count} features in {filepath}")

if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent.parent
    enrich_geojson_file(base_dir / "data" / "processed" / "buildings.geojson")
    enrich_geojson_file(base_dir.parent / "data" / "processed" / "buildings.geojson")
