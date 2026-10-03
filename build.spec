# -*- mode: python ; coding: utf-8 -*-

# 版本资源：版本号只在 project_stats/app_info.py 里维护一份，这里把它翻译成
# Windows 版本资源写进 exe（"属性 → 详细信息" 里的文件版本/产品版本）。
# 此前 EXE() 没有 version= 参数，两个 exe 的版本字段全是空的。
import importlib.util as _importlib_util
import os as _os

_version_module_path = _os.path.join(SPECPATH, 'tools', 'version_info.py')
_version_spec = _importlib_util.spec_from_file_location('project_stats_version_info', _version_module_path)
_version_module = _importlib_util.module_from_spec(_version_spec)
_version_spec.loader.exec_module(_version_module)
VERSION_INFO = _version_module.build_version_info()


a = Analysis(
    ['project_stats/app.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['pystray._win32', 'PIL._tkinter_finder'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='\u9879\u76ee\u7edf\u8ba1',
    # onedir 模式下由 COLLECT 负责携带二进制依赖，避免在 dist 根目录
    # 额外生成一个缺少 _internal 目录的半成品 EXE。
    exclude_binaries=True,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # 关闭 UPX，减少 Windows Defender/杀毒软件对启动解包和临时目录的误报。
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['\u9879\u76ee\u7edf\u8ba1.ico'],
    version=VERSION_INFO,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='\u9879\u76ee\u7edf\u8ba1',
)
