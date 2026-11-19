#!/usr/bin/env python3
"""
MSK Phone Device Database Generator
Generates a massive realistic Android device database from known device patterns.
Run this once to produce: MSK_core/Assets/phone_devices.json

Usage:
    python generate_device_db.py
    python generate_device_db.py --count 500  (generate 500 variants)
"""

import json
import os
import hashlib
import random
import argparse
from typing import Dict, List, Any

# ── Real device seeds — brand/model/chipset/screen data based on actual hardware ──
DEVICE_SEEDS = [
    # ─── Samsung ───
    {"brand": "samsung", "model": "SM-G991B", "marketing": "Galaxy S21", "chipset": "exynos9840", "cpu": "exynos", "gpu": "Mali-G78 MP14", "ram_gb": 8, "screen_w": 1080, "screen_h": 2400, "dpi": 421, "android": 13, "sdk": 33},
    {"brand": "samsung", "model": "SM-G998B", "marketing": "Galaxy S21 Ultra", "chipset": "exynos9840", "cpu": "exynos", "gpu": "Mali-G78 MP14", "ram_gb": 12, "screen_w": 1440, "screen_h": 3200, "dpi": 515, "android": 13, "sdk": 33},
    {"brand": "samsung", "model": "SM-S908B", "marketing": "Galaxy S22 Ultra", "chipset": "exynos2200", "cpu": "exynos", "gpu": "Xclipse 920", "ram_gb": 12, "screen_w": 1440, "screen_h": 3088, "dpi": 500, "android": 14, "sdk": 34},
    {"brand": "samsung", "model": "SM-S911B", "marketing": "Galaxy S23", "chipset": "SM8550", "cpu": "qcom", "gpu": "Adreno 740", "ram_gb": 8, "screen_w": 1080, "screen_h": 2340, "dpi": 393, "android": 14, "sdk": 34},
    {"brand": "samsung", "model": "SM-S918B", "marketing": "Galaxy S23 Ultra", "chipset": "SM8550", "cpu": "qcom", "gpu": "Adreno 740", "ram_gb": 12, "screen_w": 1440, "screen_h": 3088, "dpi": 500, "android": 14, "sdk": 34},
    {"brand": "samsung", "model": "SM-A546B", "marketing": "Galaxy A54", "chipset": "exynos1380", "cpu": "exynos", "gpu": "Mali-G68", "ram_gb": 8, "screen_w": 1080, "screen_h": 2340, "dpi": 390, "android": 13, "sdk": 33},
    {"brand": "samsung", "model": "SM-A336B", "marketing": "Galaxy A33", "chipset": "exynos1280", "cpu": "exynos", "gpu": "Mali-G68", "ram_gb": 6, "screen_w": 1080, "screen_h": 2408, "dpi": 401, "android": 12, "sdk": 31},
    {"brand": "samsung", "model": "SM-A736B", "marketing": "Galaxy A73", "chipset": "SM7325", "cpu": "qcom", "gpu": "Adreno 642L", "ram_gb": 8, "screen_w": 1080, "screen_h": 2408, "dpi": 393, "android": 12, "sdk": 31},
    {"brand": "samsung", "model": "SM-M526B", "marketing": "Galaxy M52", "chipset": "SM7325", "cpu": "qcom", "gpu": "Adreno 642L", "ram_gb": 6, "screen_w": 1080, "screen_h": 2408, "dpi": 393, "android": 11, "sdk": 30},
    {"brand": "samsung", "model": "SM-A235F", "marketing": "Galaxy A23", "chipset": "SM6225", "cpu": "qcom", "gpu": "Adreno 619", "ram_gb": 4, "screen_w": 720, "screen_h": 1600, "dpi": 269, "android": 12, "sdk": 31},
    {"brand": "samsung", "model": "SM-A135F", "marketing": "Galaxy A13", "chipset": "exynos850", "cpu": "exynos", "gpu": "Mali-G52", "ram_gb": 4, "screen_w": 1080, "screen_h": 2408, "dpi": 401, "android": 12, "sdk": 31},
    {"brand": "samsung", "model": "SM-A528B", "marketing": "Galaxy A52s 5G", "chipset": "SM7325", "cpu": "qcom", "gpu": "Adreno 642L", "ram_gb": 6, "screen_w": 1080, "screen_h": 2400, "dpi": 407, "android": 12, "sdk": 31},
    {"brand": "samsung", "model": "SM-F936B", "marketing": "Galaxy Z Fold4", "chipset": "SM8475", "cpu": "qcom", "gpu": "Adreno 730", "ram_gb": 12, "screen_w": 1812, "screen_h": 2176, "dpi": 373, "android": 13, "sdk": 33},
    {"brand": "samsung", "model": "SM-F721B", "marketing": "Galaxy Z Flip4", "chipset": "SM8475", "cpu": "qcom", "gpu": "Adreno 730", "ram_gb": 8, "screen_w": 1080, "screen_h": 2640, "dpi": 425, "android": 13, "sdk": 33},

    # ─── Xiaomi / Redmi / POCO ───
    {"brand": "Xiaomi", "model": "2211133G", "marketing": "Xiaomi 13", "chipset": "SM8550", "cpu": "qcom", "gpu": "Adreno 740", "ram_gb": 8, "screen_w": 1080, "screen_h": 2400, "dpi": 413, "android": 13, "sdk": 33},
    {"brand": "Xiaomi", "model": "2201122G", "marketing": "Xiaomi 12", "chipset": "SM8450", "cpu": "qcom", "gpu": "Adreno 730", "ram_gb": 8, "screen_w": 1080, "screen_h": 2400, "dpi": 419, "android": 12, "sdk": 31},
    {"brand": "Xiaomi", "model": "M2007J3SG", "marketing": "Xiaomi Mi 10T", "chipset": "SM8250", "cpu": "qcom", "gpu": "Adreno 650", "ram_gb": 8, "screen_w": 1080, "screen_h": 2400, "dpi": 395, "android": 11, "sdk": 30},
    {"brand": "Redmi", "model": "220333QAG", "marketing": "Redmi Note 12", "chipset": "SM6375", "cpu": "qcom", "gpu": "Adreno 619", "ram_gb": 6, "screen_w": 1080, "screen_h": 2400, "dpi": 395, "android": 12, "sdk": 31},
    {"brand": "Redmi", "model": "21091116AI", "marketing": "Redmi Note 11", "chipset": "SM6225", "cpu": "qcom", "gpu": "Adreno 619", "ram_gb": 4, "screen_w": 1080, "screen_h": 2400, "dpi": 401, "android": 11, "sdk": 30},
    {"brand": "Redmi", "model": "M2006C3MG", "marketing": "Redmi Note 9", "chipset": "MT6769", "cpu": "mediatek", "gpu": "Mali-G52 MC2", "ram_gb": 4, "screen_w": 1080, "screen_h": 2340, "dpi": 395, "android": 10, "sdk": 29},
    {"brand": "Redmi", "model": "220333QPG", "marketing": "Redmi 10C", "chipset": "SM6225", "cpu": "qcom", "gpu": "Adreno 619", "ram_gb": 4, "screen_w": 720, "screen_h": 1600, "dpi": 269, "android": 11, "sdk": 30},
    {"brand": "POCO", "model": "M2012K11AG", "marketing": "POCO X3 Pro", "chipset": "SM8150", "cpu": "qcom", "gpu": "Adreno 640", "ram_gb": 6, "screen_w": 1080, "screen_h": 2400, "dpi": 395, "android": 11, "sdk": 30},
    {"brand": "POCO", "model": "22041219PG", "marketing": "POCO F4 GT", "chipset": "SM8450", "cpu": "qcom", "gpu": "Adreno 730", "ram_gb": 8, "screen_w": 1080, "screen_h": 2400, "dpi": 395, "android": 12, "sdk": 31},
    {"brand": "POCO", "model": "22021211RG", "marketing": "POCO M4 Pro", "chipset": "MT6781", "cpu": "mediatek", "gpu": "Mali-G57 MC2", "ram_gb": 6, "screen_w": 1080, "screen_h": 2400, "dpi": 395, "android": 11, "sdk": 30},

    # ─── Vivo ───
    {"brand": "vivo", "model": "vivo 1910", "marketing": "Vivo V17 Pro", "chipset": "SM6150", "cpu": "qcom", "gpu": "Adreno 612", "ram_gb": 8, "screen_w": 1080, "screen_h": 2340, "dpi": 390, "android": 12, "sdk": 31},
    {"brand": "vivo", "model": "V2127", "marketing": "Vivo Y21", "chipset": "MT6765", "cpu": "mediatek", "gpu": "Mali-G52 MC2", "ram_gb": 4, "screen_w": 720, "screen_h": 1600, "dpi": 269, "android": 11, "sdk": 30},
    {"brand": "vivo", "model": "V2109", "marketing": "Vivo Y33s", "chipset": "MT6765", "cpu": "mediatek", "gpu": "Mali-G52 MC2", "ram_gb": 8, "screen_w": 1080, "screen_h": 2408, "dpi": 401, "android": 11, "sdk": 30},
    {"brand": "vivo", "model": "V2204", "marketing": "Vivo V23", "chipset": "MT6877", "cpu": "mediatek", "gpu": "Mali-G68 MC4", "ram_gb": 8, "screen_w": 1080, "screen_h": 2376, "dpi": 390, "android": 12, "sdk": 31},
    {"brand": "vivo", "model": "V2118", "marketing": "Vivo X70 Pro", "chipset": "MT6893", "cpu": "mediatek", "gpu": "Mali-G78 MC10", "ram_gb": 12, "screen_w": 1080, "screen_h": 2400, "dpi": 421, "android": 12, "sdk": 31},
    {"brand": "vivo", "model": "V2145", "marketing": "Vivo T1", "chipset": "SM6225", "cpu": "qcom", "gpu": "Adreno 619", "ram_gb": 8, "screen_w": 1080, "screen_h": 2408, "dpi": 401, "android": 12, "sdk": 31},
    {"brand": "vivo", "model": "V2219", "marketing": "Vivo Y75", "chipset": "MT6781", "cpu": "mediatek", "gpu": "Mali-G57 MC2", "ram_gb": 8, "screen_w": 1080, "screen_h": 2408, "dpi": 401, "android": 12, "sdk": 31},

    # ─── OPPO ───
    {"brand": "OPPO", "model": "CPH2269", "marketing": "OPPO A96", "chipset": "SM6225", "cpu": "qcom", "gpu": "Adreno 619", "ram_gb": 8, "screen_w": 1080, "screen_h": 2412, "dpi": 401, "android": 11, "sdk": 30},
    {"brand": "OPPO", "model": "CPH2325", "marketing": "OPPO Reno8", "chipset": "MT6877", "cpu": "mediatek", "gpu": "Mali-G68 MC4", "ram_gb": 8, "screen_w": 1080, "screen_h": 2400, "dpi": 394, "android": 12, "sdk": 31},
    {"brand": "OPPO", "model": "CPH2385", "marketing": "OPPO Find X5", "chipset": "SM8450", "cpu": "qcom", "gpu": "Adreno 730", "ram_gb": 8, "screen_w": 1080, "screen_h": 2400, "dpi": 394, "android": 12, "sdk": 31},
    {"brand": "OPPO", "model": "CPH2219", "marketing": "OPPO A74", "chipset": "SM6225", "cpu": "qcom", "gpu": "Adreno 619", "ram_gb": 6, "screen_w": 1080, "screen_h": 2400, "dpi": 401, "android": 11, "sdk": 30},
    {"brand": "OPPO", "model": "CPH2127", "marketing": "OPPO A53", "chipset": "SM4250", "cpu": "qcom", "gpu": "Adreno 610", "ram_gb": 4, "screen_w": 720, "screen_h": 1600, "dpi": 269, "android": 10, "sdk": 29},
    {"brand": "OPPO", "model": "CPH2471", "marketing": "OPPO A57", "chipset": "MT6765", "cpu": "mediatek", "gpu": "Mali-G52 MC2", "ram_gb": 4, "screen_w": 720, "screen_h": 1612, "dpi": 269, "android": 12, "sdk": 31},

    # ─── OnePlus ───
    {"brand": "OnePlus", "model": "LE2115", "marketing": "OnePlus 9", "chipset": "SM8350", "cpu": "qcom", "gpu": "Adreno 660", "ram_gb": 8, "screen_w": 1080, "screen_h": 2400, "dpi": 395, "android": 13, "sdk": 33},
    {"brand": "OnePlus", "model": "CPH2399", "marketing": "OnePlus 10T", "chipset": "SM8475", "cpu": "qcom", "gpu": "Adreno 730", "ram_gb": 8, "screen_w": 1080, "screen_h": 2412, "dpi": 394, "android": 13, "sdk": 33},
    {"brand": "OnePlus", "model": "LE2117", "marketing": "OnePlus 9 Pro", "chipset": "SM8350", "cpu": "qcom", "gpu": "Adreno 660", "ram_gb": 8, "screen_w": 1440, "screen_h": 3216, "dpi": 525, "android": 13, "sdk": 33},
    {"brand": "OnePlus", "model": "CPH2447", "marketing": "OnePlus Nord 2T", "chipset": "MT6893", "cpu": "mediatek", "gpu": "Mali-G610 MC6", "ram_gb": 8, "screen_w": 1080, "screen_h": 2400, "dpi": 395, "android": 12, "sdk": 31},
    {"brand": "OnePlus", "model": "CPH2409", "marketing": "OnePlus Nord CE 2", "chipset": "MT6877", "cpu": "mediatek", "gpu": "Mali-G68 MC4", "ram_gb": 8, "screen_w": 1080, "screen_h": 2400, "dpi": 401, "android": 12, "sdk": 31},

    # ─── Realme ───
    {"brand": "realme", "model": "RMX3491", "marketing": "Realme 9 Pro+", "chipset": "MT6877", "cpu": "mediatek", "gpu": "Mali-G68 MC4", "ram_gb": 6, "screen_w": 1080, "screen_h": 2400, "dpi": 394, "android": 12, "sdk": 31},
    {"brand": "realme", "model": "RMX3363", "marketing": "Realme GT Neo 2", "chipset": "SM8250-AC", "cpu": "qcom", "gpu": "Adreno 650", "ram_gb": 8, "screen_w": 1080, "screen_h": 2400, "dpi": 395, "android": 12, "sdk": 31},
    {"brand": "realme", "model": "RMX3630", "marketing": "Realme 10 Pro+", "chipset": "MT6877", "cpu": "mediatek", "gpu": "Mali-G68 MC4", "ram_gb": 8, "screen_w": 1080, "screen_h": 2400, "dpi": 394, "android": 13, "sdk": 33},
    {"brand": "realme", "model": "RMX3085", "marketing": "Realme 8", "chipset": "MT6785", "cpu": "mediatek", "gpu": "Mali-G76 MC4", "ram_gb": 6, "screen_w": 1080, "screen_h": 2400, "dpi": 409, "android": 11, "sdk": 30},
    {"brand": "realme", "model": "RMX2111", "marketing": "Realme 7", "chipset": "MT6785", "cpu": "mediatek", "gpu": "Mali-G76 MC4", "ram_gb": 6, "screen_w": 1080, "screen_h": 2400, "dpi": 401, "android": 10, "sdk": 29},

    # ─── Huawei / Honor ───
    {"brand": "HUAWEI", "model": "ELS-NX9", "marketing": "Huawei P40 Pro", "chipset": "kirin990_5g", "cpu": "kirin", "gpu": "Mali-G76 MP16", "ram_gb": 8, "screen_w": 1200, "screen_h": 2640, "dpi": 441, "android": 10, "sdk": 29},
    {"brand": "HUAWEI", "model": "NOH-NX9", "marketing": "Huawei Mate 40 Pro", "chipset": "kirin9000", "cpu": "kirin", "gpu": "Mali-G78 MP24", "ram_gb": 8, "screen_w": 1344, "screen_h": 2772, "dpi": 456, "android": 10, "sdk": 29},
    {"brand": "Honor", "model": "ANY-LX1", "marketing": "Honor 50", "chipset": "SM7325", "cpu": "qcom", "gpu": "Adreno 642L", "ram_gb": 6, "screen_w": 1080, "screen_h": 2340, "dpi": 390, "android": 11, "sdk": 30},
    {"brand": "Honor", "model": "RKY-LX1", "marketing": "Honor Magic5 Lite", "chipset": "SM6375", "cpu": "qcom", "gpu": "Adreno 619", "ram_gb": 6, "screen_w": 1080, "screen_h": 2412, "dpi": 394, "android": 12, "sdk": 31},

    # ─── Motorola ───
    {"brand": "motorola", "model": "XT2201-1", "marketing": "Moto Edge 30 Pro", "chipset": "SM8450", "cpu": "qcom", "gpu": "Adreno 730", "ram_gb": 8, "screen_w": 1080, "screen_h": 2400, "dpi": 395, "android": 12, "sdk": 31},
    {"brand": "motorola", "model": "XT2175-2", "marketing": "Moto G82", "chipset": "SM7325", "cpu": "qcom", "gpu": "Adreno 642L", "ram_gb": 6, "screen_w": 1080, "screen_h": 2400, "dpi": 394, "android": 12, "sdk": 31},
    {"brand": "motorola", "model": "XT2153-1", "marketing": "Moto G71 5G", "chipset": "SM6375", "cpu": "qcom", "gpu": "Adreno 619", "ram_gb": 6, "screen_w": 1080, "screen_h": 2400, "dpi": 395, "android": 11, "sdk": 30},
    {"brand": "motorola", "model": "XT2235-2", "marketing": "Moto G53", "chipset": "SM4350-AC", "cpu": "qcom", "gpu": "Adreno 619", "ram_gb": 4, "screen_w": 720, "screen_h": 1600, "dpi": 269, "android": 13, "sdk": 33},
    {"brand": "motorola", "model": "XT2137-1", "marketing": "Moto G200", "chipset": "SM8350", "cpu": "qcom", "gpu": "Adreno 660", "ram_gb": 8, "screen_w": 1080, "screen_h": 2460, "dpi": 403, "android": 12, "sdk": 31},

    # ─── Nokia ───
    {"brand": "Nokia", "model": "TA-1428", "marketing": "Nokia X30", "chipset": "SM6375", "cpu": "qcom", "gpu": "Adreno 619", "ram_gb": 6, "screen_w": 1080, "screen_h": 2400, "dpi": 401, "android": 12, "sdk": 31},
    {"brand": "Nokia", "model": "TA-1383", "marketing": "Nokia G21", "chipset": "MT6768", "cpu": "mediatek", "gpu": "Mali-G52 MC2", "ram_gb": 4, "screen_w": 720, "screen_h": 1600, "dpi": 269, "android": 11, "sdk": 30},
    {"brand": "Nokia", "model": "TA-1285", "marketing": "Nokia 5.4", "chipset": "SM4250", "cpu": "qcom", "gpu": "Adreno 610", "ram_gb": 4, "screen_w": 720, "screen_h": 1600, "dpi": 269, "android": 10, "sdk": 29},

    # ─── Sony ───
    {"brand": "Sony", "model": "XQ-BC72", "marketing": "Xperia 1 III", "chipset": "SM8350", "cpu": "qcom", "gpu": "Adreno 660", "ram_gb": 12, "screen_w": 1644, "screen_h": 3840, "dpi": 643, "android": 13, "sdk": 33},
    {"brand": "Sony", "model": "XQ-CT54", "marketing": "Xperia 10 IV", "chipset": "SM6375", "cpu": "qcom", "gpu": "Adreno 619", "ram_gb": 6, "screen_w": 1080, "screen_h": 2520, "dpi": 449, "android": 13, "sdk": 33},
    {"brand": "Sony", "model": "XQ-AT51", "marketing": "Xperia 5 II", "chipset": "SM8250", "cpu": "qcom", "gpu": "Adreno 650", "ram_gb": 8, "screen_w": 1080, "screen_h": 2520, "dpi": 449, "android": 12, "sdk": 31},

    # ─── Google Pixel ───
    {"brand": "Google", "model": "GVU6C", "marketing": "Pixel 7", "chipset": "gs201", "cpu": "google", "gpu": "Mali-G710 MP7", "ram_gb": 8, "screen_w": 1080, "screen_h": 2400, "dpi": 429, "android": 14, "sdk": 34},
    {"brand": "Google", "model": "GQML3", "marketing": "Pixel 6a", "chipset": "gs101", "cpu": "google", "gpu": "Mali-G78 MP20", "ram_gb": 6, "screen_w": 1080, "screen_h": 2400, "dpi": 429, "android": 14, "sdk": 34},
    {"brand": "Google", "model": "GP4BC", "marketing": "Pixel 7 Pro", "chipset": "gs201", "cpu": "google", "gpu": "Mali-G710 MP7", "ram_gb": 12, "screen_w": 1440, "screen_h": 3120, "dpi": 512, "android": 14, "sdk": 34},

    # ─── Tecno / Infinix / itel (budget Africa/Asia) ───
    {"brand": "TECNO", "model": "CH6i", "marketing": "Tecno Camon 18", "chipset": "MT6769", "cpu": "mediatek", "gpu": "Mali-G52 MC2", "ram_gb": 6, "screen_w": 1080, "screen_h": 2460, "dpi": 406, "android": 11, "sdk": 30},
    {"brand": "TECNO", "model": "LG7n", "marketing": "Tecno Spark 9 Pro", "chipset": "MT6761", "cpu": "mediatek", "gpu": "PowerVR GE8300", "ram_gb": 4, "screen_w": 720, "screen_h": 1600, "dpi": 269, "android": 12, "sdk": 31},
    {"brand": "Infinix", "model": "X6511", "marketing": "Infinix Note 12", "chipset": "MT6781", "cpu": "mediatek", "gpu": "Mali-G57 MC2", "ram_gb": 4, "screen_w": 1080, "screen_h": 2460, "dpi": 394, "android": 12, "sdk": 31},
    {"brand": "Infinix", "model": "X6816", "marketing": "Infinix Hot 20", "chipset": "MT6765", "cpu": "mediatek", "gpu": "Mali-G52 MC2", "ram_gb": 4, "screen_w": 720, "screen_h": 1612, "dpi": 269, "android": 12, "sdk": 31},

    # ─── Asus ───
    {"brand": "asus", "model": "ASUS_AI2203", "marketing": "Zenfone 9", "chipset": "SM8475", "cpu": "qcom", "gpu": "Adreno 730", "ram_gb": 8, "screen_w": 1080, "screen_h": 2400, "dpi": 445, "android": 13, "sdk": 33},
    {"brand": "asus", "model": "ASUS_AI2205", "marketing": "ROG Phone 6", "chipset": "SM8475", "cpu": "qcom", "gpu": "Adreno 730", "ram_gb": 12, "screen_w": 1080, "screen_h": 2448, "dpi": 395, "android": 13, "sdk": 33},

    # ─── ZTE / Nubia ───
    {"brand": "ZTE", "model": "ZTE 8030N", "marketing": "ZTE Blade A72", "chipset": "MT6765", "cpu": "mediatek", "gpu": "Mali-G52 MC2", "ram_gb": 3, "screen_w": 720, "screen_h": 1612, "dpi": 269, "android": 11, "sdk": 30},
    {"brand": "nubia", "model": "NX659J", "marketing": "Nubia Red Magic 6", "chipset": "SM8350", "cpu": "qcom", "gpu": "Adreno 660", "ram_gb": 12, "screen_w": 1080, "screen_h": 2400, "dpi": 395, "android": 11, "sdk": 30},

    # ─── Lenovo ───
    {"brand": "Lenovo", "model": "Lenovo K13 Note", "marketing": "Lenovo K13 Note", "chipset": "MT6769", "cpu": "mediatek", "gpu": "Mali-G52 MC2", "ram_gb": 4, "screen_w": 720, "screen_h": 1640, "dpi": 269, "android": 10, "sdk": 29},
    {"brand": "Lenovo", "model": "Lenovo Tab M8", "marketing": "Lenovo Tab M8", "chipset": "MT6762", "cpu": "mediatek", "gpu": "PowerVR GE8300", "ram_gb": 3, "screen_w": 800, "screen_h": 1280, "dpi": 189, "android": 10, "sdk": 29},
]

# ── Android version → security patch dates (realistic) ──
SECURITY_PATCHES = {
    14: ["2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01", "2024-05-01"],
    13: ["2023-01-01", "2023-03-01", "2023-05-01", "2023-07-01", "2023-09-01", "2023-11-01"],
    12: ["2022-03-01", "2022-05-01", "2022-07-01", "2022-09-01", "2022-11-01"],
    11: ["2021-03-01", "2021-06-01", "2021-09-01", "2021-11-01"],
    10: ["2020-03-01", "2020-06-01", "2020-09-01", "2020-12-01"],
}

BUILD_ID_MAP = {
    14: ["UP1A.231005.007", "UP1A.240401.001", "UQ1A.240205.002"],
    13: ["TP1A.221005.002", "TQ2A.230505.002", "TQ3A.230901.001"],
    12: ["SP1A.210812.003", "SP2A.220305.013", "SP3A.210811.010"],
    11: ["RP1A.200720.012", "RQ3A.210905.001", "RD2A.211001.002"],
    10: ["QP1A.190711.020", "QD1A.190821.011", "QKQ1.190910.002"],
}

CHROME_MAJOR_BY_YEAR = {
    # Chrome major versions shipped as Chrome for Android
    2024: [120, 121, 122, 123, 124, 125, 126],
    2023: [108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119],
    2022: [96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107],
    2021: [86, 87, 88, 89, 90, 91, 92, 93, 94, 95],
}

def _rng(seed: str, index: int) -> float:
    """Deterministic float 0-1 from seed + index."""
    h = int(hashlib.md5(f"{seed}:{index}".encode()).hexdigest(), 16)
    return (h % 1000000) / 1000000.0

def _pick(seed: str, index: int, lst: list):
    return lst[int(_rng(seed, index) * len(lst))]

def _randint(seed: str, index: int, lo: int, hi: int) -> int:
    return lo + int(_rng(seed, index) * (hi - lo + 1))


def build_device_profile(seed_device: dict, variant_seed: str) -> dict:
    """
    Given a real device seed and a variant string, produce a fully consistent
    phone fingerprint profile. Every field is deterministically derived from
    variant_seed so the same seed always gives the same fingerprint.
    """
    s = variant_seed
    android_ver = seed_device["android"]
    sdk = seed_device["sdk"]

    # Build fingerprint components
    build_id = _pick(s, 1, BUILD_ID_MAP.get(android_ver, BUILD_ID_MAP[12]))
    sec_patch = _pick(s, 2, SECURITY_PATCHES.get(android_ver, SECURITY_PATCHES[12]))

    brand_lc = seed_device["brand"].lower()
    model_id = seed_device["model"].lower().replace(" ", "")
    incremental = f"compiler{_randint(s, 3, 1, 12):02d}{_randint(s, 4, 1, 28):02d}{_randint(s, 5, 1000, 9999)}"
    build_user = _pick(s, 6, ["compiler", "builder", "release", "user"])
    build_host_suffixes = ["comsz01", "bldsvr", "compile", "android"]
    build_host = _pick(s, 7, build_host_suffixes) + str(_randint(s, 8, 100000, 999999))

    build_fingerprint = (
        f"{seed_device['brand']}/{seed_device['model']}/{seed_device['model']}:"
        f"{android_ver}/{build_id}/{incremental}:user/release-keys"
    )

    # Screen
    sw = seed_device["screen_w"]
    sh = seed_device["screen_h"]
    dpi = seed_device["dpi"]

    # RAM/storage variants
    ram_gb = seed_device["ram_gb"]
    storage_gb = _pick(s, 9, [64, 128, 256])

    # Chrome version (realistic for the android version year)
    if android_ver >= 13:
        chrome_candidates = CHROME_MAJOR_BY_YEAR[2023] + CHROME_MAJOR_BY_YEAR[2024]
    elif android_ver == 12:
        chrome_candidates = CHROME_MAJOR_BY_YEAR[2022] + CHROME_MAJOR_BY_YEAR[2023]
    else:
        chrome_candidates = CHROME_MAJOR_BY_YEAR[2021] + CHROME_MAJOR_BY_YEAR[2022]
    chrome_major = _pick(s, 10, chrome_candidates)
    chrome_minor = _randint(s, 11, 0, 9)
    chrome_patch = _randint(s, 12, 1000, 9999)
    chrome_sub = _randint(s, 13, 10, 150)
    chrome_full = f"{chrome_major}.0.{chrome_patch}.{chrome_sub}"

    # User agent (mobile Chrome for Android)
    ua = (
        f"Mozilla/5.0 (Linux; Android {android_ver}; {seed_device['model']}) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{chrome_full} Mobile Safari/537.36"
    )

    # WebView UA
    webview_ua = (
        f"Mozilla/5.0 (Linux; Android {android_ver}; {seed_device['model']}) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{chrome_full} Mobile Safari/537.36"
    )

    # sec-ch-ua
    ch_ua = (
        f'"Android WebView";v="{chrome_major}", '
        f'"Chromium";v="{chrome_major}", '
        f'"Google Chrome";v="{chrome_major}"'
    )

    # timezone variants per region
    timezones = [
        "Asia/Karachi", "Asia/Dhaka", "Asia/Jakarta", "Asia/Manila",
        "Asia/Kolkata", "Asia/Riyadh", "Asia/Dubai", "Asia/Baghdad",
        "Africa/Cairo", "Africa/Lagos", "Africa/Nairobi",
        "Europe/Istanbul", "Asia/Singapore", "Asia/Kuala_Lumpur",
        "America/New_York", "America/Chicago", "America/Los_Angeles",
        "Europe/London", "Europe/Paris", "Europe/Berlin",
        "Asia/Bangkok", "Asia/Ho_Chi_Minh", "Asia/Tokyo",
    ]
    timezone = _pick(s, 14, timezones)

    locale_map = {
        "Asia/Karachi": "en-PK", "Asia/Dhaka": "bn-BD", "Asia/Jakarta": "id-ID",
        "Asia/Manila": "en-PH", "Asia/Kolkata": "en-IN", "Asia/Riyadh": "ar-SA",
        "Asia/Dubai": "ar-AE", "Asia/Baghdad": "ar-IQ", "Africa/Cairo": "ar-EG",
        "Africa/Lagos": "en-NG", "Africa/Nairobi": "en-KE", "Europe/Istanbul": "tr-TR",
        "Asia/Singapore": "en-SG", "Asia/Kuala_Lumpur": "ms-MY",
        "America/New_York": "en-US", "America/Chicago": "en-US",
        "America/Los_Angeles": "en-US", "Europe/London": "en-GB",
        "Europe/Paris": "fr-FR", "Europe/Berlin": "de-DE",
        "Asia/Bangkok": "th-TH", "Asia/Ho_Chi_Minh": "vi-VN", "Asia/Tokyo": "ja-JP",
    }
    locale = locale_map.get(timezone, "en-US")
    lang_short = locale.split("-")[0]
    accept_language = f"{locale},{lang_short};q=0.9,en;q=0.8"

    # Hardware concurrency (CPU cores)
    cpu_cores_map = {"qcom": [6, 8], "mediatek": [6, 8], "exynos": [8], "kirin": [8], "google": [8]}
    cpu_cores = _pick(s, 15, cpu_cores_map.get(seed_device["cpu"], [6, 8]))

    # Device memory (navigator.deviceMemory)
    device_memory = _pick(s, 16, [4, 6, 8] if ram_gb >= 6 else [2, 3, 4])

    # Touch points
    max_touch = 10

    # Battery level (random 0.2 - 0.99)
    battery_level = round(0.20 + _rng(s, 17) * 0.79, 2)

    # Connection type
    connection_types = ["wifi", "4g", "5g"]
    connection = _pick(s, 18, connection_types)

    # Platform string for mobile (always Linux armv8l or 64)
    platform_str = "Linux armv8l"

    profile = {
        "seed": variant_seed,
        "device": {
            "brand": seed_device["brand"],
            "model": seed_device["model"],
            "marketing_name": seed_device["marketing"],
            "manufacturer": seed_device["brand"],
            "device_id": seed_device["model"].lower().replace(" ", "").replace("-", "_"),
            "board": seed_device["chipset"],
            "hardware": seed_device["cpu"],
            "chipset": seed_device["chipset"],
            "gpu": seed_device["gpu"],
            "cpu_abi": "arm64-v8a",
            "cpu_abi_list": "arm64-v8a,armeabi-v7a,armeabi",
            "cpu_cores": cpu_cores,
            "ram_gb": ram_gb,
            "storage_gb": storage_gb,
        },
        "system": {
            "android_version": str(android_ver),
            "sdk_version": str(sdk),
            "security_patch": sec_patch,
            "build_id": build_id,
            "build_fingerprint": build_fingerprint,
            "build_type": "user",
            "build_tags": "release-keys",
            "build_incremental": incremental,
            "build_user": build_user,
            "build_host": build_host,
        },
        "display": {
            "width_px": sw,
            "height_px": sh,
            "dpi": dpi,
            "density": round(dpi / 160.0, 1),
            "density_dpi_name": _dpi_bucket(dpi),
            "physical_width_dp": round(sw / (dpi / 160.0)),
            "physical_height_dp": round(sh / (dpi / 160.0)),
            "avail_width": sw,
            "avail_height": sh - _randint(s, 19, 36, 90),  # nav bar
            "color_depth": 24,
            "pixel_depth": 24,
            "outer_width": sw,
            "outer_height": sh,
        },
        "browser": {
            "user_agent": ua,
            "webview_ua": webview_ua,
            "chrome_version": chrome_full,
            "chrome_major": chrome_major,
            "platform": platform_str,
            "language": locale,
            "languages": [locale, lang_short, "en"],
            "accept_language": accept_language,
            "timezone": timezone,
            "hardware_concurrency": cpu_cores,
            "device_memory": device_memory,
            "max_touch_points": max_touch,
            "mobile": True,
            "sec_ch_ua": ch_ua,
            "sec_ch_ua_mobile": "?1",
            "sec_ch_ua_platform": '"Android"',
            "sec_ch_ua_platform_version": f'"{android_ver}.0.0"',
            "sec_ch_ua_arch": '"arm"',
            "sec_ch_ua_bitness": '"64"',
            "sec_ch_ua_full_version_list": ch_ua.replace(f'v="{chrome_major}"', f'v="{chrome_full}"'),
        },
        "sensors": {
            "accelerometer": True,
            "gyroscope": True,
            "magnetometer": True,
            "proximity": True,
            "ambient_light": True,
            "barometer": android_ver >= 11,
        },
        "network": {
            "connection_type": connection,
            "downlink": round(1.5 + _rng(s, 20) * 48.5, 1),
            "rtt": _randint(s, 21, 20, 200),
        },
        "battery": {
            "level": battery_level,
            "charging": _rng(s, 22) > 0.6,
        },
    }
    return profile


def _dpi_bucket(dpi: int) -> str:
    if dpi <= 120: return "ldpi"
    if dpi <= 160: return "mdpi"
    if dpi <= 240: return "hdpi"
    if dpi <= 320: return "xhdpi"
    if dpi <= 480: return "xxhdpi"
    return "xxxhdpi"


def generate_database(num_variants_per_device: int = 300) -> List[dict]:
    """
    For each seed device, generate N variants with unique seeds.
    Total profiles = len(DEVICE_SEEDS) * num_variants_per_device
    """
    profiles = []
    total = 0
    for seed_dev in DEVICE_SEEDS:
        for i in range(num_variants_per_device):
            # Generate a unique deterministic seed from device model + index
            variant_seed = hashlib.sha256(
                f"{seed_dev['model']}:{seed_dev['brand']}:{i}".encode()
            ).hexdigest()[:16]
            profile = build_device_profile(seed_dev, variant_seed)
            profiles.append(profile)
            total += 1
    print(f"[+] Generated {total} phone fingerprint profiles from {len(DEVICE_SEEDS)} device models.")
    return profiles


def main():
    parser = argparse.ArgumentParser(description="Build MSK phone device fingerprint database.")
    parser.add_argument("--variants", type=int, default=300,
                        help="Variants per device model (default 300 → ~20k+ profiles)")
    parser.add_argument("--out", type=str, default=None,
                        help="Output JSON path (default: MSK_core/Assets/phone_devices.json)")
    args = parser.parse_args()

    # Resolve output path relative to this script's repo root
    this_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(this_dir)  # python-tools/ → repo root
    if args.out:
        out_path = args.out
    else:
        assets_dir = os.path.join(repo_root, "MSK_core", "Assets")
        os.makedirs(assets_dir, exist_ok=True)
        out_path = os.path.join(assets_dir, "phone_devices.json")

    profiles = generate_database(num_variants_per_device=args.variants)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(profiles, f, ensure_ascii=False, separators=(",", ":"))

    size_mb = os.path.getsize(out_path) / 1024 / 1024
    print(f"[+] Saved {len(profiles)} profiles to: {out_path} ({size_mb:.1f} MB)")
    print(f"[+] Coverage: {len(DEVICE_SEEDS)} device models × {args.variants} variants each")


if __name__ == "__main__":
    main()
