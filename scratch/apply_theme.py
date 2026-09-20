import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

with open(BASE_DIR / "app.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Replace the <style>...</style> block
old_style_match = re.search(r'<style>.*?</style>', content, re.DOTALL)
assert old_style_match is not None, "Could not find <style> block"

new_style = """<style>
        :root {
            --bg-main: #F4F6F8;
            --bg-card: #FFFFFF;
            --bg-card-hover: #F8FAFC;
            --primary-gov-blue: #155E95;
            --secondary-gov-blue: #2F7D95;
            --accent-cyan: #155E95;
            --accent-blue: #2F7D95;
            --accent-emerald: #16A34A;
            --accent-amber: #D97706;
            --border-subtle: #D9E1E8;
            --border-divider: #D9E1E8;
            --border-glow: rgba(21, 94, 149, 0.2);
            --text-primary: #1F2937;
            --text-secondary: #64748B;
            --text-dim: #94A3B8;
        }

        * { box-sizing: border-box; }
        body, html {
            margin: 0; padding: 0; width: 100%; height: 100%;
            font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
            background: #F4F6F8; color: #1F2937;
            overflow: hidden; user-select: none;
        }

        #map, #fallback-map { position: absolute; top: 0; bottom: 0; width: 100%; height: 100%; }
        #map { display: block; background: #F0F4F8; }
        #fallback-map { display: none; }
        .cesium-viewer { background: #F0F4F8; }

        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: #F1F5F9; }
        ::-webkit-scrollbar-thumb { background: #CBD5E1; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #94A3B8; }

        .glass-panel {
            background: #FFFFFF;
            border: 1px solid #D9E1E8;
            border-radius: 8px;
            box-shadow: 0 4px 16px rgba(15, 23, 42, 0.06);
        }

        .code-font {
            font-family: 'JetBrains Mono', monospace;
        }

        #viewport-tooltip {
            position: absolute; display: none; pointer-events: none; z-index: 50;
            background: #FFFFFF; border: 1px solid #D9E1E8;
            border-radius: 6px; padding: 8px 12px; font-size: 11px;
            box-shadow: 0 4px 16px rgba(15, 23, 42, 0.1);
            transform: translate(-50%, -120%); transition: opacity 0.15s;
            color: #1F2937;
        }

        #twin-workspace {
            position: absolute; top: 0; left: 0; width: 100vw; height: 100vh;
            background: #F4F6F8;
            z-index: 40; display: none; flex-direction: column;
        }

        #twin-canvas-container {
            flex: 1; width: 100%; height: 100%; position: relative; overflow: hidden;
            background: #EAF0F6;
        }

        .pulsing-dot {
            width: 8px; height: 8px; border-radius: 50%; background: #16A34A;
            box-shadow: 0 0 0 2px rgba(22, 163, 74, 0.2); animation: pulse 2.5s infinite;
        }
        @keyframes pulse {
            0% { transform: scale(0.95); opacity: 0.8; }
            50% { transform: scale(1.15); opacity: 1; }
            100% { transform: scale(0.95); opacity: 0.8; }
        }

        #react-root {
            position: absolute; top: 0; left: 0; width: 100%; height: 100%;
            pointer-events: none; z-index: 45;
        }
        #react-root > * {
            pointer-events: auto;
        }

        .ulpin-badge-popup .maplibregl-popup-content {
            background: transparent !important;
            box-shadow: none !important;
            padding: 0 !important;
            border: none !important;
        }
        .ulpin-badge-popup .maplibregl-popup-tip {
            border-top-color: #FFFFFF !important;
        }
    </style>"""

content = content[:old_style_match.start()] + new_style + content[old_style_match.end():]

# 2. Update Tooltip header styles in HTML body
content = content.replace(
    '<div id="tt-title" style="font-weight: 700; color: var(--accent-cyan); margin-bottom: 2px;"></div>',
    '<div id="tt-title" style="font-weight: 700; color: #155E95; margin-bottom: 2px;"></div>'
)
content = content.replace(
    '<div id="tt-sub" style="color: var(--text-secondary);"></div>',
    '<div id="tt-sub" style="color: #64748B;"></div>'
)
content = content.replace(
    '<div id="tt-ulpin" class="code-font" style="color: var(--accent-amber); font-size: 10px; margin-top: 4px;"></div>',
    '<div id="tt-ulpin" class="code-font" style="color: #2F7D95; font-size: 10px; margin-top: 4px; font-weight: 600;"></div>'
)

# 3. Update Three.js materials in ArchitecturalDigitalTwinRenderer
old_materials = """            initMaterials() {
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
            }"""

new_materials = """            initMaterials() {
                return {
                    slabConcrete: new THREE.MeshStandardMaterial({
                        color: 0x94a3b8, roughness: 0.75, metalness: 0.12
                    }),
                    slabEdge: new THREE.MeshStandardMaterial({
                        color: 0x64748b, roughness: 0.65, metalness: 0.2
                    }),
                    exteriorStone: new THREE.MeshStandardMaterial({
                        color: 0xf1f5f9, roughness: 0.85, metalness: 0.05
                    }),
                    exteriorAccent: new THREE.MeshStandardMaterial({
                        color: 0xcbd5e1, roughness: 0.7, metalness: 0.1
                    }),
                    windowGlass: new THREE.MeshPhysicalMaterial({
                        color: 0x93c5fd, roughness: 0.1, transmission: 0.78, opacity: 0.72,
                        transparent: true, reflectivity: 0.85, clearcoat: 0.8, clearcoatRoughness: 0.15
                    }),
                    windowGlassWarm: new THREE.MeshPhysicalMaterial({
                        color: 0x60a5fa, roughness: 0.12, transmission: 0.75, opacity: 0.75,
                        transparent: true, reflectivity: 0.82, clearcoat: 0.8
                    }),
                    aluminumFrame: new THREE.MeshStandardMaterial({
                        color: 0x475569, roughness: 0.45, metalness: 0.65
                    }),
                    balconyDeck: new THREE.MeshStandardMaterial({
                        color: 0xe2e8f0, roughness: 0.85, metalness: 0.08
                    }),
                    balconyGlassRailing: new THREE.MeshPhysicalMaterial({
                        color: 0xcbd5e1, roughness: 0.2, transmission: 0.85, opacity: 0.55,
                        transparent: true, reflectivity: 0.75
                    }),
                    metalRailing: new THREE.MeshStandardMaterial({
                        color: 0x64748b, roughness: 0.4, metalness: 0.7
                    }),
                    entranceDoor: new THREE.MeshPhysicalMaterial({
                        color: 0x155e95, roughness: 0.2, transmission: 0.75, opacity: 0.85,
                        transparent: true
                    }),
                    roofHVAC: new THREE.MeshStandardMaterial({
                        color: 0x94a3b8, roughness: 0.65, metalness: 0.45
                    }),
                    flatFloorSelected: new THREE.MeshStandardMaterial({
                        color: 0x155e95, emissive: 0x0d3b5e, emissiveIntensity: 0.35,
                        roughness: 0.4, metalness: 0.15
                    }),
                    ghostedMaterial: new THREE.MeshPhysicalMaterial({
                        color: 0xcbd5e1, roughness: 0.3, transmission: 0.85, opacity: 0.24,
                        transparent: true, reflectivity: 0.65
                    })
                };
            }"""

assert old_materials in content, "old_materials not found"
content = content.replace(old_materials, new_materials)

# 4. Update Three.js scene background, lighting, and ground
content = content.replace(
    "this.scene.background = new THREE.Color(0x060913);",
    "this.scene.background = new THREE.Color(0xeaf0f6);\n                this.scene.fog = new THREE.Fog(0xeaf0f6, 120, 900);"
)

content = content.replace(
    "this.renderer.toneMappingExposure = 1.15;",
    "this.renderer.toneMappingExposure = 1.0;"
)

old_lighting = """            setupLighting() {
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
            }"""

new_lighting = """            setupLighting() {
                const ambient = new THREE.AmbientLight(0xffffff, 0.85);
                this.scene.add(ambient);

                const hemiLight = new THREE.HemisphereLight(0xf8fafc, 0xcbd5e1, 0.85);
                hemiLight.position.set(0, 200, 0);
                this.scene.add(hemiLight);

                const sun = new THREE.DirectionalLight(0xfffdf5, 1.4);
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

                const rimLight = new THREE.DirectionalLight(0xdce7f5, 0.55);
                rimLight.position.set(-140, 90, -140);
                this.scene.add(rimLight);
            }"""

assert old_lighting in content, "old_lighting not found"
content = content.replace(old_lighting, new_lighting)

old_ground = """            setupGround() {
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
            }"""

new_ground = """            setupGround() {
                const gridHelper = new THREE.GridHelper(260, 52, 0xcbd5e1, 0xe2e8f0);
                gridHelper.position.y = -0.05;
                gridHelper.material.opacity = 0.65;
                gridHelper.material.transparent = true;
                this.scene.add(gridHelper);

                const groundGeo = new THREE.PlaneGeometry(320, 320);
                const groundMat = new THREE.MeshStandardMaterial({
                    color: 0xeef2f6, roughness: 0.95, metalness: 0.05
                });
                const ground = new THREE.Mesh(groundGeo, groundMat);
                ground.rotation.x = -Math.PI / 2;
                ground.position.y = -0.1;
                ground.receiveShadow = true;
                this.scene.add(ground);
            }"""

assert old_ground in content, "old_ground not found"
content = content.replace(old_ground, new_ground)

# 5. Replace cyan slab edge line and flat outlines in Three.js
content = content.replace(
    "color: 0x00e5ff, transparent: true, opacity: 0.45",
    "color: 0x155e95, transparent: true, opacity: 0.35"
)
content = content.replace(
    "color: 0x00e5ff, transparent: true, opacity: 0.0, linewidth: 2",
    "color: 0x155e95, transparent: true, opacity: 0.0, linewidth: 2"
)
content = content.replace(
    "color: 0x00e5ff, opacity: 0.8, transparent: true",
    "color: 0x155e95, opacity: 0.6, transparent: true"
)

# 6. Update Procedural architectural features in createProceduralBuildingFeatures
old_arch_palette = """            const slabColors = ['#374151', '#4b5563', '#334155'];
            const wallColors = ['#1e293b', '#243247', '#1a2434'];
            const windowColors = ['#1e3a5f', '#1b2f48', '#16283d'];"""

new_arch_palette = """            const slabColors = ['#94a3b8', '#64748b', '#94a3b8'];
            const wallColors = ['#f1f5f9', '#e2e8f0', '#f8fafc'];
            const windowColors = ['#93c5fd', '#bfdbfe', '#93c5fd'];"""

assert old_arch_palette in content, "old_arch_palette not found"
content = content.replace(old_arch_palette, new_arch_palette)
content = content.replace("color: '#64748b',\\n                    tier: 'parapet',", "color: '#cbd5e1',\\n                    tier: 'parapet',")

# 7. Update Cesium Viewer styling
content = content.replace(
    "viewer.scene.highDynamicRange = true;",
    "viewer.scene.highDynamicRange = true;\n            viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString('#E2E8F0');\n            viewer.scene.backgroundColor = Cesium.Color.fromCssColorString('#F0F4F8');\n            if (viewer.scene.fog) { viewer.scene.fog.enabled = true; viewer.scene.fog.density = 0.00015; }"
)

# Cesium parcel boundary lines and fill
content = content.replace(
    "material: Cesium.Color.fromCssColorString('rgba(56, 189, 248, 0.04)'),\\n                        classificationType: Cesium.ClassificationType.CESIUM_3D_TILE",
    "material: Cesium.Color.fromCssColorString('rgba(21, 94, 149, 0.05)'),\\n                        classificationType: Cesium.ClassificationType.CESIUM_3D_TILE"
)
content = content.replace(
    "material: Cesium.Color.fromCssColorString('rgba(56, 189, 248, 0.65)'),\\n                        clampToGround: true,",
    "material: Cesium.Color.fromCssColorString('rgba(21, 94, 149, 0.65)'),\\n                        clampToGround: true,"
)

# Cesium highlightBuilding
content = content.replace(
    "material: Cesium.Color.fromCssColorString('rgba(245, 158, 11, 0.28)'),",
    "material: Cesium.Color.fromCssColorString('rgba(21, 94, 149, 0.15)'),"
)
content = content.replace(
    "material: Cesium.Color.fromCssColorString('#f59e0b'),\\n                        clampToGround: true,",
    "material: Cesium.Color.fromCssColorString('#155E95'),\\n                        clampToGround: true,"
)
content = content.replace(
    "outlineColor: Cesium.Color.fromCssColorString('#f59e0b')",
    "outlineColor: Cesium.Color.fromCssColorString('#155E95')"
)
content = content.replace(
    "backgroundColor: Cesium.Color.fromCssColorString('rgba(13, 20, 36, 0.92)'),",
    "backgroundColor: Cesium.Color.fromCssColorString('rgba(255, 255, 255, 0.95)'),\\n                        fillColor: Cesium.Color.fromCssColorString('#1F2937'),\\n                        outlineColor: Cesium.Color.fromCssColorString('#E2E8F0'),"
)

# 8. Update MapLibre Viewer styling
content = content.replace(
    "paint: { 'line-color': '#00e5ff', 'line-width': 5, 'line-dasharray': [2, 1.5] }",
    "paint: { 'line-color': '#155E95', 'line-width': 4.5, 'line-dasharray': [2, 1.5] }"
)
content = content.replace(
    "paint: { 'line-color': '#ff3b30', 'line-width': 4.5, 'line-opacity': 0.85 }",
    "paint: { 'line-color': '#D97706', 'line-width': 3.5, 'line-opacity': 0.85 }"
)
content = content.replace(
    "'fill-color': '#38bdf8',",
    "'fill-color': '#155E95',"
)
content = content.replace(
    "'line-color': 'rgba(56, 189, 248, 0.65)',",
    "'line-color': 'rgba(21, 94, 149, 0.65)',"
)
content = content.replace(
    "'fill-color': '#f59e0b',\\n                        'fill-opacity': 0.25",
    "'fill-color': 'rgba(21, 94, 149, 0.15)',\\n                        'fill-opacity': 0.8"
)
content = content.replace(
    "'line-color': '#f59e0b',\\n                        'line-width': 3.5",
    "'line-color': '#155E95',\\n                        'line-width': 3.0"
)

# MapLibre popup styling
old_popup_html = """                        <div style="font-family: 'Plus Jakarta Sans', sans-serif; background: rgba(13, 20, 36, 0.95); border: 1px solid #f59e0b; border-radius: 8px; padding: 6px 10px; color: #fff; box-shadow: 0 4px 20px rgba(0,0,0,0.6);">
                            <div style="font-size: 11px; font-weight: 700; color: #f59e0b;">${p.name || 'Selected Property'}</div>
                            <div style="font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #00e5ff; margin-top: 2px;">ULPIN: ${p.land_ulpin || ''}</div>
                            <div style="font-size: 9px; color: #94a3b8; margin-top: 2px;">${p.height_m || 0}m • ${p.floors || 1} Storeys</div>
                        </div>"""

new_popup_html = """                        <div style="font-family: 'Plus Jakarta Sans', sans-serif; background: #FFFFFF; border: 1px solid #D9E1E8; border-radius: 6px; padding: 8px 12px; color: #1F2937; box-shadow: 0 4px 16px rgba(15, 23, 42, 0.1);">
                            <div style="font-size: 11px; font-weight: 700; color: #155E95;">${p.name || 'Selected Property'}</div>
                            <div style="font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #2F7D95; margin-top: 2px; font-weight: 600;">ULPIN: ${p.land_ulpin || ''}</div>
                            <div style="font-size: 9px; color: #64748B; margin-top: 2px;">${p.height_m || 0}m • ${p.floors || 1} Storeys</div>
                        </div>"""

assert old_popup_html in content, "old_popup_html not found"
content = content.replace(old_popup_html, new_popup_html)

# Fallback initMapLibre layer colors
content = content.replace(
    "paint: { 'line-color': '#00e5ff', 'line-width': 6, 'line-dasharray': [2, 1.5] }",
    "paint: { 'line-color': '#155E95', 'line-width': 4.5, 'line-dasharray': [2, 1.5] }"
)
content = content.replace(
    "paint: { 'line-color': '#ff3b30', 'line-width': 5.5, 'line-opacity': 0.9 }",
    "paint: { 'line-color': '#D97706', 'line-width': 3.5, 'line-opacity': 0.85 }"
)
content = content.replace(
    """                            'fill-extrusion-color': [
                                'interpolate', ['linear'], ['get', 'height_m'],
                                0, '#0284c7',
                                25, '#00e5ff',
                                55, '#38bdf8',
                                85, '#818cf8',
                                120, '#c084fc'
                            ],
                            'fill-extrusion-height': ['get', 'height_m'],
                            'fill-extrusion-base': 0,
                            'fill-extrusion-opacity': 0.92""",
    """                            'fill-extrusion-color': [
                                'interpolate', ['linear'], ['get', 'height_m'],
                                0, '#CBD5E1',
                                25, '#94A3B8',
                                55, '#64748B',
                                85, '#2F7D95',
                                120, '#155E95'
                            ],
                            'fill-extrusion-height': ['get', 'height_m'],
                            'fill-extrusion-base': 0,
                            'fill-extrusion-opacity': 0.85"""
)

# 9. Update React JSX UI styling
# Top navigation bar
content = content.replace(
    "width: 38, height: 38, borderRadius: 8, background: 'linear-gradient(135deg, #00e5ff 0%, #3b82f6 100%)',\\n                                display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, boxShadow: '0 0 16px rgba(0,229,255,0.5)'",
    "width: 38, height: 38, borderRadius: 6, background: '#155E95',\\n                                display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, boxShadow: '0 2px 6px rgba(21, 94, 149, 0.25)'"
)
content = content.replace(
    "<div style={{ fontWeight: 800, fontSize: 16, letterSpacing: '0.02em', color: '#fff', display: 'flex', alignItems: 'center', gap: 8 }}>",
    "<div style={{ fontWeight: 800, fontSize: 15, letterSpacing: '0.02em', color: '#1F2937', display: 'flex', alignItems: 'center', gap: 8 }}>"
)
content = content.replace(
    "<span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 20, background: 'rgba(0,229,255,0.15)', color: 'var(--accent-cyan)', border: '1px solid var(--accent-cyan)' }}>",
    "<span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 6, background: '#F1F5F9', color: '#155E95', border: '1px solid #D9E1E8', fontWeight: 700 }}>"
)
content = content.replace(
    "<b style={{ color: '#fff' }}>{cadastre.name}</b>",
    "<b style={{ color: '#1F2937' }}>{cadastre.name}</b>"
)
content = content.replace(
    "width: '100%', background: 'rgba(15, 23, 42, 0.8)', border: '1px solid var(--border-subtle)',\\n                                    borderRadius: 8, padding: '8px 14px', color: '#fff', fontSize: 12, outline: 'none'",
    "width: '100%', background: '#F8FAFC', border: '1px solid #D9E1E8',\\n                                    borderRadius: 6, padding: '8px 14px', color: '#1F2937', fontSize: 12, outline: 'none'"
)
content = content.replace(
    "marginBottom: 4, background: 'rgba(30, 41, 59, 0.5)', transition: 'background 0.15s'",
    "marginBottom: 4, background: '#F8FAFC', border: '1px solid #E2E8F0', transition: 'background 0.15s'"
)
content = content.replace(
    "onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(0, 229, 255, 0.2)'}\\n                                            onMouseLeave={(e) => e.currentTarget.style.background = 'rgba(30, 41, 59, 0.5)'}",
    "onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(21, 94, 149, 0.08)'}\\n                                            onMouseLeave={(e) => e.currentTarget.style.background = '#F8FAFC'}"
)
content = content.replace(
    "<div style={{ fontWeight: 700, color: 'var(--accent-cyan)' }}>{b.properties.name}</div>",
    "<div style={{ fontWeight: 700, color: '#155E95' }}>{b.properties.name}</div>"
)

# Twin camera preset buttons container
content = content.replace(
    "<div style={{ display: 'flex', background: 'rgba(15,23,42,0.8)', borderRadius: 8, padding: 3, border: '1px solid var(--border-subtle)' }}>",
    "<div style={{ display: 'flex', background: '#F8FAFC', borderRadius: 6, padding: 3, border: '1px solid #D9E1E8' }}>"
)
content = content.replace(
    "background: twinPreset === 'iso' ? 'var(--accent-cyan)' : 'transparent',\\n                                            color: twinPreset === 'iso' ? '#000' : 'var(--text-secondary)',",
    "background: twinPreset === 'iso' ? '#155E95' : 'transparent',\\n                                            color: twinPreset === 'iso' ? '#FFFFFF' : '#64748B',"
)
content = content.replace(
    "background: twinPreset === 'elevation' ? 'var(--accent-cyan)' : 'transparent',\\n                                            color: twinPreset === 'elevation' ? '#000' : 'var(--text-secondary)',",
    "background: twinPreset === 'elevation' ? '#155E95' : 'transparent',\\n                                            color: twinPreset === 'elevation' ? '#FFFFFF' : '#64748B',"
)
content = content.replace(
    "background: twinPreset === 'plan' ? 'var(--accent-cyan)' : 'transparent',\\n                                            color: twinPreset === 'plan' ? '#000' : 'var(--text-secondary)',",
    "background: twinPreset === 'plan' ? '#155E95' : 'transparent',\\n                                            color: twinPreset === 'plan' ? '#FFFFFF' : '#64748B',"
)
content = content.replace(
    "background: 'rgba(239, 68, 68, 0.2)', color: '#fca5a5', border: '1px solid rgba(239, 68, 68, 0.4)',\\n                                        padding: '8px 16px', borderRadius: 8, fontWeight: 700, fontSize: 12, cursor: 'pointer', transition: 'all 0.2s'",
    "background: '#FEF2F2', color: '#B91C1C', border: '1px solid #FECACA',\\n                                        padding: '7px 14px', borderRadius: 6, fontWeight: 700, fontSize: 12, cursor: 'pointer', transition: 'all 0.15s'"
)
content = content.replace(
    "onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(239, 68, 68, 0.4)'}\\n                                    onMouseLeave={(e) => e.currentTarget.style.background = 'rgba(239, 68, 68, 0.2)'}",
    "onMouseEnter={(e) => e.currentTarget.style.background = '#FEE2E2'}\\n                                    onMouseLeave={(e) => e.currentTarget.style.background = '#FEF2F2'}"
)

# Preset buttons (3D View, 2D Plan)
content = content.replace(
    "background: 'rgba(15,23,42,0.8)', color: 'var(--text-secondary)',\\n                                            border: '1px solid var(--border-subtle)', padding: '6px 12px', borderRadius: 6,",
    "background: '#F8FAFC', color: '#1F2937',\\n                                            border: '1px solid #D9E1E8', padding: '6px 12px', borderRadius: 6,"
)
content = content.replace(
    "onMouseEnter={(e) => e.currentTarget.style.color = '#fff'}\\n                                        onMouseLeave={(e) => e.currentTarget.style.color = 'var(--text-secondary)'}",
    "onMouseEnter={(e) => e.currentTarget.style.background = '#F1F5F9'}\\n                                        onMouseLeave={(e) => e.currentTarget.style.background = '#F8FAFC'}"
)

# Map view bottom-right selected building card
content = content.replace(
    "fontSize: 10, fontWeight: 800, padding: '3px 9px', borderRadius: 20,\\n                                    background: 'var(--accent-cyan)', color: '#000'",
    "fontSize: 10, fontWeight: 800, padding: '3px 9px', borderRadius: 6,\\n                                    background: '#EAF0F6', color: '#155E95', border: '1px solid #D9E1E8'"
)
content = content.replace(
    "<h3 style={{ margin: '12px 0 4px 0', fontSize: 17, color: '#fff' }}>",
    "<h3 style={{ margin: '12px 0 4px 0', fontSize: 17, color: '#1F2937' }}>"
)
content = content.replace(
    "<div style={{ background: 'rgba(15,23,42,0.6)', padding: 8, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>",
    "<div style={{ background: '#F8FAFC', padding: 8, borderRadius: 6, border: '1px solid #D9E1E8' }}>"
)
content = content.replace(
    "<div className=\"code-font\" style={{ fontSize: 12, fontWeight: 700, color: 'var(--accent-amber)' }}>",
    "<div className=\"code-font\" style={{ fontSize: 12, fontWeight: 700, color: '#155E95' }}>"
)
content = content.replace(
    "<div style={{ fontSize: 12, fontWeight: 700, color: 'var(--accent-cyan)' }}>",
    "<div style={{ fontSize: 12, fontWeight: 700, color: '#1F2937' }}>"
)
content = content.replace(
    "<div style={{ fontSize: 12, fontWeight: 700, color: '#fff' }}>",
    "<div style={{ fontSize: 12, fontWeight: 700, color: '#1F2937' }}>"
)
content = content.replace(
    "width: '100%', background: 'linear-gradient(135deg, #00e5ff 0%, #0284c7 100%)',\\n                                    color: '#000', border: 'none', padding: '12px', borderRadius: 8, fontWeight: 800,\\n                                    fontSize: 13, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',\\n                                    gap: 8, boxShadow: '0 0 20px rgba(0,229,255,0.4)', transition: 'all 0.2s'",
    "width: '100%', background: '#155E95',\\n                                    color: '#FFFFFF', border: 'none', padding: '11px', borderRadius: 6, fontWeight: 700,\\n                                    fontSize: 13, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',\\n                                    gap: 8, boxShadow: '0 2px 8px rgba(21, 94, 149, 0.25)', transition: 'all 0.15s'"
)

# Twin view left panel
content = content.replace(
    "<span style={{ color: 'var(--accent-cyan)' }}>South Mumbai</span>",
    "<span style={{ color: '#155E95' }}>South Mumbai</span>"
)
content = content.replace(
    "<b style={{ color: '#fff' }}>Floor {selectedFloor !== null ? selectedFloor + 1 : 'All'}</b>",
    "<b style={{ color: '#1F2937' }}>Floor {selectedFloor !== null ? selectedFloor + 1 : 'All'}</b>"
)
content = content.replace(
    "{selectedFlat && <span style={{ color: 'var(--accent-amber)' }}>› Flat {selectedFlat.unit_number}</span>}",
    "{selectedFlat && <span style={{ color: '#155E95', fontWeight: 700 }}>› Flat {selectedFlat.unit_number}</span>}"
)
content = content.replace(
    "background: 'rgba(15,23,42,0.7)', borderRadius: 10, padding: 14,\\n                                    border: '1px solid var(--border-subtle)', marginBottom: 16",
    "background: '#F8FAFC', borderRadius: 6, padding: 14,\\n                                    border: '1px solid #D9E1E8', marginBottom: 16"
)
content = content.replace(
    "<span style={{ color: 'var(--accent-cyan)' }}>💥 Explode Floors</span>",
    "<span style={{ color: '#155E95' }}>💥 Explode Floors</span>"
)
content = content.replace(
    "<span className=\"code-font\" style={{ color: '#fff' }}>{Math.round(explodeRatio * 100)}%</span>",
    "<span className=\"code-font\" style={{ color: '#1F2937' }}>{Math.round(explodeRatio * 100)}%</span>"
)
content = content.replace(
    "style={{ width: '100%', accentColor: 'var(--accent-cyan)', cursor: 'pointer' }}",
    "style={{ width: '100%', accentColor: '#155E95', cursor: 'pointer' }}"
)
content = content.replace(
    "style={{ background: 'none', border: '1px solid rgba(255,255,255,0.1)', color: 'var(--text-dim)', padding: '3px 8px', borderRadius: 4, fontSize: 10, cursor: 'pointer' }}",
    "style={{ background: '#FFFFFF', border: '1px solid #D9E1E8', color: '#64748B', padding: '3px 8px', borderRadius: 4, fontSize: 10, cursor: 'pointer' }}"
)

# Wing buttons in Twin view
content = content.replace(
    "background: selectedWing === 'all' ? 'var(--accent-cyan)' : 'rgba(15,23,42,0.8)',\\n                                            color: selectedWing === 'all' ? '#000' : 'var(--text-secondary)',\\n                                            border: '1px solid var(--border-subtle)', cursor: 'pointer'",
    "background: selectedWing === 'all' ? '#155E95' : '#F8FAFC',\\n                                            color: selectedWing === 'all' ? '#FFFFFF' : '#64748B',\\n                                            border: selectedWing === 'all' ? '1px solid #155E95' : '1px solid #D9E1E8', cursor: 'pointer'"
)
content = content.replace(
    "background: selectedWing === w.wing_id ? 'var(--accent-cyan)' : 'rgba(15,23,42,0.8)',\\n                                                color: selectedWing === w.wing_id ? '#000' : 'var(--text-secondary)',\\n                                                border: '1px solid var(--border-subtle)', cursor: 'pointer'",
    "background: selectedWing === w.wing_id ? '#155E95' : '#F8FAFC',\\n                                                color: selectedWing === w.wing_id ? '#FFFFFF' : '#64748B',\\n                                                border: selectedWing === w.wing_id ? '1px solid #155E95' : '1px solid #D9E1E8', cursor: 'pointer'"
)
content = content.replace(
    "color: 'var(--accent-cyan)', fontSize: 11, cursor: 'pointer', fontWeight: 600",
    "color: '#155E95', fontSize: 11, cursor: 'pointer', fontWeight: 700"
)

# Floor cards in Twin view
content = content.replace(
    "background: isFlActive ? 'rgba(0, 229, 255, 0.12)' : 'rgba(15, 23, 42, 0.6)',\\n                                                    border: isFlActive ? '1px solid var(--accent-cyan)' : '1px solid var(--border-subtle)',\\n                                                    borderRadius: 8, padding: 10, marginBottom: 8, transition: 'all 0.15s'",
    "background: isFlActive ? 'rgba(21, 94, 149, 0.08)' : '#F8FAFC',\\n                                                    border: isFlActive ? '1px solid #155E95' : '1px solid #D9E1E8',\\n                                                    borderRadius: 6, padding: 10, marginBottom: 8, transition: 'all 0.15s'"
)
content = content.replace(
    "color: isFlActive ? 'var(--accent-cyan)' : '#fff'",
    "color: isFlActive ? '#155E95' : '#1F2937'"
)
content = content.replace(
    "borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: 8",
    "borderTop: '1px solid #D9E1E8', paddingTop: 8"
)

# Flat cards in Twin view floor
content = content.replace(
    "background: isUActive ? 'var(--accent-cyan)' : 'rgba(30, 41, 59, 0.8)',\\n                                                                            color: isUActive ? '#000' : '#fff',\\n                                                                            border: isUActive ? '1px solid #fff' : '1px solid rgba(255,255,255,0.05)',\\n                                                                            padding: '6px 8px', borderRadius: 6, cursor: 'pointer', transition: 'all 0.15s'",
    "background: isUActive ? '#155E95' : '#FFFFFF',\\n                                                                            color: isUActive ? '#FFFFFF' : '#1F2937',\\n                                                                            border: isUActive ? '1px solid #155E95' : '1px solid #D9E1E8',\\n                                                                            padding: '6px 8px', borderRadius: 4, cursor: 'pointer', transition: 'all 0.15s'"
)

# Right Cadastral Title Panel in Twin view
content = content.replace(
    "background: selectedFlat ? 'var(--accent-amber)' : 'var(--accent-cyan)',\\n                                        color: '#000'",
    "background: '#EAF0F6',\\n                                        color: '#155E95', border: '1px solid #D9E1E8'"
)
content = content.replace(
    "color: 'var(--accent-emerald)', display: 'flex', alignItems: 'center', gap: 4, fontWeight: 600",
    "color: '#15803D', display: 'flex', alignItems: 'center', gap: 4, fontWeight: 700"
)
content = content.replace(
    "<h3 style={{ margin: '0 0 2px 0', fontSize: 18, color: '#fff' }}>",
    "<h3 style={{ margin: '0 0 2px 0', fontSize: 18, color: '#1F2937' }}>"
)
content = content.replace(
    "background: 'rgba(0, 229, 255, 0.08)', border: '1px solid var(--accent-cyan)',\\n                                            borderRadius: 8, padding: 12, marginBottom: 16",
    "background: '#F0F7FF', border: '1px solid rgba(21, 94, 149, 0.25)',\\n                                            borderRadius: 6, padding: 12, marginBottom: 16"
)
content = content.replace(
    "<div className=\"code-font\" style={{ fontSize: 13, fontWeight: 700, color: 'var(--accent-cyan)', margin: '4px 0' }}>",
    "<div className=\"code-font\" style={{ fontSize: 13, fontWeight: 700, color: '#155E95', margin: '4px 0' }}>"
)
content = content.replace(
    "Base Parcel: <span className=\"code-font\" style={{ color: '#fff' }}>{cadastre.land_ulpin}</span>",
    "Base Parcel: <span className=\"code-font\" style={{ color: '#1F2937' }}>{cadastre.land_ulpin}</span>"
)
content = content.replace(
    "<div style={{ background: 'rgba(15,23,42,0.6)', padding: 10, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>",
    "<div style={{ background: '#F8FAFC', padding: 10, borderRadius: 6, border: '1px solid #D9E1E8' }}>"
)
content = content.replace(
    "<div style={{ fontSize: 13, fontWeight: 700, color: '#fff' }}>",
    "<div style={{ fontSize: 13, fontWeight: 700, color: '#1F2937' }}>"
)
content = content.replace(
    "<div style={{ fontSize: 13, fontWeight: 700, color: 'var(--accent-amber)' }}>",
    "<div style={{ fontSize: 13, fontWeight: 700, color: '#D97706' }}>"
)
content = content.replace(
    "<div style={{ fontSize: 13, fontWeight: 700, color: 'var(--accent-cyan)' }}>",
    "<div style={{ fontSize: 13, fontWeight: 700, color: '#155E95' }}>"
)
content = content.replace(
    "background: 'rgba(15,23,42,0.7)', borderRadius: 8, padding: 12, border: '1px solid var(--border-subtle)', marginBottom: 16",
    "background: '#F8FAFC', borderRadius: 6, padding: 12, border: '1px solid #D9E1E8', marginBottom: 16"
)
content = content.replace(
    "<div style={{ fontSize: 11, fontWeight: 700, color: 'var(--accent-cyan)', marginBottom: 8, textTransform: 'uppercase' }}>",
    "<div style={{ fontSize: 11, fontWeight: 700, color: '#155E95', marginBottom: 8, textTransform: 'uppercase' }}>"
)
content = content.replace(
    "<b style={{ color: '#fff' }}>{selectedFlat.owner_name}</b>",
    "<b style={{ color: '#1F2937' }}>{selectedFlat.owner_name}</b>"
)
content = content.replace(
    "<span className=\"code-font\" style={{ color: 'var(--accent-amber)' }}>{selectedFlat.property_card_no}</span>",
    "<span className=\"code-font\" style={{ color: '#2F7D95', fontWeight: 600 }}>{selectedFlat.property_card_no}</span>"
)
content = content.replace(
    "<span style={{ color: '#fff' }}>{selectedFlat.cts_no}</span>",
    "<span style={{ color: '#1F2937' }}>{selectedFlat.cts_no}</span>"
)
content = content.replace(
    "<span className=\"code-font\" style={{ color: '#fff' }}>{selectedFlat.tax_assessment_sac}</span>",
    "<span className=\"code-font\" style={{ color: '#1F2937' }}>{selectedFlat.tax_assessment_sac}</span>"
)
content = content.replace(
    "<span style={{ color: 'var(--accent-emerald)' }}>Freehold • Clear Title (MahaRERA Registered)</span>",
    "<span style={{ color: '#15803D', fontWeight: 600 }}>Freehold • Clear Title (MahaRERA Registered)</span>"
)
content = content.replace(
    "width: '100%', background: 'rgba(0, 229, 255, 0.15)', color: 'var(--accent-cyan)',\\n                                                border: '1px solid var(--accent-cyan)', padding: '10px', borderRadius: 8,",
    "width: '100%', background: '#155E95', color: '#FFFFFF',\\n                                                border: 'none', padding: '10px', borderRadius: 6, boxShadow: '0 2px 6px rgba(21,94,149,0.25)',"
)

# Building level panel in Twin view (when flat is not selected)
content = content.replace(
    "<h3 style={{ margin: '0 0 4px 0', fontSize: 18, color: '#fff' }}>",
    "<h3 style={{ margin: '0 0 4px 0', fontSize: 18, color: '#1F2937' }}>"
)
content = content.replace(
    "<div className=\"code-font\" style={{ fontSize: 14, fontWeight: 700, color: 'var(--accent-cyan)', margin: '4px 0' }}>",
    "<div className=\"code-font\" style={{ fontSize: 14, fontWeight: 700, color: '#155E95', margin: '4px 0' }}>"
)
content = content.replace(
    "Survey: <b>{cadastre.cts_no}</b>",
    "Survey: <b style={{ color: '#1F2937' }}>{cadastre.cts_no}</b>"
)
content = content.replace(
    "background: 'rgba(15,23,42,0.7)', borderRadius: 8, padding: 14,\\n                                            border: '1px solid var(--border-subtle)', textAlign: 'center', marginTop: 'auto'",
    "background: '#F8FAFC', borderRadius: 6, padding: 14,\\n                                            border: '1px solid #D9E1E8', textAlign: 'center', marginTop: 'auto'"
)
content = content.replace(
    "<div style={{ fontSize: 13, fontWeight: 700, color: 'var(--accent-cyan)', marginBottom: 4 }}>",
    "<div style={{ fontSize: 13, fontWeight: 700, color: '#155E95', marginBottom: 4 }}>"
)

with open(BASE_DIR / "app.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Theme successfully updated in app.py!")

