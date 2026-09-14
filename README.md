# 🏢 3D Property Mapping System
### South Mumbai 3D Urban Digital Twin & Vertical ULPIN Cadastre

An interactive, high-fidelity **3D GIS Urban Digital Twin & Vertical Property Mapping Platform** built for cadastral exploration, vertical property registration, and architectural inspection.

Built with **FastAPI, React 18, Three.js, MapLibre GL JS, and GeoJSON**, this platform transitions from city-wide GIS geospatial layers down to individual building storeys, apartments, and their unique **Bhu-Aadhaar 3D ULPINs**.

---

## 🌟 Key Features

### 🏛️ Realistic Architectural Digital Twin (Not Simple Extruded Blocks)
- **Chamfered Slabs**: Reinforced concrete floor slabs with an architectural cantilever lip (0.36m thickness) cleanly separating every floor level.
- **Façade Articulation**: Exterior solid walls and spandrel panels with realistic PBR stone/concrete roughness and ambient occlusion.
- **Punched Recessed Windows**: Window apertures recessed 0.15m inward from the outer façade, featuring dark aluminum frames, cross-mullions, and high-transmission PBR physical glass (`THREE.MeshPhysicalMaterial`) with realistic reflections and clearcoat highlights.
- **Cantilevered Balconies & Railings**: Exterior projecting balconies with concrete deck slabs, tempered glass railing panels, and dark anodized aluminum handrails.
- **Ground Floor Entrance Lobby**: Grand entrance portico canopy with cyan accent edge line, structural steel columns, and double glass entrance doors.
- **Rooftop Architectural Crown**: Safety parapet wall with coping stone, central elevator overrun penthouse, rooftop HVAC chillers, water tanks, and telecommunication spire with an active beacon light.

### 📐 Structural Hierarchy (Building → Wing → Floor → Flat → ULPIN)
- **Building Level**: Base Land Parcel ULPIN (14-digit Indian Bhu-Aadhaar code: `2701XXXXXXXXXX`), Cadastral Survey Number (CTS No), revenue division, storeys count, and footprint area.
- **Wing Level**: Architectural division into towers/wings (`Wing A - East Wing`, `Wing B - West Wing`).
- **Floor Level**: Vertical slices from Ground Floor up to Terrace & Penthouse with exact metric elevation above MSL datum.
- **Flat / Unit Level**: Individual flats (`Flat 401`, `Flat 402`) with unit types (`2BHK Luxury Sea-Facing Flat`, `Commercial Office Suite`, `Sky Villa Penthouse`), RERA carpet area ($m^2$ and sq.ft), gross built-up area, and undivided share of land (`UDS %`).
- **3D Vertical ULPIN**: Unique Bhu-Aadhaar vertical cadastral identifier for every unit (e.g. `27014543271680-WA-FL04-U401`).

### 💥 Interactive Floor Exploding, Isolation & Flat Selection
- **Explode / Stack Floors**: Interactive slider (0% to 100%) and quick presets that smoothly animate vertical floor separation.
- **Floor Isolation**: Clicking any floor isolates that level, rendering surrounding floors in translucent ghosted glass so internal layouts can be studied.
- **Flat Selection with Ghosted Context**: Clicking any flat highlights it with an electric cyan/amber emissive glow and accent outline, while surrounding flats and floors transition into an architectural translucent x-ray mode (18% opacity with edge lines) so spatial orientation is preserved.
- **Smooth Camera Transitions**: Cubic-eased camera tweens smoothly glide when focusing on a building, floor, or flat.
- **View Presets**: Quick buttons for **3D Isometric**, **Front Elevation**, and **Top-Down Floor Plan** views.

### 🗺️ GIS Base Map & Subterranean Utilities
- MapLibre GL JS base map with ESRI high-resolution satellite raster imagery.
- 3D extruded city layout across South Mumbai (2,926 buildings).
- Subterranean municipal utilities: **Mumbai Metro Line 3 (Aqua Line Underground Tunnel)** and **MCGM High-Pressure Stormwater & Freshwater Trunk Conduit**.

---

## 🛠️ Architecture & Tech Stack

| Layer | Technology |
|---|---|
| **Backend API** | FastAPI, Uvicorn, Python 3.10+ |
| **GIS & Geospatial Data** | GeoPandas, Shapely, GeoJSON (EPSG:4326 & EPSG:32643) |
| **3D Rendering Engine** | Three.js (r128), OrbitControls, PBR MeshPhysicalMaterial |
| **GIS Map Viewer** | MapLibre GL JS (v3.6.2) |
| **Frontend UI** | React 18, Glassmorphism CSS, JetBrains Mono & Plus Jakarta Sans |
| **Cadastre Standard** | Indian Bhu-Aadhaar 14-Digit ULPIN & Maharashtra 3D Cadastre (SVAMITVA) |

---

## 🚀 Setup & Installation

### 1. Prerequisites
- Python 3.10 or higher
- Git

### 2. Clone the Repository
```bash
git clone https://github.com/Vedant-npc/3D-Property-Mapping-System.git
cd 3D-Property-Mapping-System
```

### 3. Create & Activate a Virtual Environment
```bash
# Windows
python -m venv .venv
.\.venv\Scripts\activate

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

### 5. Environment Variables (Optional)
If you wish to enable Google Photorealistic 3D Tiles in CesiumJS mode, create a `.env` file:
```env
GOOGLE_3D_TILES_API_KEY=your_google_3d_tiles_api_key_here
```
*(By default, the platform runs on high-performance MapLibre GL + Three.js and does not require an API key).*

---

## 🎮 Running the Platform

Start the local server:
```bash
python app.py
```
Or with uvicorn:
```bash
uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

Open your browser and navigate to:
👉 **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

---

## 🕹️ Controls & Navigation

### City Map (MapLibre):
- **Left-Click + Drag**: Pan ground map
- **Right-Click + Drag**: Rotate bearing & pitch
- **Scroll Wheel**: Zoom in / out
- **W / A / S / D**: Pan map via keyboard
- **Q / E**: 360° rotate left / right
- **R / F**: Tilt pitch up / down

### 3D Architectural Digital Twin (Three.js):
- **Left-Click + Drag**: Orbit 3D perspective
- **Right-Click + Drag**: Pan camera target
- **Scroll Wheel**: Smooth zoom
- **Hover**: Preview flat unit, carpet area, and ULPIN code
- **Click Unit**: Isolate flat and inspect full cadastral ownership card
- **Presets**: 🏙️ 3D Isometric, 📐 Front Elevation, 🗺️ Top-Down Plan

---

## 📡 REST API Endpoints

- `GET /` — Interactive 3D Digital Twin & GIS web interface.
- `GET /api/buildings` — GeoJSON FeatureCollection of all 2,926 South Mumbai structures enriched with `land_ulpin`, `cts_no`, and `cadastral_division`.
- `GET /api/utilities` — Subterranean Metro Line 3 and drainage infrastructure GeoJSON.
- `GET /api/building/{spatial_id}/cadastre` — Complete vertical cadastre hierarchy (`Building` → `Wings` → `Floors` → `Flats` → `3D ULPIN`, areas, owners, CTS records).

---

## 📄 License
This project is open-source under the MIT License.