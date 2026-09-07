import json
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=False)
GOOGLE_3D_TILES_API_KEY = os.getenv("GOOGLE_3D_TILES_API_KEY", "").strip()

from src.cadastre_service import generate_building_cadastre

app = FastAPI(title="South Mumbai 3D Urban Architecture Twin - Vertical ULPIN Cadastre")

BUILDINGS_PATH = BASE_DIR / "data" / "processed" / "buildings.geojson"
UTILITIES_PATH = BASE_DIR / "data" / "processed" / "utilities.geojson"

if not BUILDINGS_PATH.exists() or not UTILITIES_PATH.exists():
    from src.ingest_south_mumbai import build_south_mumbai_dataset
    build_south_mumbai_dataset()

CACHED_BUILDINGS_INDEX = {}

def load_buildings_index():
    global CACHED_BUILDINGS_INDEX
    if BUILDINGS_PATH.exists():
        with open(BUILDINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            for feat in data.get("features", []):
                sp_id = feat.get("properties", {}).get("spatial_id")
                if sp_id:
                    CACHED_BUILDINGS_INDEX[sp_id] = feat

load_buildings_index()

@app.get("/api/buildings")
def get_buildings():
    with open(BUILDINGS_PATH, "r", encoding="utf-8") as f:
        return JSONResponse(content=json.load(f))

@app.get("/api/utilities")
def get_utilities():
    with open(UTILITIES_PATH, "r", encoding="utf-8") as f:
        return JSONResponse(content=json.load(f))

@app.get("/api/building/{spatial_id}/cadastre")
def get_building_cadastre_endpoint(spatial_id: str):
    feat = CACHED_BUILDINGS_INDEX.get(spatial_id)
    if not feat:
        with open(BUILDINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            for item in data.get("features", []):
                if item.get("properties", {}).get("spatial_id") == spatial_id:
                    feat = item
                    break
    if not feat:
        raise HTTPException(status_code=404, detail="Building not found in South Mumbai cadastral registry.")
    
    props = feat.get("properties", {})
    cadastre = generate_building_cadastre(props)
    cadastre["geometry"] = feat.get("geometry", {})
    return JSONResponse(content=cadastre)

@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    google_key_literal = json.dumps(GOOGLE_3D_TILES_API_KEY)
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>South Mumbai 3D Urban Architecture Twin - Vertical ULPIN Cadastre</title>
    <meta name="viewport" content="initial-scale=1,maximum-scale=1,user-scalable=no">
    <!-- Fonts & Icons -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet">
    <!-- CesiumJS -->
    <script src="https://cdn.jsdelivr.net/npm/cesium@1.124.0/Build/Cesium/Cesium.js"></script>
    <link href="https://cdn.jsdelivr.net/npm/cesium@1.124.0/Build/Cesium/Widgets/widgets.css" rel="stylesheet" />
    <!-- MapLibre GL JS -->
    <script src="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.js"></script>
    <link href="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.css" rel="stylesheet" />
    <!-- Three.js & OrbitControls -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
    <!-- React 18 & Babel -->
    <script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
    <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
    <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>

    <style>
        :root {
            --bg-dark: #070b14;
            --bg-card: rgba(13, 20, 36, 0.92);
            --bg-card-hover: rgba(22, 33, 58, 0.95);
            --accent-cyan: #00e5ff;
            --accent-blue: #38bdf8;
            --accent-emerald: #10b981;
            --accent-amber: #f59e0b;
            --border-subtle: rgba(56, 189, 248, 0.18);
            --border-glow: rgba(0, 229, 255, 0.45);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-dim: #64748b;
        }

        * { box-sizing: border-box; }
        body, html {
            margin: 0; padding: 0; width: 100%; height: 100%;
            font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
            background: var(--bg-dark); color: var(--text-primary);
            overflow: hidden; user-select: none;
        }

        #map, #fallback-map { position: absolute; top: 0; bottom: 0; width: 100%; height: 100%; }
        #map { display: block; background: #020816; }
        #fallback-map { display: none; }
        .cesium-viewer { background: #030b18; }

        ::-webkit-scrollbar { width: 5px; height: 5px; }
        ::-webkit-scrollbar-track { background: rgba(5, 10, 20, 0.6); }
        ::-webkit-scrollbar-thumb { background: rgba(56, 189, 248, 0.3); border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--accent-cyan); }

        .glass-panel {
            background: var(--bg-card);
            backdrop-filter: blur(18px);
            -webkit-backdrop-filter: blur(18px);
            border: 1px solid var(--border-subtle);
            border-radius: 12px;
            box-shadow: 0 16px 40px rgba(0, 0, 0, 0.7);
        }

        .code-font {
            font-family: 'JetBrains Mono', monospace;
        }

        #viewport-tooltip {
            position: absolute; display: none; pointer-events: none; z-index: 50;
            background: rgba(8, 14, 28, 0.95); border: 1px solid var(--accent-cyan);
            border-radius: 8px; padding: 8px 12px; font-size: 11px;
            box-shadow: 0 8px 24px rgba(0, 229, 255, 0.25);
            transform: translate(-50%, -120%); transition: opacity 0.15s;
        }

        #twin-workspace {
            position: absolute; top: 0; left: 0; width: 100vw; height: 100vh;
            background: radial-gradient(circle at 50% 30%, #0d172e 0%, #060913 100%);
            z-index: 40; display: none; flex-direction: column;
        }

        #twin-canvas-container {
            flex: 1; width: 100%; height: 100%; position: relative; overflow: hidden;
        }

        .pulsing-dot {
            width: 8px; height: 8px; border-radius: 50%; background: #10b981;
            box-shadow: 0 0 10px #10b981; animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
            70% { transform: scale(1.1); box-shadow: 0 0 0 8px rgba(16, 185, 129, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
        }

        #react-root {
            position: absolute; top: 0; left: 0; width: 100%; height: 100%;
            pointer-events: none; z-index: 45;
        }
        #react-root > * {
            pointer-events: auto;
        }
    </style>
</head>
<body>
    <div id="map"></div>
    <div id="fallback-map"></div>

    <div id="twin-workspace">
        <div id="twin-canvas-container">
            <div id="viewport-tooltip">
                <div id="tt-title" style="font-weight: 700; color: var(--accent-cyan); margin-bottom: 2px;"></div>
                <div id="tt-sub" style="color: var(--text-secondary);"></div>
                <div id="tt-ulpin" class="code-font" style="color: var(--accent-amber); font-size: 10px; margin-top: 4px;"></div>
            </div>
        </div>
    </div>

    <div id="react-root"></div>

    <script type="text/babel">
        const { useState, useEffect, useRef } = React;

        const GOOGLE_3D_TILES_API_KEY = __GOOGLE_3D_TILES_API_KEY__;
        const SOUTH_MUMBAI = { lon: 72.8270, lat: 18.9280 };

        window.appBridge = {
            openDigitalTwin: null,
            closeDigitalTwin: null,
            selectFlat: null,
            selectFloor: null,
            currentBuilding: null,
            currentCadastre: null
        };

        class ArchitecturalDigitalTwinRenderer {
            constructor(containerId) {
                this.container = document.getElementById(containerId);
                this.scene = null;
                this.camera = null;
                this.renderer = null;
                this.controls = null;
                this.animId = null;

                this.buildingData = null;
                this.cadastreData = null;

                this.floorGroups = [];
                this.flatMeshes = [];
                this.allInteractiveMeshes = [];

                this.selectedFlatId = null;
                this.selectedFloorIndex = null;

                this.explodeRatio = 0.0;
                this.targetExplodeRatio = 0.0;

                this.raycaster = new THREE.Raycaster();
                this.mouse = new THREE.Vector2();

                this.materials = this.initMaterials();

                this.camTween = {
                    active: false,
                    startPos: new THREE.Vector3(),
                    targetPos: new THREE.Vector3(),
                    startLook: new THREE.Vector3(),
                    targetLook: new THREE.Vector3(),
                    progress: 0,
                    duration: 45
                };

                this.init();
            }

            initMaterials() {
                return {
                    slabConcrete: new THREE.MeshStandardMaterial({
                        color: 0x1f2937, roughness: 0.82, metalness: 0.18
                    }),
                    slabEdge: new THREE.MeshStandardMaterial({
                        color: 0x374151, roughness: 0.7, metalness: 0.3
                    }),
                    exteriorStone: new THREE.MeshStandardMaterial({
                        color: 0x334155, roughness: 0.78, metalness: 0.15
                    }),
                    exteriorAccent: new THREE.MeshStandardMaterial({
                        color: 0x1e293b, roughness: 0.6, metalness: 0.35
                    }),
                    windowGlass: new THREE.MeshPhysicalMaterial({
                        color: 0x38bdf8, roughness: 0.08, transmission: 0.82, opacity: 0.75,
                        transparent: true, reflectivity: 0.92, clearcoat: 1.0, clearcoatRoughness: 0.1
                    }),
                    windowGlassWarm: new THREE.MeshPhysicalMaterial({
                        color: 0x0284c7, roughness: 0.12, transmission: 0.78, opacity: 0.8,
                        transparent: true, reflectivity: 0.88, clearcoat: 1.0
                    }),
                    aluminumFrame: new THREE.MeshStandardMaterial({
                        color: 0x0f172a, roughness: 0.4, metalness: 0.85
                    }),
                    balconyDeck: new THREE.MeshStandardMaterial({
                        color: 0x475569, roughness: 0.85, metalness: 0.1
                    }),
                    balconyGlassRailing: new THREE.MeshPhysicalMaterial({
                        color: 0x00e5ff, roughness: 0.15, transmission: 0.9, opacity: 0.65,
                        transparent: true, reflectivity: 0.85
                    }),
                    metalRailing: new THREE.MeshStandardMaterial({
                        color: 0x94a3b8, roughness: 0.35, metalness: 0.9
                    }),
                    entranceDoor: new THREE.MeshPhysicalMaterial({
                        color: 0x0284c7, roughness: 0.1, transmission: 0.9, opacity: 0.85,
                        transparent: true
                    }),
                    roofHVAC: new THREE.MeshStandardMaterial({
                        color: 0x4b5563, roughness: 0.65, metalness: 0.7
                    }),
                    flatFloorSelected: new THREE.MeshStandardMaterial({
                        color: 0x00e5ff, emissive: 0x0088aa, emissiveIntensity: 0.75,
                        roughness: 0.3, metalness: 0.5
                    }),
                    ghostedMaterial: new THREE.MeshPhysicalMaterial({
                        color: 0x0f172a, roughness: 0.2, transmission: 0.85, opacity: 0.18,
                        transparent: true, reflectivity: 0.7
                    })
                };
            }

            init() {
                const w = this.container.clientWidth || window.innerWidth;
                const h = this.container.clientHeight || window.innerHeight;

                this.scene = new THREE.Scene();
                this.scene.background = new THREE.Color(0x060913);

                this.camera = new THREE.PerspectiveCamera(42, w / h, 0.5, 3000);

                this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
                this.renderer.setSize(w, h);
                this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
                this.renderer.shadowMap.enabled = true;
                this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
                this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
                this.renderer.toneMappingExposure = 1.15;
                this.container.appendChild(this.renderer.domElement);

                if (typeof THREE.OrbitControls !== 'undefined') {
                    this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
                    this.controls.enableDamping = true;
                    this.controls.dampingFactor = 0.06;
                    this.controls.maxPolarAngle = Math.PI / 2 - 0.03;
                    this.controls.minDistance = 6;
                    this.controls.maxDistance = 600;
                } else {
                    this.controls = { target: new THREE.Vector3(0, 20, 0), update: () => {} };
                    this.setupFallbackControls();
                }

                this.setupLighting();
                this.setupGround();

                window.addEventListener('resize', () => this.onResize());
                this.renderer.domElement.addEventListener('mousemove', (e) => this.onMouseMove(e));
                this.renderer.domElement.addEventListener('click', (e) => this.onClick(e));

                this.animate = this.animate.bind(this);
                this.animate();
            }

            setupLighting() {
                const ambient = new THREE.AmbientLight(0xffffff, 0.85);
                this.scene.add(ambient);

                const hemiLight = new THREE.HemisphereLight(0xe0f2fe, 0x090d16, 0.95);
                hemiLight.position.set(0, 200, 0);
                this.scene.add(hemiLight);

                const sun = new THREE.DirectionalLight(0xfffbeb, 1.9);
                sun.position.set(120, 220, 140);
                sun.castShadow = true;
                sun.shadow.mapSize.width = 2048;
                sun.shadow.mapSize.height = 2048;
                sun.shadow.camera.near = 10;
                sun.shadow.camera.far = 600;
                const d = 100;
                sun.shadow.camera.left = -d;
                sun.shadow.camera.right = d;
                sun.shadow.camera.top = d;
                sun.shadow.camera.bottom = -d;
                sun.shadow.bias = -0.0004;
                this.scene.add(sun);

                const rimLight = new THREE.DirectionalLight(0x00e5ff, 1.25);
                rimLight.position.set(-140, 90, -140);
                this.scene.add(rimLight);
            }

            setupGround() {
                const gridHelper = new THREE.GridHelper(260, 52, 0x00e5ff, 0x1e293b);
                gridHelper.position.y = -0.05;
                gridHelper.material.opacity = 0.45;
                gridHelper.material.transparent = true;
                this.scene.add(gridHelper);

                const groundGeo = new THREE.PlaneGeometry(320, 320);
                const groundMat = new THREE.MeshStandardMaterial({
                    color: 0x060913, roughness: 0.9, metalness: 0.1
                });
                const ground = new THREE.Mesh(groundGeo, groundMat);
                ground.rotation.x = -Math.PI / 2;
                ground.position.y = -0.1;
                ground.receiveShadow = true;
                this.scene.add(ground);
            }

            setupFallbackControls() {
                let isDragging = false, isPanning = false;
                let prevMouse = { x: 0, y: 0 };
                let spherical = { radius: 80, theta: 0.85, phi: 1.15 };

                const updateCam = () => {
                    spherical.phi = Math.max(0.08, Math.min(Math.PI - 0.08, spherical.phi));
                    this.camera.position.x = this.controls.target.x + spherical.radius * Math.sin(spherical.phi) * Math.sin(spherical.theta);
                    this.camera.position.y = this.controls.target.y + spherical.radius * Math.cos(spherical.phi);
                    this.camera.position.z = this.controls.target.z + spherical.radius * Math.sin(spherical.phi) * Math.cos(spherical.theta);
                    this.camera.lookAt(this.controls.target);
                };

                this.renderer.domElement.addEventListener('contextmenu', e => e.preventDefault());
                this.renderer.domElement.addEventListener('mousedown', (e) => {
                    if (e.button === 0) isDragging = true;
                    if (e.button === 2) isPanning = true;
                    prevMouse = { x: e.clientX, y: e.clientY };
                });
                window.addEventListener('mouseup', () => { isDragging = false; isPanning = false; });
                this.renderer.domElement.addEventListener('mousemove', (e) => {
                    const dx = e.clientX - prevMouse.x;
                    const dy = e.clientY - prevMouse.y;
                    if (isDragging) {
                        spherical.theta -= dx * 0.008;
                        spherical.phi -= dy * 0.008;
                        updateCam();
                    } else if (isPanning) {
                        this.controls.target.x -= dx * 0.12;
                        this.controls.target.y += dy * 0.12;
                        updateCam();
                    }
                    prevMouse = { x: e.clientX, y: e.clientY };
                });
                this.renderer.domElement.addEventListener('wheel', (e) => {
                    spherical.radius = Math.max(8, Math.min(800, spherical.radius + e.deltaY * 0.25));
                    updateCam();
                });
                updateCam();
            }

            onResize() {
                if (!this.container || !this.renderer || !this.camera) return;
                const w = this.container.clientWidth;
                const h = this.container.clientHeight;
                this.camera.aspect = w / h;
                this.camera.updateProjectionMatrix();
                this.renderer.setSize(w, h);
            }

            clearBuilding() {
                if (this.buildingGroup) {
                    this.scene.remove(this.buildingGroup);
                    this.buildingGroup = null;
                }
                this.floorGroups = [];
                this.flatMeshes = [];
                this.allInteractiveMeshes = [];
                this.selectedFlatId = null;
                this.selectedFloorIndex = null;
                this.explodeRatio = 0.0;
                this.targetExplodeRatio = 0.0;
            }

            loadBuilding(buildingFeature, cadastre) {
                this.clearBuilding();
                this.buildingData = buildingFeature;
                this.cadastreData = cadastre;

                const p = buildingFeature.properties;
                const geom = buildingFeature.geometry;

                let ring = [];
                if (geom.type === 'Polygon') {
                    ring = geom.coordinates[0];
                } else if (geom.type === 'MultiPolygon') {
                    ring = geom.coordinates[0][0];
                }
                if (!ring || ring.length < 3) return;

                let avgLon = 0, avgLat = 0;
                ring.forEach(pt => { avgLon += pt[0]; avgLat += pt[1]; });
                avgLon /= ring.length;
                avgLat /= ring.length;

                const SCALE_M = 111320;
                const cosLat = Math.cos(avgLat * Math.PI / 180);

                const shapePoints = ring.map(pt => new THREE.Vector2(
                    (pt[0] - avgLon) * SCALE_M * cosLat,
                    -(pt[1] - avgLat) * SCALE_M
                ));

                const shape = new THREE.Shape(shapePoints);
                const box2 = new THREE.Box2().setFromPoints(shapePoints);
                const size = new THREE.Vector2();
                box2.getSize(size);
                const center = new THREE.Vector2();
                box2.getCenter(center);

                const centeredPoints = shapePoints.map(pt => new THREE.Vector2(pt.x - center.x, pt.y - center.y));
                const centeredShape = new THREE.Shape(centeredPoints);

                this.buildingGroup = new THREE.Group();
                this.scene.add(this.buildingGroup);

                const floors = cadastre.floors_count || p.floors || 5;
                const floorHeight = cadastre.floor_height_m || (p.height_m / floors);
                const maxDim = Math.max(size.x, size.y, p.height_m || 50);

                this.buildArchitecturalFloors(centeredShape, centeredPoints, cadastre, floorHeight, size);
                this.buildGroundEntrance(size, floorHeight);
                this.buildRooftopCrown(centeredShape, floors * floorHeight, size);
                this.resetCameraToFraming(maxDim, p.height_m || 50);
            }

            buildArchitecturalFloors(centeredShape, points, cadastre, floorHeight, bboxSize) {
                const floors = cadastre.floors;

                floors.forEach((floorObj, flIdx) => {
                    const floorGroup = new THREE.Group();
                    floorGroup.position.y = flIdx * floorHeight;
                    floorGroup.userData = {
                        floorIndex: flIdx,
                        baseY: flIdx * floorHeight,
                        floorData: floorObj
                    };

                    const slabThickness = 0.36;
                    const slabGeom = new THREE.ExtrudeGeometry(centeredShape, {
                        depth: slabThickness,
                        bevelEnabled: true,
                        bevelSegments: 2,
                        steps: 1,
                        bevelSize: 0.16,
                        bevelThickness: 0.12
                    });
                    slabGeom.rotateX(-Math.PI / 2);

                    const slabMesh = new THREE.Mesh(slabGeom, this.materials.slabConcrete);
                    slabMesh.castShadow = true;
                    slabMesh.receiveShadow = true;
                    floorGroup.add(slabMesh);

                    const slabEdgeGeom = new THREE.EdgesGeometry(slabGeom, 35);
                    const slabEdge = new THREE.LineSegments(slabEdgeGeom, new THREE.LineBasicMaterial({
                        color: 0x00e5ff, transparent: true, opacity: 0.45
                    }));
                    floorGroup.add(slabEdge);

                    const units = floorObj.units || [];
                    const hWall = floorHeight - slabThickness;

                    units.forEach((unit, uIdx) => {
                        const flatGroup = new THREE.Group();
                        flatGroup.position.y = slabThickness;
                        flatGroup.userData = {
                            isFlat: true,
                            unitId: unit.unit_id,
                            unitData: unit,
                            floorIndex: flIdx,
                            wingId: unit.wing_id
                        };

                        const flatShape = this.createQuadrantShape(centeredShape, points, unit.quadrant, bboxSize);

                        const flatPlateGeom = new THREE.ExtrudeGeometry(flatShape, { depth: 0.08, bevelEnabled: false });
                        flatPlateGeom.rotateX(-Math.PI / 2);
                        const flatPlateMesh = new THREE.Mesh(flatPlateGeom, this.materials.exteriorAccent.clone());
                        flatPlateMesh.position.y = 0.02;
                        flatPlateMesh.userData = { isFlatClickable: true, unitId: unit.unit_id, unitData: unit };
                        flatGroup.add(flatPlateMesh);

                        const wallGeom = new THREE.ExtrudeGeometry(flatShape, { depth: hWall, bevelEnabled: false });
                        wallGeom.rotateX(-Math.PI / 2);
                        const wallMesh = new THREE.Mesh(wallGeom, this.materials.exteriorStone.clone());
                        wallMesh.castShadow = true;
                        wallMesh.receiveShadow = true;
                        wallMesh.userData = { isFlatClickable: true, unitId: unit.unit_id, unitData: unit };
                        flatGroup.add(wallMesh);

                        const glassInsetShape = this.createInsetShape(flatShape, 0.35);
                        if (glassInsetShape) {
                            const glassGeom = new THREE.ExtrudeGeometry(glassInsetShape, { depth: hWall * 0.82, bevelEnabled: false });
                            glassGeom.rotateX(-Math.PI / 2);
                            const glassMat = (uIdx % 2 === 0 ? this.materials.windowGlass : this.materials.windowGlassWarm).clone();
                            const glassMesh = new THREE.Mesh(glassGeom, glassMat);
                            glassMesh.position.y = hWall * 0.12;
                            glassMesh.userData = { isFlatClickable: true, unitId: unit.unit_id, unitData: unit };
                            flatGroup.add(glassMesh);

                            const frameEdges = new THREE.EdgesGeometry(glassGeom);
                            const frameLine = new THREE.LineSegments(frameEdges, new THREE.LineBasicMaterial({
                                color: 0x94a3b8, transparent: true, opacity: 0.65
                            }));
                            frameLine.position.y = hWall * 0.12;
                            flatGroup.add(frameLine);
                        }

                        const balconyMesh = this.createBalcony(unit.quadrant, bboxSize, hWall);
                        if (balconyMesh) {
                            balconyMesh.userData = { isFlatClickable: true, unitId: unit.unit_id, unitData: unit };
                            flatGroup.add(balconyMesh);
                        }

                        const flatEdgeGeom = new THREE.EdgesGeometry(wallGeom, 30);
                        const flatOutline = new THREE.LineSegments(flatEdgeGeom, new THREE.LineBasicMaterial({
                            color: 0x00e5ff, transparent: true, opacity: 0.0, linewidth: 2
                        }));
                        flatGroup.add(flatOutline);

                        flatGroup.userData.wallMesh = wallMesh;
                        flatGroup.userData.plateMesh = flatPlateMesh;
                        flatGroup.userData.outline = flatOutline;
                        flatGroup.userData.unitData = unit;

                        this.allInteractiveMeshes.push(wallMesh, flatPlateMesh);
                        this.flatMeshes.push(flatGroup);
                        floorGroup.add(flatGroup);
                    });

                    floorGroup.userData.slabMesh = slabMesh;
                    this.floorGroups.push(floorGroup);
                    this.buildingGroup.add(floorGroup);
                });
            }

            createQuadrantShape(fullShape, points, quadIdx, size) {
                const quadShape = new THREE.Shape();
                const halfW = size.x * 0.48;
                const halfH = size.y * 0.48;

                const inQuad = (points || []).filter(pt => {
                    if (quadIdx === 0) return pt.x >= -0.2 && pt.y >= -0.2;
                    if (quadIdx === 1) return pt.x <= 0.2 && pt.y >= -0.2;
                    if (quadIdx === 2) return pt.x <= 0.2 && pt.y <= 0.2;
                    return pt.x >= -0.2 && pt.y <= 0.2;
                });

                if (inQuad.length >= 3) {
                    const coreOffset = 0.32;
                    const cx = (quadIdx === 0 || quadIdx === 3 ? 1 : -1) * coreOffset;
                    const cy = (quadIdx === 0 || quadIdx === 1 ? 1 : -1) * coreOffset;
                    quadShape.moveTo(cx, cy);

                    const sorted = [...inQuad].sort((a, b) => Math.atan2(a.y - cy, a.x - cx) - Math.atan2(b.y - cy, b.x - cx));
                    sorted.forEach(pt => quadShape.lineTo(pt.x * 0.96, pt.y * 0.96));
                    quadShape.closePath();
                    return quadShape;
                }

                let minX = -halfW, maxX = 0, minY = -halfH, maxY = 0;
                if (quadIdx === 0) { minX = 0.3; maxX = halfW; minY = 0.3; maxY = halfH; }
                else if (quadIdx === 1) { minX = -halfW; maxX = -0.3; minY = 0.3; maxY = halfH; }
                else if (quadIdx === 2) { minX = -halfW; maxX = -0.3; minY = -halfH; maxY = -0.3; }
                else if (quadIdx === 3) { minX = 0.3; maxX = halfW; minY = -halfH; maxY = -0.3; }

                quadShape.moveTo(minX, minY);
                quadShape.lineTo(maxX, minY);
                quadShape.lineTo(maxX, maxY);
                quadShape.lineTo(minX, maxY);
                quadShape.closePath();
                return quadShape;
            }

            createInsetShape(shape, inset) {
                const s = new THREE.Shape();
                const pts = shape.getPoints();
                if (pts.length < 3) return null;
                pts.forEach((pt, i) => {
                    const sx = pt.x * (1 - inset * 0.15);
                    const sy = pt.y * (1 - inset * 0.15);
                    if (i === 0) s.moveTo(sx, sy);
                    else s.lineTo(sx, sy);
                });
                s.closePath();
                return s;
            }

            createBalcony(quadIdx, bboxSize, hWall) {
                const bGroup = new THREE.Group();
                const bWidth = Math.min(bboxSize.x * 0.35, 8.0);
                const bDepth = 1.6;
                const bThick = 0.22;

                const slabGeo = new THREE.BoxGeometry(bWidth, bThick, bDepth);
                const slab = new THREE.Mesh(slabGeo, this.materials.balconyDeck);
                slab.castShadow = true;
                bGroup.add(slab);

                const railH = 1.05;
                const railGeo = new THREE.BoxGeometry(bWidth, railH, 0.05);
                const rail = new THREE.Mesh(railGeo, this.materials.balconyGlassRailing);
                rail.position.set(0, railH / 2, bDepth / 2);
                bGroup.add(rail);

                const handrailGeo = new THREE.BoxGeometry(bWidth + 0.1, 0.06, 0.08);
                const handrail = new THREE.Mesh(handrailGeo, this.materials.aluminumFrame);
                handrail.position.set(0, railH, bDepth / 2);
                bGroup.add(handrail);

                const signX = (quadIdx === 0 || quadIdx === 3) ? 1 : -1;
                const signZ = (quadIdx === 0 || quadIdx === 1) ? 1 : -1;
                bGroup.position.set(signX * (bboxSize.x * 0.38), 0.15, signZ * (bboxSize.y * 0.38));
                return bGroup;
            }

            buildGroundEntrance(bboxSize, floorHeight) {
                const entranceGroup = new THREE.Group();
                entranceGroup.position.y = 0;

                const canopyW = Math.min(bboxSize.x * 0.45, 14);
                const canopyD = 4.2;
                const canopyThick = 0.3;
                const canopyGeo = new THREE.BoxGeometry(canopyW, canopyThick, canopyD);
                const canopy = new THREE.Mesh(canopyGeo, this.materials.slabEdge);
                canopy.position.set(0, floorHeight * 0.95, bboxSize.y * 0.48 + canopyD / 2);
                entranceGroup.add(canopy);

                const edgeGeo = new THREE.EdgesGeometry(canopyGeo);
                const line = new THREE.LineSegments(edgeGeo, new THREE.LineBasicMaterial({ color: 0x00e5ff, opacity: 0.8, transparent: true }));
                line.position.copy(canopy.position);
                entranceGroup.add(line);

                [-canopyW * 0.42, canopyW * 0.42].forEach(posX => {
                    const colGeo = new THREE.CylinderGeometry(0.25, 0.25, floorHeight * 0.95, 16);
                    const col = new THREE.Mesh(colGeo, this.materials.aluminumFrame);
                    col.position.set(posX, (floorHeight * 0.95) / 2, bboxSize.y * 0.48 + canopyD * 0.85);
                    col.castShadow = true;
                    entranceGroup.add(col);
                });

                const doorGeo = new THREE.BoxGeometry(canopyW * 0.55, floorHeight * 0.75, 0.1);
                const doors = new THREE.Mesh(doorGeo, this.materials.entranceDoor);
                doors.position.set(0, (floorHeight * 0.75) / 2, bboxSize.y * 0.48);
                entranceGroup.add(doors);

                this.buildingGroup.add(entranceGroup);
            }

            buildRooftopCrown(centeredShape, totalHeight, bboxSize) {
                const crownGroup = new THREE.Group();
                crownGroup.position.y = totalHeight;

                const parapetH = 1.15;
                const parapetGeom = new THREE.ExtrudeGeometry(centeredShape, { depth: parapetH, bevelEnabled: false });
                parapetGeom.rotateX(-Math.PI / 2);
                const parapetMesh = new THREE.Mesh(parapetGeom, this.materials.slabEdge);
                crownGroup.add(parapetMesh);

                const coreW = Math.min(bboxSize.x * 0.32, 10);
                const coreD = Math.min(bboxSize.y * 0.32, 10);
                const coreH = 3.8;
                const coreGeo = new THREE.BoxGeometry(coreW, coreH, coreD);
                const core = new THREE.Mesh(coreGeo, this.materials.exteriorStone);
                core.position.set(0, coreH / 2, 0);
                core.castShadow = true;
                crownGroup.add(core);

                [-coreW * 0.7, coreW * 0.7].forEach((posX, idx) => {
                    const hvacGeo = new THREE.BoxGeometry(2.4, 1.6, 2.8);
                    const hvac = new THREE.Mesh(hvacGeo, this.materials.roofHVAC);
                    hvac.position.set(posX, 0.8, -coreD * 0.5);
                    crownGroup.add(hvac);

                    const tankGeo = new THREE.CylinderGeometry(1.1, 1.1, 2.2, 16);
                    const tank = new THREE.Mesh(tankGeo, this.materials.aluminumFrame);
                    tank.position.set(posX, 1.1, coreD * 0.5);
                    crownGroup.add(tank);
                });

                const spireH = Math.min(totalHeight * 0.22, 18);
                const spireGeo = new THREE.CylinderGeometry(0.08, 0.35, spireH, 8);
                const spire = new THREE.Mesh(spireGeo, this.materials.aluminumFrame);
                spire.position.set(0, coreH + spireH / 2, 0);
                crownGroup.add(spire);

                const beaconGeo = new THREE.SphereGeometry(0.3, 12, 12);
                const beaconMat = new THREE.MeshBasicMaterial({ color: 0xff3b30 });
                const beacon = new THREE.Mesh(beaconGeo, beaconMat);
                beacon.position.set(0, coreH + spireH, 0);
                crownGroup.add(beacon);

                crownGroup.userData = { isCrown: true, baseY: totalHeight };
                this.crownGroup = crownGroup;
                this.buildingGroup.add(crownGroup);
            }

            setExplode(ratio) {
                this.targetExplodeRatio = THREE.MathUtils.clamp(ratio, 0.0, 1.0);
            }

            updateExplodeAnimation() {
                const diff = this.targetExplodeRatio - this.explodeRatio;
                if (Math.abs(diff) > 0.002) {
                    this.explodeRatio += diff * 0.12;
                    const maxGap = 8.5;

                    this.floorGroups.forEach((fg, idx) => {
                        const targetY = fg.userData.baseY + (idx * maxGap * this.explodeRatio);
                        fg.position.y = targetY;
                    });

                    if (this.crownGroup) {
                        const crownTargetY = this.crownGroup.userData.baseY + (this.floorGroups.length * maxGap * this.explodeRatio);
                        this.crownGroup.position.y = crownTargetY;
                    }
                }
            }

            selectFlat(unitId) {
                this.selectedFlatId = unitId;

                this.flatMeshes.forEach(fg => {
                    const isTarget = (fg.userData.unitId === unitId);
                    const isSameFloor = (this.selectedFloorIndex !== null && fg.userData.floorIndex === this.selectedFloorIndex);

                    if (unitId === null) {
                        fg.userData.wallMesh.material = this.materials.exteriorStone;
                        fg.userData.plateMesh.material = this.materials.exteriorAccent;
                        fg.userData.outline.material.opacity = 0.0;
                    } else if (isTarget) {
                        fg.userData.wallMesh.material = this.materials.flatFloorSelected;
                        fg.userData.plateMesh.material = this.materials.flatFloorSelected;
                        fg.userData.outline.material.opacity = 1.0;
                    } else {
                        fg.userData.wallMesh.material = this.materials.ghostedMaterial;
                        fg.userData.plateMesh.material = this.materials.ghostedMaterial;
                        fg.userData.outline.material.opacity = isSameFloor ? 0.35 : 0.08;
                    }
                });

                if (unitId) {
                    const targetFlat = this.flatMeshes.find(f => f.userData.unitId === unitId);
                    if (targetFlat) {
                        const worldPos = new THREE.Vector3();
                        targetFlat.getWorldPosition(worldPos);
                        this.tweenCameraTo(
                            new THREE.Vector3(worldPos.x + 22, worldPos.y + 16, worldPos.z + 28),
                            worldPos
                        );
                    }
                }
            }

            selectFloor(floorIndex) {
                this.selectedFloorIndex = floorIndex;
                this.selectedFlatId = null;

                this.floorGroups.forEach((fg, idx) => {
                    const isSelected = (idx === floorIndex);
                    fg.traverse(child => {
                        if (child.isMesh && child.userData.isFlatClickable) {
                            if (floorIndex === null || isSelected) {
                                child.material = this.materials.exteriorStone;
                            } else {
                                child.material = this.materials.ghostedMaterial;
                            }
                        }
                    });
                });

                if (floorIndex !== null && this.floorGroups[floorIndex]) {
                    const targetFloor = this.floorGroups[floorIndex];
                    const worldPos = new THREE.Vector3();
                    targetFloor.getWorldPosition(worldPos);
                    this.tweenCameraTo(
                        new THREE.Vector3(worldPos.x + 36, worldPos.y + 24, worldPos.z + 42),
                        worldPos
                    );
                }
            }

            tweenCameraTo(targetPos, targetLook) {
                this.camTween.active = true;
                this.camTween.startPos.copy(this.camera.position);
                this.camTween.targetPos.copy(targetPos);
                this.camTween.startLook.copy(this.controls.target);
                this.camTween.targetLook.copy(targetLook);
                this.camTween.progress = 0;
            }

            updateCameraTween() {
                if (!this.camTween.active) return;
                this.camTween.progress += 1.0 / this.camTween.duration;
                const t = THREE.MathUtils.clamp(this.camTween.progress, 0.0, 1.0);
                const ease = t * t * (3.0 - 2.0 * t);

                this.camera.position.lerpVectors(this.camTween.startPos, this.camTween.targetPos, ease);
                this.controls.target.lerpVectors(this.camTween.startLook, this.camTween.targetLook, ease);

                if (t >= 1.0) {
                    this.camTween.active = false;
                }
            }

            setCameraPreset(preset) {
                if (!this.buildingGroup) return;
                const box = new THREE.Box3().setFromObject(this.buildingGroup);
                const center = box.getCenter(new THREE.Vector3());
                const size = box.getSize(new THREE.Vector3());
                const maxDim = Math.max(size.x, size.y, size.z);

                if (preset === 'iso') {
                    this.tweenCameraTo(
                        new THREE.Vector3(center.x + maxDim * 1.4, center.y + maxDim * 1.1, center.z + maxDim * 1.4),
                        center
                    );
                } else if (preset === 'elevation') {
                    this.tweenCameraTo(
                        new THREE.Vector3(center.x, center.y, center.z + maxDim * 2.2),
                        center
                    );
                } else if (preset === 'plan') {
                    this.tweenCameraTo(
                        new THREE.Vector3(center.x, center.y + maxDim * 2.5, center.z + 0.1),
                        center
                    );
                }
            }

            resetCameraToFraming(maxDim, height) {
                const targetLook = new THREE.Vector3(0, height / 2, 0);
                const targetPos = new THREE.Vector3(maxDim * 1.6, height * 0.9 + maxDim * 0.8, maxDim * 1.6);
                this.camera.position.copy(targetPos);
                this.controls.target.copy(targetLook);
                this.camera.lookAt(targetLook);
            }

            onMouseMove(event) {
                const rect = this.renderer.domElement.getBoundingClientRect();
                this.mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
                this.mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

                this.raycaster.setFromCamera(this.mouse, this.camera);
                const intersects = this.raycaster.intersectObjects(this.allInteractiveMeshes, false);

                const tooltip = document.getElementById('viewport-tooltip');
                if (intersects.length > 0) {
                    const top = intersects[0];
                    const uData = top.object.userData.unitData;
                    if (uData) {
                        tooltip.style.display = 'block';
                        tooltip.style.left = `${event.clientX}px`;
                        tooltip.style.top = `${event.clientY}px`;
                        document.getElementById('tt-title').innerText = `Flat ${uData.unit_number} (${uData.wing_id})`;
                        document.getElementById('tt-sub').innerText = `${uData.unit_type} • ${uData.carpet_area_sqm} m² (${uData.carpet_area_sqft} sq.ft)`;
                        document.getElementById('tt-ulpin').innerText = `ULPIN: ${uData.unit_ulpin}`;
                        this.renderer.domElement.style.cursor = 'pointer';
                        return;
                    }
                }
                tooltip.style.display = 'none';
                this.renderer.domElement.style.cursor = 'default';
            }

            onClick(event) {
                this.raycaster.setFromCamera(this.mouse, this.camera);
                const intersects = this.raycaster.intersectObjects(this.allInteractiveMeshes, false);
                if (intersects.length > 0) {
                    const uData = intersects[0].object.userData.unitData;
                    if (uData && window.appBridge.selectFlat) {
                        window.appBridge.selectFlat(uData);
                    }
                }
            }

            animate() {
                this.animId = requestAnimationFrame(this.animate);
                this.controls.update();
                this.updateExplodeAnimation();
                this.updateCameraTween();
                this.renderer.render(this.scene, this.camera);
            }
        }

        function App() {
            const [viewMode, setViewMode] = useState('map');
            const [buildingsData, setBuildingsData] = useState(null);
            const [selectedBuilding, setSelectedBuilding] = useState(null);
            const [cadastre, setCadastre] = useState(null);
            const [selectedWing, setSelectedWing] = useState('all');
            const [selectedFloor, setSelectedFloor] = useState(null);
            const [selectedFlat, setSelectedFlat] = useState(null);
            const [explodeRatio, setExplodeRatio] = useState(0);
            const [searchQuery, setSearchQuery] = useState('');
            const [searchResults, setSearchResults] = useState([]);
            const [twinPreset, setTwinPreset] = useState('iso');

            const twinRef = useRef(null);

            useEffect(() => {
                fetch('/api/buildings')
                    .then(r => r.json())
                    .then(data => {
                        setBuildingsData(data);
                        initMapLibre(data);
                    })
                    .catch(err => console.error("Buildings fetch error:", err));
            }, []);

            useEffect(() => {
                if (!twinRef.current) {
                    twinRef.current = new ArchitecturalDigitalTwinRenderer('twin-canvas-container');
                }
            }, []);

            useEffect(() => {
                window.appBridge.openDigitalTwin = (bldFeat) => {
                    handleOpenTwin(bldFeat);
                };
                window.appBridge.selectFlat = (unitData) => {
                    setSelectedFlat(unitData);
                    setSelectedFloor(unitData.floor_index);
                    if (twinRef.current) twinRef.current.selectFlat(unitData.unit_id);
                };
            }, []);

            const handleOpenTwin = async (bldFeat) => {
                setSelectedBuilding(bldFeat);
                setSelectedFloor(null);
                setSelectedFlat(null);
                setExplodeRatio(0);
                setViewMode('twin');

                document.getElementById('twin-workspace').style.display = 'flex';

                try {
                    const spId = bldFeat.properties.spatial_id;
                    const res = await fetch(`/api/building/${spId}/cadastre`);
                    const cad = await res.json();
                    setCadastre(cad);

                    if (twinRef.current) {
                        setTimeout(() => {
                            twinRef.current.onResize();
                            twinRef.current.loadBuilding(bldFeat, cad);
                        }, 50);
                    }
                } catch (err) {
                    console.error("Cadastre fetch failed:", err);
                }
            };

            const handleCloseTwin = () => {
                setViewMode('map');
                document.getElementById('twin-workspace').style.display = 'none';
                if (twinRef.current) {
                    twinRef.current.clearBuilding();
                }
            };

            const handleExplodeChange = (val) => {
                const num = parseFloat(val);
                setExplodeRatio(num);
                if (twinRef.current) twinRef.current.setExplode(num);
            };

            const handleFloorClick = (flIdx) => {
                if (selectedFloor === flIdx) {
                    setSelectedFloor(null);
                    if (twinRef.current) twinRef.current.selectFloor(null);
                } else {
                    setSelectedFloor(flIdx);
                    setSelectedFlat(null);
                    if (twinRef.current) twinRef.current.selectFloor(flIdx);
                }
            };

            const handleFlatClick = (unit) => {
                setSelectedFlat(unit);
                setSelectedFloor(unit.floor_index);
                if (twinRef.current) twinRef.current.selectFlat(unit.unit_id);
            };

            const handleCameraPreset = (preset) => {
                setTwinPreset(preset);
                if (twinRef.current) twinRef.current.setCameraPreset(preset);
            };

            const handleSearch = (q) => {
                setSearchQuery(q);
                if (!q.trim() || !buildingsData) {
                    setSearchResults([]);
                    return;
                }
                const lower = q.toLowerCase();
                const matched = buildingsData.features.filter(f => {
                    const p = f.properties;
                    return (p.name && p.name.toLowerCase().includes(lower)) ||
                           (p.land_ulpin && p.land_ulpin.includes(lower)) ||
                           (p.street && p.street.toLowerCase().includes(lower));
                }).slice(0, 6);
                setSearchResults(matched);
            };

            const initMapLibre = (bldGeo) => {
                const map = new maplibregl.Map({
                    container: 'map',
                    style: {
                        version: 8,
                        sources: {
                            'esri-satellite': {
                                type: 'raster',
                                tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
                                tileSize: 256,
                                attribution: '&copy; ESRI World Imagery'
                            }
                        },
                        layers: [{
                            id: 'satellite-base',
                            type: 'raster',
                            source: 'esri-satellite',
                            paint: { 'raster-brightness-max': 0.85, 'raster-contrast': 0.15 }
                        }]
                    },
                    center: [SOUTH_MUMBAI.lon, SOUTH_MUMBAI.lat],
                    zoom: 16.2,
                    pitch: 60,
                    bearing: -18,
                    maxPitch: 85,
                    antialias: true
                });

                map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }));

                map.on('load', async () => {
                    const utilities = await fetch('/api/utilities').then(r => r.json());

                    map.addSource('util-src', { type: 'geojson', data: utilities });
                    map.addLayer({
                        id: 'metro-dashed',
                        type: 'line',
                        source: 'util-src',
                        filter: ['==', 'category', 'metro_underground'],
                        paint: { 'line-color': '#00e5ff', 'line-width': 6, 'line-dasharray': [2, 1.5] }
                    });
                    map.addLayer({
                        id: 'pipeline-solid',
                        type: 'line',
                        source: 'util-src',
                        filter: ['!=', 'category', 'metro_underground'],
                        paint: { 'line-color': '#ff3b30', 'line-width': 5.5, 'line-opacity': 0.9 }
                    });

                    map.addSource('buildings-src', { type: 'geojson', data: bldGeo });
                    map.addLayer({
                        id: 'buildings-3d',
                        type: 'fill-extrusion',
                        source: 'buildings-src',
                        paint: {
                            'fill-extrusion-color': [
                                'interpolate', ['linear'], ['get', 'height_m'],
                                0, '#0284c7',
                                25, '#00e5ff',
                                55, '#38bdf8',
                                85, '#818cf8',
                                120, '#c084fc'
                            ],
                            'fill-extrusion-height': ['get', 'height_m'],
                            'fill-extrusion-base': 0,
                            'fill-extrusion-opacity': 0.92
                        }
                    });

                    map.on('click', 'buildings-3d', (e) => {
                        if (!e.features.length) return;
                        const f = e.features[0];
                        setSelectedBuilding(f);
                    });

                    map.on('mouseenter', 'buildings-3d', () => map.getCanvas().style.cursor = 'pointer');
                    map.on('mouseleave', 'buildings-3d', () => map.getCanvas().style.cursor = '');
                });

                window.mapInstance = map;
            };

            return (
                <div style={{ width: '100%', height: '100%', position: 'relative', pointerEvents: 'none' }}>
                    <div className="glass-panel" style={{
                        position: 'absolute', top: 16, left: 16, right: 16, height: 64,
                        padding: '0 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                        zIndex: 60, pointerEvents: 'auto'
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                            <div style={{
                                width: 38, height: 38, borderRadius: 8, background: 'linear-gradient(135deg, #00e5ff 0%, #3b82f6 100%)',
                                display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, boxShadow: '0 0 16px rgba(0,229,255,0.5)'
                            }}>
                                🏛️
                            </div>
                            <div>
                                <div style={{ fontWeight: 800, fontSize: 16, letterSpacing: '0.02em', color: '#fff', display: 'flex', alignItems: 'center', gap: 8 }}>
                                    SOUTH MUMBAI 3D DIGITAL TWIN
                                    <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 20, background: 'rgba(0,229,255,0.15)', color: 'var(--accent-cyan)', border: '1px solid var(--accent-cyan)' }}>
                                        BHU-AADHAAR 3D CADASTRE
                                    </span>
                                </div>
                                <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                                    {cadastre ? (
                                        <span>
                                            <b style={{ color: '#fff' }}>{cadastre.name}</b> • {cadastre.land_ulpin} • {cadastre.cts_no}
                                        </span>
                                    ) : "Cadastral Land Parcel & Vertical Property Identification System"}
                                </div>
                            </div>
                        </div>

                        <div style={{ position: 'relative', width: 340 }}>
                            <input
                                type="text"
                                value={searchQuery}
                                onChange={(e) => handleSearch(e.target.value)}
                                placeholder="🔍 Search by ULPIN, Building or Street..."
                                style={{
                                    width: '100%', background: 'rgba(15, 23, 42, 0.8)', border: '1px solid var(--border-subtle)',
                                    borderRadius: 8, padding: '8px 14px', color: '#fff', fontSize: 12, outline: 'none'
                                }}
                            />
                            {searchResults.length > 0 && (
                                <div className="glass-panel" style={{
                                    position: 'absolute', top: 42, left: 0, right: 0, maxHeight: 280, overflowY: 'auto',
                                    zIndex: 100, padding: 8
                                }}>
                                    {searchResults.map(b => (
                                        <div
                                            key={b.properties.spatial_id}
                                            onClick={() => {
                                                handleOpenTwin(b);
                                                setSearchResults([]);
                                                setSearchQuery('');
                                            }}
                                            style={{
                                                padding: '8px 10px', borderRadius: 6, cursor: 'pointer', fontSize: 12,
                                                marginBottom: 4, background: 'rgba(30, 41, 59, 0.5)', transition: 'background 0.15s'
                                            }}
                                            onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(0, 229, 255, 0.2)'}
                                            onMouseLeave={(e) => e.currentTarget.style.background = 'rgba(30, 41, 59, 0.5)'}
                                        >
                                            <div style={{ fontWeight: 700, color: 'var(--accent-cyan)' }}>{b.properties.name}</div>
                                            <div style={{ fontSize: 10, color: 'var(--text-secondary)' }}>
                                                {b.properties.land_ulpin} • {b.properties.street}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>

                        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                            {viewMode === 'twin' && (
                                <div style={{ display: 'flex', background: 'rgba(15,23,42,0.8)', borderRadius: 8, padding: 3, border: '1px solid var(--border-subtle)' }}>
                                    <button
                                        onClick={() => handleCameraPreset('iso')}
                                        style={{
                                            background: twinPreset === 'iso' ? 'var(--accent-cyan)' : 'transparent',
                                            color: twinPreset === 'iso' ? '#000' : 'var(--text-secondary)',
                                            border: 'none', padding: '6px 12px', borderRadius: 6, fontSize: 11, fontWeight: 700, cursor: 'pointer'
                                        }}
                                    >
                                        🏙️ 3D Isometric
                                    </button>
                                    <button
                                        onClick={() => handleCameraPreset('elevation')}
                                        style={{
                                            background: twinPreset === 'elevation' ? 'var(--accent-cyan)' : 'transparent',
                                            color: twinPreset === 'elevation' ? '#000' : 'var(--text-secondary)',
                                            border: 'none', padding: '6px 12px', borderRadius: 6, fontSize: 11, fontWeight: 700, cursor: 'pointer'
                                        }}
                                    >
                                        📐 Elevation
                                    </button>
                                    <button
                                        onClick={() => handleCameraPreset('plan')}
                                        style={{
                                            background: twinPreset === 'plan' ? 'var(--accent-cyan)' : 'transparent',
                                            color: twinPreset === 'plan' ? '#000' : 'var(--text-secondary)',
                                            border: 'none', padding: '6px 12px', borderRadius: 6, fontSize: 11, fontWeight: 700, cursor: 'pointer'
                                        }}
                                    >
                                        🗺️ Top Plan
                                    </button>
                                </div>
                            )}

                            {viewMode === 'twin' ? (
                                <button
                                    onClick={handleCloseTwin}
                                    style={{
                                        background: 'rgba(239, 68, 68, 0.2)', color: '#fca5a5', border: '1px solid rgba(239, 68, 68, 0.4)',
                                        padding: '8px 16px', borderRadius: 8, fontWeight: 700, fontSize: 12, cursor: 'pointer', transition: 'all 0.2s'
                                    }}
                                    onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(239, 68, 68, 0.4)'}
                                    onMouseLeave={(e) => e.currentTarget.style.background = 'rgba(239, 68, 68, 0.2)'}
                                >
                                    ← Exit 3D Digital Twin
                                </button>
                            ) : (
                                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
                                    <span className="pulsing-dot"></span> GIS Live Stream
                                </div>
                            )}
                        </div>
                    </div>

                    {viewMode === 'map' && selectedBuilding && (
                        <div className="glass-panel" style={{
                            position: 'absolute', bottom: 30, right: 30, width: 380, padding: 22,
                            pointerEvents: 'auto', zIndex: 60
                        }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <span style={{
                                    fontSize: 10, fontWeight: 800, padding: '3px 9px', borderRadius: 20,
                                    background: 'var(--accent-cyan)', color: '#000'
                                }}>
                                    3D URBAN CADASTRAL ASSET
                                </span>
                                <button
                                    onClick={() => setSelectedBuilding(null)}
                                    style={{ background: 'none', border: 'none', color: 'var(--text-dim)', cursor: 'pointer', fontSize: 16 }}
                                >
                                    ✕
                                </button>
                            </div>
                            <h3 style={{ margin: '12px 0 4px 0', fontSize: 17, color: '#fff' }}>
                                {selectedBuilding.properties.name}
                            </h3>
                            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 14 }}>
                                {selectedBuilding.properties.street}
                            </div>

                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 16 }}>
                                <div style={{ background: 'rgba(15,23,42,0.6)', padding: 8, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                    <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>LAND ULPIN</div>
                                    <div className="code-font" style={{ fontSize: 12, fontWeight: 700, color: 'var(--accent-amber)' }}>
                                        {selectedBuilding.properties.land_ulpin || "27010482910472"}
                                    </div>
                                </div>
                                <div style={{ background: 'rgba(15,23,42,0.6)', padding: 8, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                    <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>TOTAL HEIGHT</div>
                                    <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--accent-cyan)' }}>
                                        {selectedBuilding.properties.height_m}m ({selectedBuilding.properties.floors} Floors)
                                    </div>
                                </div>
                                <div style={{ background: 'rgba(15,23,42,0.6)', padding: 8, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                    <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>FOOTPRINT AREA</div>
                                    <div style={{ fontSize: 12, fontWeight: 700, color: '#fff' }}>
                                        {selectedBuilding.properties.area_sqm} m²
                                    </div>
                                </div>
                                <div style={{ background: 'rgba(15,23,42,0.6)', padding: 8, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                    <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>CTS SURVEY NO</div>
                                    <div style={{ fontSize: 12, fontWeight: 700, color: '#fff' }}>
                                        {selectedBuilding.properties.cts_no || "CTS 418/A"}
                                    </div>
                                </div>
                            </div>

                            <button
                                onClick={() => handleOpenTwin(selectedBuilding)}
                                style={{
                                    width: '100%', background: 'linear-gradient(135deg, #00e5ff 0%, #0284c7 100%)',
                                    color: '#000', border: 'none', padding: '12px', borderRadius: 8, fontWeight: 800,
                                    fontSize: 13, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    gap: 8, boxShadow: '0 0 20px rgba(0,229,255,0.4)', transition: 'all 0.2s'
                                }}
                            >
                                🏢 Launch 3D Architectural Digital Twin
                            </button>
                        </div>
                    )}

                    {viewMode === 'twin' && cadastre && (
                        <React.Fragment>
                            <div className="glass-panel" style={{
                                position: 'absolute', top: 96, left: 16, bottom: 24, width: 340,
                                display: 'flex', flexDirection: 'column', padding: 18, zIndex: 60,
                                pointerEvents: 'auto'
                            }}>
                                <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                                    <span style={{ color: 'var(--accent-cyan)' }}>South Mumbai</span> ›
                                    <span>{cadastre.cadastral_division.split(' ')[0]}</span> ›
                                    <b style={{ color: '#fff' }}>Floor {selectedFloor !== null ? selectedFloor + 1 : 'All'}</b>
                                    {selectedFlat && <span style={{ color: 'var(--accent-amber)' }}>› Flat {selectedFlat.unit_number}</span>}
                                </div>

                                <div style={{
                                    background: 'rgba(15,23,42,0.7)', borderRadius: 10, padding: 14,
                                    border: '1px solid var(--border-subtle)', marginBottom: 16
                                }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, fontWeight: 700, marginBottom: 8 }}>
                                        <span style={{ color: 'var(--accent-cyan)' }}>💥 Explode Floors</span>
                                        <span className="code-font" style={{ color: '#fff' }}>{Math.round(explodeRatio * 100)}%</span>
                                    </div>
                                    <input
                                        type="range"
                                        min="0"
                                        max="1"
                                        step="0.01"
                                        value={explodeRatio}
                                        onChange={(e) => handleExplodeChange(e.target.value)}
                                        style={{ width: '100%', accentColor: 'var(--accent-cyan)', cursor: 'pointer' }}
                                    />
                                    <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8 }}>
                                        <button
                                            onClick={() => handleExplodeChange(0)}
                                            style={{ background: 'none', border: '1px solid rgba(255,255,255,0.1)', color: 'var(--text-dim)', padding: '3px 8px', borderRadius: 4, fontSize: 10, cursor: 'pointer' }}
                                        >
                                            Stack (0%)
                                        </button>
                                        <button
                                            onClick={() => handleExplodeChange(0.5)}
                                            style={{ background: 'none', border: '1px solid rgba(255,255,255,0.1)', color: 'var(--text-dim)', padding: '3px 8px', borderRadius: 4, fontSize: 10, cursor: 'pointer' }}
                                        >
                                            Inspect (50%)
                                        </button>
                                        <button
                                            onClick={() => handleExplodeChange(1.0)}
                                            style={{ background: 'none', border: '1px solid rgba(255,255,255,0.1)', color: 'var(--text-dim)', padding: '3px 8px', borderRadius: 4, fontSize: 10, cursor: 'pointer' }}
                                        >
                                            Explode (100%)
                                        </button>
                                    </div>
                                </div>

                                <div style={{ display: 'flex', gap: 6, marginBottom: 14 }}>
                                    <button
                                        onClick={() => setSelectedWing('all')}
                                        style={{
                                            flex: 1, padding: '7px 0', borderRadius: 6, fontSize: 11, fontWeight: 700,
                                            background: selectedWing === 'all' ? 'var(--accent-cyan)' : 'rgba(15,23,42,0.8)',
                                            color: selectedWing === 'all' ? '#000' : 'var(--text-secondary)',
                                            border: '1px solid var(--border-subtle)', cursor: 'pointer'
                                        }}
                                    >
                                        All Wings
                                    </button>
                                    {cadastre.wings.map(w => (
                                        <button
                                            key={w.wing_id}
                                            onClick={() => setSelectedWing(w.wing_id)}
                                            style={{
                                                flex: 1, padding: '7px 0', borderRadius: 6, fontSize: 11, fontWeight: 700,
                                                background: selectedWing === w.wing_id ? 'var(--accent-cyan)' : 'rgba(15,23,42,0.8)',
                                                color: selectedWing === w.wing_id ? '#000' : 'var(--text-secondary)',
                                                border: '1px solid var(--border-subtle)', cursor: 'pointer'
                                            }}
                                        >
                                            {w.wing_id}
                                        </button>
                                    ))}
                                </div>

                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                                    <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase' }}>
                                        Vertical Slices ({cadastre.floors_count} Levels)
                                    </span>
                                    {selectedFloor !== null && (
                                        <button
                                            onClick={() => handleFloorClick(selectedFloor)}
                                            style={{ background: 'none', border: 'none', color: 'var(--accent-cyan)', fontSize: 11, cursor: 'pointer', fontWeight: 600 }}
                                        >
                                            Reset Isolation
                                        </button>
                                    )}
                                </div>

                                <div style={{ flex: 1, overflowY: 'auto', paddingRight: 4 }}>
                                    {cadastre.floors.slice().reverse().map(fl => {
                                        const isFlActive = (selectedFloor === fl.floor_index);
                                        return (
                                            <div
                                                key={fl.floor_index}
                                                style={{
                                                    background: isFlActive ? 'rgba(0, 229, 255, 0.12)' : 'rgba(15, 23, 42, 0.6)',
                                                    border: isFlActive ? '1px solid var(--accent-cyan)' : '1px solid var(--border-subtle)',
                                                    borderRadius: 8, padding: 10, marginBottom: 8, transition: 'all 0.15s'
                                                }}
                                            >
                                                <div
                                                    onClick={() => handleFloorClick(fl.floor_index)}
                                                    style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
                                                >
                                                    <span style={{ fontWeight: 700, fontSize: 12, color: isFlActive ? 'var(--accent-cyan)' : '#fff' }}>
                                                        {fl.floor_label}
                                                    </span>
                                                    <span style={{ fontSize: 10, color: 'var(--text-dim)' }}>
                                                        +{fl.elevation_base_m}m • {fl.units_count} Units
                                                    </span>
                                                </div>

                                                {isFlActive && (
                                                    <div style={{ marginTop: 10, borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: 8 }}>
                                                        <div style={{ fontSize: 10, color: 'var(--text-dim)', marginBottom: 6 }}>
                                                            SELECT UNIT TO INSPECT ULPIN:
                                                        </div>
                                                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                                                            {fl.units.map(u => {
                                                                const isUActive = (selectedFlat && selectedFlat.unit_id === u.unit_id);
                                                                return (
                                                                    <div
                                                                        key={u.unit_id}
                                                                        onClick={() => handleFlatClick(u)}
                                                                        style={{
                                                                            background: isUActive ? 'var(--accent-cyan)' : 'rgba(30, 41, 59, 0.8)',
                                                                            color: isUActive ? '#000' : '#fff',
                                                                            border: isUActive ? '1px solid #fff' : '1px solid rgba(255,255,255,0.05)',
                                                                            padding: '6px 8px', borderRadius: 6, cursor: 'pointer', transition: 'all 0.15s'
                                                                        }}
                                                                    >
                                                                        <div style={{ fontWeight: 800, fontSize: 11 }}>Flat {u.unit_number}</div>
                                                                        <div style={{ fontSize: 9, opacity: 0.8 }}>{u.carpet_area_sqm} m²</div>
                                                                    </div>
                                                                );
                                                            })}
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>

                            <div className="glass-panel" style={{
                                position: 'absolute', top: 96, right: 16, bottom: 24, width: 380,
                                display: 'flex', flexDirection: 'column', padding: 22, zIndex: 60,
                                pointerEvents: 'auto', overflowY: 'auto'
                            }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                                    <span style={{
                                        fontSize: 10, fontWeight: 800, padding: '3px 9px', borderRadius: 20,
                                        background: selectedFlat ? 'var(--accent-amber)' : 'var(--accent-cyan)',
                                        color: '#000'
                                    }}>
                                        {selectedFlat ? "VERTICAL UNIT 3D ULPIN" : "BUILDING BASE PARCEL"}
                                    </span>
                                    <span style={{ fontSize: 11, color: 'var(--accent-emerald)', display: 'flex', alignItems: 'center', gap: 4, fontWeight: 600 }}>
                                        <span className="pulsing-dot" style={{ width: 6, height: 6 }}></span> MahaBhumi Verified
                                    </span>
                                </div>

                                {selectedFlat ? (
                                    <React.Fragment>
                                        <h3 style={{ margin: '0 0 2px 0', fontSize: 18, color: '#fff' }}>
                                            Unit {selectedFlat.unit_number} ({selectedFlat.wing_name})
                                        </h3>
                                        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 16 }}>
                                            {selectedFlat.unit_type} • Level {selectedFlat.floor_number}
                                        </div>

                                        <div style={{
                                            background: 'rgba(0, 229, 255, 0.08)', border: '1px solid var(--accent-cyan)',
                                            borderRadius: 8, padding: 12, marginBottom: 16
                                        }}>
                                            <div style={{ fontSize: 10, color: 'var(--text-dim)', textTransform: 'uppercase' }}>3D VERTICAL ULPIN (BHU-AADHAAR)</div>
                                            <div className="code-font" style={{ fontSize: 13, fontWeight: 700, color: 'var(--accent-cyan)', margin: '4px 0' }}>
                                                {selectedFlat.unit_ulpin}
                                            </div>
                                            <div style={{ fontSize: 10, color: 'var(--text-secondary)' }}>
                                                Base Parcel: <span className="code-font" style={{ color: '#fff' }}>{cadastre.land_ulpin}</span>
                                            </div>
                                        </div>

                                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 16 }}>
                                            <div style={{ background: 'rgba(15,23,42,0.6)', padding: 10, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                                <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>RERA CARPET AREA</div>
                                                <div style={{ fontSize: 13, fontWeight: 700, color: '#fff' }}>
                                                    {selectedFlat.carpet_area_sqm} m²
                                                </div>
                                                <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>{selectedFlat.carpet_area_sqft} sq.ft</div>
                                            </div>
                                            <div style={{ background: 'rgba(15,23,42,0.6)', padding: 10, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                                <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>BUILT-UP AREA</div>
                                                <div style={{ fontSize: 13, fontWeight: 700, color: '#fff' }}>
                                                    {selectedFlat.built_up_area_sqm} m²
                                                </div>
                                                <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>Gross Enclosed</div>
                                            </div>
                                            <div style={{ background: 'rgba(15,23,42,0.6)', padding: 10, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                                <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>UDS (LAND SHARE)</div>
                                                <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--accent-amber)' }}>
                                                    {selectedFlat.uds_percentage}
                                                </div>
                                                <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>Undivided Share</div>
                                            </div>
                                            <div style={{ background: 'rgba(15,23,42,0.6)', padding: 10, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                                <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>ELEVATION (MSL)</div>
                                                <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--accent-cyan)' }}>
                                                    +{selectedFlat.elevation_base_m}m
                                                </div>
                                                <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>Base datum</div>
                                            </div>
                                        </div>

                                        <div style={{ background: 'rgba(15,23,42,0.7)', borderRadius: 8, padding: 12, border: '1px solid var(--border-subtle)', marginBottom: 16 }}>
                                            <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--accent-cyan)', marginBottom: 8, textTransform: 'uppercase' }}>
                                                Cadastral Ownership & Title
                                            </div>
                                            <div style={{ fontSize: 12, marginBottom: 6 }}>
                                                <span style={{ color: 'var(--text-dim)' }}>Titleholder: </span>
                                                <b style={{ color: '#fff' }}>{selectedFlat.owner_name}</b>
                                            </div>
                                            <div style={{ fontSize: 12, marginBottom: 6 }}>
                                                <span style={{ color: 'var(--text-dim)' }}>Property Card: </span>
                                                <span className="code-font" style={{ color: 'var(--accent-amber)' }}>{selectedFlat.property_card_no}</span>
                                            </div>
                                            <div style={{ fontSize: 12, marginBottom: 6 }}>
                                                <span style={{ color: 'var(--text-dim)' }}>CTS Survey No: </span>
                                                <span style={{ color: '#fff' }}>{selectedFlat.cts_no}</span>
                                            </div>
                                            <div style={{ fontSize: 12, marginBottom: 6 }}>
                                                <span style={{ color: 'var(--text-dim)' }}>Tax SAC Assessment: </span>
                                                <span className="code-font" style={{ color: '#fff' }}>{selectedFlat.tax_assessment_sac}</span>
                                            </div>
                                            <div style={{ fontSize: 12 }}>
                                                <span style={{ color: 'var(--text-dim)' }}>Title Status: </span>
                                                <span style={{ color: 'var(--accent-emerald)' }}>Freehold • Clear Title (MahaRERA Registered)</span>
                                            </div>
                                        </div>

                                        <button
                                            onClick={() => {
                                                navigator.clipboard.writeText(selectedFlat.unit_ulpin);
                                                alert(`Copied 3D ULPIN to Clipboard:\n${selectedFlat.unit_ulpin}`);
                                            }}
                                            style={{
                                                width: '100%', background: 'rgba(0, 229, 255, 0.15)', color: 'var(--accent-cyan)',
                                                border: '1px solid var(--accent-cyan)', padding: '10px', borderRadius: 8,
                                                fontWeight: 700, fontSize: 12, cursor: 'pointer', display: 'flex', alignItems: 'center',
                                                justifyContent: 'center', gap: 6, transition: 'all 0.2s'
                                            }}
                                        >
                                            📋 Copy 3D ULPIN Code
                                        </button>
                                    </React.Fragment>
                                ) : (
                                    <React.Fragment>
                                        <h3 style={{ margin: '0 0 4px 0', fontSize: 18, color: '#fff' }}>
                                            {cadastre.name}
                                        </h3>
                                        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 16 }}>
                                            {cadastre.street} • {cadastre.cadastral_division}
                                        </div>

                                        <div style={{
                                            background: 'rgba(0, 229, 255, 0.08)', border: '1px solid var(--accent-cyan)',
                                            borderRadius: 8, padding: 12, marginBottom: 16
                                        }}>
                                            <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>LAND PARCEL ULPIN (BHU-AADHAAR)</div>
                                            <div className="code-font" style={{ fontSize: 14, fontWeight: 700, color: 'var(--accent-cyan)', margin: '4px 0' }}>
                                                {cadastre.land_ulpin}
                                            </div>
                                            <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                                                Survey: <b>{cadastre.cts_no}</b>
                                            </div>
                                        </div>

                                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 16 }}>
                                            <div style={{ background: 'rgba(15,23,42,0.6)', padding: 10, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                                <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>TOTAL HEIGHT</div>
                                                <div style={{ fontSize: 13, fontWeight: 700, color: '#fff' }}>{cadastre.height_m} m</div>
                                                <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>{cadastre.floors_count} Storeys</div>
                                            </div>
                                            <div style={{ background: 'rgba(15,23,42,0.6)', padding: 10, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                                <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>VERTICAL UNITS</div>
                                                <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--accent-amber)' }}>{cadastre.total_units} Units</div>
                                                <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>{cadastre.wings.length} Wings</div>
                                            </div>
                                            <div style={{ background: 'rgba(15,23,42,0.6)', padding: 10, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                                <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>FOOTPRINT AREA</div>
                                                <div style={{ fontSize: 13, fontWeight: 700, color: '#fff' }}>{cadastre.footprint_area_sqm} m²</div>
                                            </div>
                                            <div style={{ background: 'rgba(15,23,42,0.6)', padding: 10, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                                <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>TYPICAL FLOOR PLATE</div>
                                                <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--accent-cyan)' }}>{cadastre.floor_plate_sqm} m²</div>
                                            </div>
                                        </div>

                                        <div style={{
                                            background: 'rgba(15,23,42,0.7)', borderRadius: 8, padding: 14,
                                            border: '1px solid var(--border-subtle)', textAlign: 'center', marginTop: 'auto'
                                        }}>
                                            <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--accent-cyan)', marginBottom: 4 }}>
                                                👉 Click Any Flat or Floor
                                            </div>
                                            <div style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                                                Click an individual unit or floor in 3D to isolate and inspect its specific 3D ULPIN, carpet area, titleholder, and registration records.
                                            </div>
                                        </div>
                                    </React.Fragment>
                                )}
                            </div>
                        </React.Fragment>
                    )}
                </div>
            );
        }

        ReactDOM.render(<App />, document.getElementById('react-root'));
    </script>
</body>
</html>
"""
    html_content = html_content.replace("__GOOGLE_3D_TILES_API_KEY__", google_key_literal)
    return HTMLResponse(content=html_content)

if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
