# src/fetch_data.py
import os
import requests
import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon, LineString

# Full South Mumbai Bounding Box: Colaba -> Worli/Byculla
SOUTH = 18.8900
WEST  = 72.8000
NORTH = 19.0050
EAST  = 72.8550

OVERPASS_MIRRORS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.osm.ch/api/interpreter"
]

def query_overpass(ql_query):
    for endpoint in OVERPASS_MIRRORS:
        try:
            print(f"Querying mirror: {endpoint} ...")
            response = requests.post(
                endpoint,
                data={'data': ql_query},
                timeout=120,
                headers={'User-Agent': 'MumbaiFullTwin/1.0'}
            )
            if response.status_code == 200:
                return response.json()
        except Exception as err:
            print(f"Mirror failed ({err}). Trying next endpoint...")
    raise ConnectionError("Overpass mirrors unreachable. Check internet connection.")

def fetch_south_mumbai_buildings():
    print("[1/3] Downloading Full South Mumbai building footprints...")
    ql_query = f"""
    [out:json][timeout:180][maxsize:1073741824];
    (
      way["building"]({SOUTH},{WEST},{NORTH},{EAST});
      relation["building"]({SOUTH},{WEST},{NORTH},{EAST});
    );
    out body;
    >;
    out skel qt;
    """
    data = query_overpass(ql_query)
    nodes = {elem['id']: (elem['lon'], elem['lat']) for elem in data.get('elements', []) if elem['type'] == 'node'}
    
    features = []
    for elem in data.get('elements', []):
        if elem.get('type') == 'way' and 'nodes' in elem:
            coords = [nodes[n] for n in elem['nodes'] if n in nodes]
            if len(coords) >= 4:
                try:
                    poly = Polygon(coords)
                    if poly.is_valid and not poly.is_empty:
                        tags = elem.get('tags', {})
                        features.append({
                            'geometry': poly,
                            'name': tags.get('name', 'Unlabeled Building'),
                            'building:levels': tags.get('building:levels', None),
                            'height': tags.get('height', None),
                            'addr:street': tags.get('addr:street', None)
                        })
                except Exception:
                    continue

    gdf = gpd.GeoDataFrame(features, crs="EPSG:4326")
    os.makedirs("data/raw", exist_ok=True)
    gdf.to_file("data/raw/buildings.geojson", driver="GeoJSON")
    print(f"✓ Saved {len(gdf)} full South Mumbai buildings to data/raw/buildings.geojson")
    return gdf

def fetch_south_mumbai_infrastructure():
    print("[2/3] Downloading Road and Rail Networks...")
    ql_query = f"""
    [out:json][timeout:120];
    (
      way["highway"]({SOUTH},{WEST},{NORTH},{EAST});
      way["railway"]({SOUTH},{WEST},{NORTH},{EAST});
    );
    out body;
    >;
    out skel qt;
    """
    data = query_overpass(ql_query)
    nodes = {elem['id']: (elem['lon'], elem['lat']) for elem in data.get('elements', []) if elem['type'] == 'node'}
    
    features = []
    for elem in data.get('elements', []):
        if elem.get('type') == 'way' and 'nodes' in elem:
            coords = [nodes[n] for n in elem['nodes'] if n in nodes]
            if len(coords) >= 2:
                try:
                    tags = elem.get('tags', {})
                    features.append({
                        'geometry': LineString(coords),
                        'name': tags.get('name', 'Road/Track'),
                        'type': tags.get('highway', tags.get('railway', 'transport')),
                        'lanes': tags.get('lanes', '2')
                    })
                except Exception:
                    continue

    gdf = gpd.GeoDataFrame(features, crs="EPSG:4326")
    gdf.to_file("data/raw/infrastructure.geojson", driver="GeoJSON")
    print(f"✓ Saved {len(gdf)} road/rail network lines to data/raw/infrastructure.geojson")
    return gdf

if __name__ == "__main__":
    fetch_south_mumbai_buildings()
    fetch_south_mumbai_infrastructure()