import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
app_path = BASE_DIR / "app.py"

with open(app_path, "r", encoding="utf-8") as f:
    content = f.read()

# Fix Cesium Label line 1262 syntax error
content = content.replace(
    "backgroundColor: Cesium.Color.fromCssColorString('rgba(255, 255, 255, 0.95)'),\\n                        fillColor: Cesium.Color.fromCssColorString('#1F2937'),\\n                        outlineColor: Cesium.Color.fromCssColorString('#E2E8F0'),",
    """backgroundColor: Cesium.Color.fromCssColorString('rgba(255, 255, 255, 0.95)'),
                        fillColor: Cesium.Color.fromCssColorString('#1F2937'),
                        outlineColor: Cesium.Color.fromCssColorString('#E2E8F0'),"""
)

# Fix Cesium procedural architectural building colors
content = content.replace(
    "const slabColors = ['#374151', '#4b5563', '#334155'];\n                const wallColors = ['#1e293b', '#243247', '#1a2434'];\n                const windowColors = ['#1e3a5f', '#1b2f48', '#16283d'];",
    "const slabColors = ['#94A3B8', '#CBD5E1', '#64748B'];\n                const wallColors = ['#F1F5F9', '#E2E8F0', '#CBD5E1'];\n                const windowColors = ['#93C5FD', '#60A5FA', '#3B82F6'];"
)

# Fix Cesium parcel polylines to government blue
content = content.replace(
    "material: Cesium.Color.fromCssColorString('rgba(56, 189, 248, 0.04)'),",
    "material: Cesium.Color.fromCssColorString('rgba(21, 94, 149, 0.04)'),"
)
content = content.replace(
    "material: Cesium.Color.fromCssColorString('rgba(56, 189, 248, 0.65)'),",
    "material: Cesium.Color.fromCssColorString('rgba(21, 94, 149, 0.65)'),"
)
content = content.replace(
    "material: Cesium.Color.fromCssColorString('#f59e0b'),\n                        clampToGround: true,",
    "material: Cesium.Color.fromCssColorString('#155E95'),\n                        clampToGround: true,"
)

# Header Logo Icon
content = content.replace(
    """                            <div style={{
                                width: 38, height: 38, borderRadius: 8, background: 'linear-gradient(135deg, #00e5ff 0%, #3b82f6 100%)',
                                display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, boxShadow: '0 0 16px rgba(0,229,255,0.5)'
                            }}>""",
    """                            <div style={{
                                width: 38, height: 38, borderRadius: 6, background: 'linear-gradient(135deg, #155E95 0%, #2F7D95 100%)',
                                display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, boxShadow: '0 2px 6px rgba(21, 94, 149, 0.25)'
                            }}>"""
)

# Header Search Input
content = content.replace(
    """                            <input
                                type="text"
                                value={searchQuery}
                                onChange={(e) => handleSearch(e.target.value)}
                                placeholder="🔍 Search by ULPIN, Building or Street..."
                                style={{
                                    width: '100%', background: 'rgba(15, 23, 42, 0.8)', border: '1px solid var(--border-subtle)',
                                    borderRadius: 8, padding: '8px 14px', color: '#fff', fontSize: 12, outline: 'none'
                                }}
                            />""",
    """                            <input
                                type="text"
                                value={searchQuery}
                                onChange={(e) => handleSearch(e.target.value)}
                                placeholder="🔍 Search by ULPIN, Building or Street..."
                                style={{
                                    width: '100%', background: '#F8FAFC', border: '1px solid #D9E1E8',
                                    borderRadius: 6, padding: '8px 14px', color: '#1F2937', fontSize: 12, outline: 'none'
                                }}
                            />"""
)

# Search hover styles
content = content.replace(
    "onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(0, 229, 255, 0.2)'}\n                                            onMouseLeave={(e) => e.currentTarget.style.background = 'rgba(30, 41, 59, 0.5)'}",
    "onMouseEnter={(e) => e.currentTarget.style.background = '#EDF5FB'}\n                                            onMouseLeave={(e) => e.currentTarget.style.background = '#F8FAFC'}"
)

# Preset buttons
content = content.replace(
    """                                    <button
                                        onClick={() => handleCameraPreset('iso')}
                                        style={{
                                            background: twinPreset === 'iso' ? 'var(--accent-cyan)' : 'transparent',
                                            color: twinPreset === 'iso' ? '#000' : 'var(--text-secondary)',
                                            border: 'none', padding: '6px 12px', borderRadius: 6, fontSize: 11, fontWeight: 700, cursor: 'pointer'
                                        }}
                                    >""",
    """                                    <button
                                        onClick={() => handleCameraPreset('iso')}
                                        style={{
                                            background: twinPreset === 'iso' ? '#155E95' : 'transparent',
                                            color: twinPreset === 'iso' ? '#FFFFFF' : '#64748B',
                                            border: 'none', padding: '6px 12px', borderRadius: 6, fontSize: 11, fontWeight: 700, cursor: 'pointer'
                                        }}
                                    >"""
)

content = content.replace(
    """                                    <button
                                        onClick={() => handleCameraPreset('elevation')}
                                        style={{
                                            background: twinPreset === 'elevation' ? 'var(--accent-cyan)' : 'transparent',
                                            color: twinPreset === 'elevation' ? '#000' : 'var(--text-secondary)',
                                            border: 'none', padding: '6px 12px', borderRadius: 6, fontSize: 11, fontWeight: 700, cursor: 'pointer'
                                        }}
                                    >""",
    """                                    <button
                                        onClick={() => handleCameraPreset('elevation')}
                                        style={{
                                            background: twinPreset === 'elevation' ? '#155E95' : 'transparent',
                                            color: twinPreset === 'elevation' ? '#FFFFFF' : '#64748B',
                                            border: 'none', padding: '6px 12px', borderRadius: 6, fontSize: 11, fontWeight: 700, cursor: 'pointer'
                                        }}
                                    >"""
)

content = content.replace(
    """                                    <button
                                        onClick={() => handleCameraPreset('plan')}
                                        style={{
                                            background: twinPreset === 'plan' ? 'var(--accent-cyan)' : 'transparent',
                                            color: twinPreset === 'plan' ? '#000' : 'var(--text-secondary)',
                                            border: 'none', padding: '6px 12px', borderRadius: 6, fontSize: 11, fontWeight: 700, cursor: 'pointer'
                                        }}
                                    >""",
    """                                    <button
                                        onClick={() => handleCameraPreset('plan')}
                                        style={{
                                            background: twinPreset === 'plan' ? '#155E95' : 'transparent',
                                            color: twinPreset === 'plan' ? '#FFFFFF' : '#64748B',
                                            border: 'none', padding: '6px 12px', borderRadius: 6, fontSize: 11, fontWeight: 700, cursor: 'pointer'
                                        }}
                                    >"""
)

# Exit Twin button
content = content.replace(
    """                                <button
                                    onClick={handleCloseTwin}
                                    style={{
                                        background: 'rgba(239, 68, 68, 0.2)', color: '#fca5a5', border: '1px solid rgba(239, 68, 68, 0.4)',
                                        padding: '8px 16px', borderRadius: 8, fontWeight: 700, fontSize: 12, cursor: 'pointer', transition: 'all 0.2s'
                                    }}
                                    onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(239, 68, 68, 0.4)'}
                                    onMouseLeave={(e) => e.currentTarget.style.background = 'rgba(239, 68, 68, 0.2)'}
                                >""",
    """                                <button
                                    onClick={handleCloseTwin}
                                    style={{
                                        background: '#FEE2E2', color: '#DC2626', border: '1px solid #FECACA',
                                        padding: '8px 16px', borderRadius: 6, fontWeight: 700, fontSize: 12, cursor: 'pointer', transition: 'all 0.2s'
                                    }}
                                    onMouseEnter={(e) => e.currentTarget.style.background = '#FCA5A5'}
                                    onMouseLeave={(e) => e.currentTarget.style.background = '#FEE2E2'}
                                >"""
)

# 3D View / 2D Plan buttons
content = content.replace(
    """                                    <button
                                        onClick={() => window.cityViewer && window.cityViewer.setPreset('oblique')}
                                        title="3D Oblique Perspective"
                                        style={{
                                            background: 'rgba(15,23,42,0.8)', color: 'var(--text-secondary)',
                                            border: '1px solid var(--border-subtle)', padding: '6px 12px', borderRadius: 6,
                                            fontSize: 11, fontWeight: 700, cursor: 'pointer', transition: 'all 0.15s'
                                        }}
                                        onMouseEnter={(e) => e.currentTarget.style.color = '#fff'}
                                        onMouseLeave={(e) => e.currentTarget.style.color = 'var(--text-secondary)'}
                                    >""",
    """                                    <button
                                        onClick={() => window.cityViewer && window.cityViewer.setPreset('oblique')}
                                        title="3D Oblique Perspective"
                                        style={{
                                            background: '#F8FAFC', color: '#64748B',
                                            border: '1px solid #D9E1E8', padding: '6px 12px', borderRadius: 6,
                                            fontSize: 11, fontWeight: 700, cursor: 'pointer', transition: 'all 0.15s'
                                        }}
                                        onMouseEnter={(e) => { e.currentTarget.style.color = '#155E95'; e.currentTarget.style.background = '#EDF5FB'; }}
                                        onMouseLeave={(e) => { e.currentTarget.style.color = '#64748B'; e.currentTarget.style.background = '#F8FAFC'; }}
                                    >"""
)

content = content.replace(
    """                                    <button
                                        onClick={() => window.cityViewer && window.cityViewer.setPreset('plan')}
                                        title="Top-Down Cadastral Plan"
                                        style={{
                                            background: 'rgba(15,23,42,0.8)', color: 'var(--text-secondary)',
                                            border: '1px solid var(--border-subtle)', padding: '6px 12px', borderRadius: 6,
                                            fontSize: 11, fontWeight: 700, cursor: 'pointer', transition: 'all 0.15s'
                                        }}
                                        onMouseEnter={(e) => e.currentTarget.style.color = '#fff'}
                                        onMouseLeave={(e) => e.currentTarget.style.color = 'var(--text-secondary)'}
                                    >""",
    """                                    <button
                                        onClick={() => window.cityViewer && window.cityViewer.setPreset('plan')}
                                        title="Top-Down Cadastral Plan"
                                        style={{
                                            background: '#F8FAFC', color: '#64748B',
                                            border: '1px solid #D9E1E8', padding: '6px 12px', borderRadius: 6,
                                            fontSize: 11, fontWeight: 700, cursor: 'pointer', transition: 'all 0.15s'
                                        }}
                                        onMouseEnter={(e) => { e.currentTarget.style.color = '#155E95'; e.currentTarget.style.background = '#EDF5FB'; }}
                                        onMouseLeave={(e) => { e.currentTarget.style.color = '#64748B'; e.currentTarget.style.background = '#F8FAFC'; }}
                                    >"""
)

# 3D Urban Cadastral Asset badge
content = content.replace(
    """                                <span style={{
                                    fontSize: 10, fontWeight: 800, padding: '3px 9px', borderRadius: 20,
                                    background: 'var(--accent-cyan)', color: '#000'
                                }}>
                                    3D URBAN CADASTRAL ASSET
                                </span>""",
    """                                <span style={{
                                    fontSize: 10, fontWeight: 700, padding: '3px 9px', borderRadius: 6,
                                    background: '#EAF0F6', color: '#155E95', border: '1px solid #D9E1E8'
                                }}>
                                    3D URBAN CADASTRAL ASSET
                                </span>"""
)

# Launch 3D Digital Twin button
content = content.replace(
    """                            <button
                                onClick={() => handleOpenTwin(selectedBuilding)}
                                style={{
                                    width: '100%', background: 'linear-gradient(135deg, #00e5ff 0%, #0284c7 100%)',
                                    color: '#000', border: 'none', padding: '12px', borderRadius: 8, fontWeight: 800,
                                    fontSize: 13, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    gap: 8, boxShadow: '0 0 20px rgba(0,229,255,0.4)', transition: 'all 0.2s'
                                }}
                            >""",
    """                            <button
                                onClick={() => handleOpenTwin(selectedBuilding)}
                                style={{
                                    width: '100%', background: '#155E95',
                                    color: '#FFFFFF', border: 'none', padding: '12px', borderRadius: 6, fontWeight: 700,
                                    fontSize: 13, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    gap: 8, boxShadow: '0 2px 6px rgba(21, 94, 149, 0.25)', transition: 'all 0.2s'
                                }}
                            >"""
)

# Explode floors container
content = content.replace(
    """                                <div style={{
                                    background: 'rgba(15,23,42,0.7)', borderRadius: 10, padding: 14,
                                    border: '1px solid var(--border-subtle)', marginBottom: 16
                                }}>""",
    """                                <div style={{
                                    background: '#F8FAFC', borderRadius: 6, padding: 14,
                                    border: '1px solid #D9E1E8', marginBottom: 16
                                }}>"""
)

# Wing buttons
content = content.replace(
    """                                    <button
                                        onClick={() => setSelectedWing('all')}
                                        style={{
                                            flex: 1, padding: '7px 0', borderRadius: 6, fontSize: 11, fontWeight: 700,
                                            background: selectedWing === 'all' ? 'var(--accent-cyan)' : 'rgba(15,23,42,0.8)',
                                            color: selectedWing === 'all' ? '#000' : 'var(--text-secondary)',
                                            border: '1px solid var(--border-subtle)', cursor: 'pointer'
                                        }}
                                    >""",
    """                                    <button
                                        onClick={() => setSelectedWing('all')}
                                        style={{
                                            flex: 1, padding: '7px 0', borderRadius: 6, fontSize: 11, fontWeight: 700,
                                            background: selectedWing === 'all' ? '#155E95' : '#FFFFFF',
                                            color: selectedWing === 'all' ? '#FFFFFF' : '#64748B',
                                            border: '1px solid #D9E1E8', cursor: 'pointer'
                                        }}
                                    >"""
)

content = content.replace(
    """                                        <button
                                            key={w.wing_id}
                                            onClick={() => setSelectedWing(w.wing_id)}
                                            style={{
                                                flex: 1, padding: '7px 0', borderRadius: 6, fontSize: 11, fontWeight: 700,
                                                background: selectedWing === w.wing_id ? 'var(--accent-cyan)' : 'rgba(15,23,42,0.8)',
                                                color: selectedWing === w.wing_id ? '#000' : 'var(--text-secondary)',
                                                border: '1px solid var(--border-subtle)', cursor: 'pointer'
                                            }}
                                        >""",
    """                                        <button
                                            key={w.wing_id}
                                            onClick={() => setSelectedWing(w.wing_id)}
                                            style={{
                                                flex: 1, padding: '7px 0', borderRadius: 6, fontSize: 11, fontWeight: 700,
                                                background: selectedWing === w.wing_id ? '#155E95' : '#FFFFFF',
                                                color: selectedWing === w.wing_id ? '#FFFFFF' : '#64748B',
                                                border: '1px solid #D9E1E8', cursor: 'pointer'
                                            }}
                                        >"""
)

# Floor item
content = content.replace(
    """                                                style={{
                                                    background: isFlActive ? 'rgba(0, 229, 255, 0.12)' : 'rgba(15, 23, 42, 0.6)',
                                                    border: isFlActive ? '1px solid var(--accent-cyan)' : '1px solid var(--border-subtle)',
                                                    borderRadius: 8, padding: 10, marginBottom: 8, transition: 'all 0.15s'
                                                }}""",
    """                                                style={{
                                                    background: isFlActive ? 'rgba(21, 94, 149, 0.10)' : '#F8FAFC',
                                                    border: isFlActive ? '1px solid #155E95' : '1px solid #D9E1E8',
                                                    borderRadius: 6, padding: 10, marginBottom: 8, transition: 'all 0.15s'
                                                }}"""
)

# Unit item
content = content.replace(
    """                                                                        style={{
                                                                            background: isUActive ? 'var(--accent-cyan)' : 'rgba(30, 41, 59, 0.8)',
                                                                            color: isUActive ? '#000' : '#fff',
                                                                            border: isUActive ? '1px solid #fff' : '1px solid rgba(255,255,255,0.05)',
                                                                            padding: '6px 8px', borderRadius: 6, cursor: 'pointer', transition: 'all 0.15s'
                                                                        }}""",
    """                                                                        style={{
                                                                            background: isUActive ? '#155E95' : '#FFFFFF',
                                                                            color: isUActive ? '#FFFFFF' : '#1F2937',
                                                                            border: isUActive ? '1px solid #155E95' : '1px solid #D9E1E8',
                                                                            padding: '6px 8px', borderRadius: 6, cursor: 'pointer', transition: 'all 0.15s'
                                                                        }}"""
)

# Right Cadastral Title Panel badge
content = content.replace(
    """                                    <span style={{
                                        fontSize: 10, fontWeight: 800, padding: '3px 9px', borderRadius: 20,
                                        background: selectedFlat ? 'var(--accent-amber)' : 'var(--accent-cyan)',
                                        color: '#000'
                                    }}>""",
    """                                    <span style={{
                                        fontSize: 10, fontWeight: 700, padding: '3px 9px', borderRadius: 6,
                                        background: selectedFlat ? '#FEF3C7' : '#EAF0F6',
                                        color: selectedFlat ? '#D97706' : '#155E95',
                                        border: selectedFlat ? '1px solid #FDE68A' : '1px solid #D9E1E8'
                                    }}>"""
)

# Selected Flat ULPIN box
content = content.replace(
    """                                        <div style={{
                                            background: 'rgba(0, 229, 255, 0.08)', border: '1px solid var(--accent-cyan)',
                                            borderRadius: 8, padding: 12, marginBottom: 16
                                        }}>""",
    """                                        <div style={{
                                            background: '#F0F7FF', border: '1px solid rgba(21, 94, 149, 0.25)',
                                            borderRadius: 6, padding: 12, marginBottom: 16
                                        }}>"""
)

# Copy 3D ULPIN Button
content = content.replace(
    """                                        <button
                                            onClick={() => {
                                                navigator.clipboard.writeText(selectedFlat.unit_ulpin);
                                                alert(`Copied 3D ULPIN to Clipboard:\\n${selectedFlat.unit_ulpin}`);
                                            }}
                                            style={{
                                                width: '100%', background: 'rgba(0, 229, 255, 0.15)', color: 'var(--accent-cyan)',
                                                border: '1px solid var(--accent-cyan)', padding: '10px', borderRadius: 8,
                                                fontWeight: 700, fontSize: 12, cursor: 'pointer', display: 'flex', alignItems: 'center',
                                                justifyContent: 'center', gap: 6, transition: 'all 0.2s'
                                            }}
                                        >""",
    """                                        <button
                                            onClick={() => {
                                                navigator.clipboard.writeText(selectedFlat.unit_ulpin);
                                                alert(`Copied 3D ULPIN to Clipboard:\\n${selectedFlat.unit_ulpin}`);
                                            }}
                                            style={{
                                                width: '100%', background: '#155E95', color: '#FFFFFF',
                                                border: 'none', padding: '10px', borderRadius: 6,
                                                fontWeight: 700, fontSize: 12, cursor: 'pointer', display: 'flex', alignItems: 'center',
                                                justifyContent: 'center', gap: 6, transition: 'all 0.2s',
                                                boxShadow: '0 2px 6px rgba(21, 94, 149, 0.25)'
                                            }}
                                        >"""
)

# Building Base Parcel ULPIN box
content = content.replace(
    """                                        <div style={{
                                            background: 'rgba(0, 229, 255, 0.08)', border: '1px solid var(--accent-cyan)',
                                            borderRadius: 8, padding: 12, marginBottom: 16
                                        }}>""",
    """                                        <div style={{
                                            background: '#F0F7FF', border: '1px solid rgba(21, 94, 149, 0.25)',
                                            borderRadius: 6, padding: 12, marginBottom: 16
                                        }}>"""
)

# Instruction callout box at bottom of right panel
content = content.replace(
    """                                        <div style={{
                                            background: 'rgba(15,23,42,0.7)', borderRadius: 8, padding: 14,
                                            border: '1px solid var(--border-subtle)', textAlign: 'center', marginTop: 'auto'
                                        }}>""",
    """                                        <div style={{
                                            background: '#F8FAFC', borderRadius: 6, padding: 14,
                                            border: '1px solid #D9E1E8', textAlign: 'center', marginTop: 'auto'
                                        }}>"""
)

with open(app_path, "w", encoding="utf-8") as f:
    f.write(content)

print("apply_full_gov_theme completed!")

