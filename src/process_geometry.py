import os
import geopandas as gpd
import numpy as np

def process_all():
    print("[3/3] Computing real dimensions (Length, Breadth, Floor Heights in meters)...")
    gdf = gpd.read_file("data/raw/buildings.geojson")
    
    # Reproject GPS degrees (EPSG:4326) to UTM Zone 43N (EPSG:32643) for exact meter calculations
    gdf = gdf.to_crs(epsg=32643)
    
    gdf['footprint_area_sqm'] = gdf.geometry.area
    
    # Calculate length and breadth using the minimum bounding rectangle
    def calc_dims(geom):
        rect = geom.minimum_rotated_rectangle
        x, y = rect.exterior.coords.xy
        edge_lengths = [np.hypot(x[i+1]-x[i], y[i+1]-y[i]) for i in range(3)]
        return max(edge_lengths), min(edge_lengths)

    dims = gdf.geometry.apply(calc_dims)
    gdf['length_m'] = [round(d[0], 2) for d in dims]
    gdf['breadth_m'] = [round(d[1], 2) for d in dims]

    if 'building:levels' not in gdf.columns:
        gdf['building:levels'] = np.nan
        
    gdf['floors'] = gdf['building:levels'].fillna(5).astype(float)
    
    if 'height' in gdf.columns:
        gdf['height_m'] = gdf['height'].astype(str).str.extract(r'(\d+\.?\d*)')[0].astype(float)
        gdf['height_m'] = gdf['height_m'].fillna(gdf['floors'] * 3.2)
    else:
        gdf['height_m'] = gdf['floors'] * 3.2

    os.makedirs("data/processed", exist_ok=True)
    output_path = "data/processed/buildings_processed.geojson"
    gdf.to_file(output_path, driver="GeoJSON")
    print(f"✓ Processed geometry for {len(gdf)} structures saved to {output_path}")
    return gdf

if __name__ == "__main__":
    process_all()