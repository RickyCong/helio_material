"""查询 Helio API 所有材料并按品牌分类输出全部字段。"""

import os
from datetime import datetime

import requests
from rich.console import Console
from rich.table import Table

API_URL = "https://api.helioadditive.com/graphql"
TOKEN = os.environ.get("HELIO_TOKEN")
if not TOKEN:
    raise SystemExit("错误: 未设置 HELIO_TOKEN 环境变量\n提示: export HELIO_TOKEN='your_token_here'")
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {TOKEN}",
}
PAGE_SIZE = 50

# 当前已知的 Material 字段列表，用于检测 API 是否新增了字段
KNOWN_FIELDS = {
    "id", "name", "brand", "alternativeNames", "description",
    "insertedAt", "updatedAt", "density", "capacity",
    "conductivityX", "conductivityY", "conductivityZ",
    "emissivity", "dryingTimeHours", "heatedChamberRequirement",
    "applicationAreas", "tg", "feedstock", "emailToBuy",
    "maxExtrusionTemp", "minExtrusionTemp", "dryingTemp",
    "bedTempMin", "bedTempMax",
}

# 加热仓要求翻译
CHAMBER_MAP = {
    "NOT_REQUIRED": "不需要",
    "OPTIONAL": "可选",
    "REQUIRED": "必须",
}

# 应用领域翻译
AREA_MAP = {
    "AEROSPACE": "航空航天",
    "ART": "艺术",
    "AUTOMOTIVE": "汽车",
    "CONSTRUCTION_ARCHITECTURE": "建筑",
    "CONSUMER_PRODUCTS": "消费品",
    "DRONES": "无人机",
    "ECO_SUSTAINABILITY": "环保",
    "EDUCATION": "教育",
    "ELECTRICAL": "电气",
    "ELECTRONICS": "电子",
    "ENGINEERING_PROTOTYPING": "工程原型",
    "GENERAL_PROTOTYPING": "通用原型",
    "HOBBY": "爱好",
    "INDUSTRIAL_PROTOTYPING": "工业原型",
    "INTERIOR_DESIGN": "室内设计",
    "LARGE_SCALE_PROTOTYPING": "大型原型",
    "LIGHTING_EQUIPMENT": "照明",
    "LOW_TEMP_MOLD": "低温模具",
    "MARINE": "船舶",
    "MED_TEMP_MOLD": "中温模具",
    "MEDICAL": "医疗",
    "OUTDOOR_EQUIPMENT": "户外",
    "ROBOTICS": "机器人",
    "TOOLING_MANUFACTURING": "工装制造",
    "WEARABLES": "穿戴设备",
}

console = Console(width=300)


def query(gql, variables=None):
    resp = requests.post(API_URL, json={"query": gql, "variables": variables or {}}, headers=HEADERS)
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]


def fetch_summary():
    return query("{ materialsSummary { count desktopMaterials lfamMaterials experimentalMaterials brands } }")["materialsSummary"]


def check_new_fields():
    """通过 introspection 检测 Material 类型是否有新增字段。"""
    gql = '{ __type(name: "Material") { fields { name } } }'
    data = query(gql)
    api_fields = {f["name"] for f in data["__type"]["fields"]}
    new_fields = api_fields - KNOWN_FIELDS
    if new_fields:
        console.print(f"  [bold red][!] 检测到新字段: {', '.join(sorted(new_fields))}, 请更新代码[/]")
    else:
        console.print("  字段无变更")
    return new_fields


def fetch_all_materials():
    gql = """
    query($page: Int, $pageSize: Int) {
      materials(page: $page, pageSize: $pageSize) {
        pages
        pageInfo { hasNextPage }
        objects {
          ... on Material {
            id name feedstock
            brand { name }
            alternativeNames { bambustudio }
            description
            minExtrusionTemp maxExtrusionTemp
            bedTempMin bedTempMax
            dryingTemp dryingTimeHours
            density tg capacity
            conductivityX conductivityY conductivityZ
            emissivity
            heatedChamberRequirement
            applicationAreas
            emailToBuy
            insertedAt updatedAt
          }
        }
      }
    }
    """
    all_materials = []
    page = 1
    while True:
        data = query(gql, {"page": page, "pageSize": PAGE_SIZE})
        materials = data["materials"]
        all_materials.extend(materials["objects"])
        console.print(f"  第 {page}/{materials['pages']} 页, 获取 {len(materials['objects'])} 条")
        if not materials["pageInfo"]["hasNextPage"]:
            break
        page += 1
    return all_materials


def k_to_c(k):
    if k is None:
        return None
    return round(k - 273.15)


def clean(s):
    if not s:
        return ""
    for ch in ("\u2122", "\u00ae", "\u00a9"):
        s = s.replace(ch, "")
    return s.strip()


def fmt_temp_range(lo_k, hi_k):
    lo = k_to_c(lo_k)
    hi = k_to_c(hi_k)
    if lo is not None and hi is not None:
        return f"{lo}~{hi}" if lo != hi else str(lo)
    return "-"


def fmt_val(v, fmt=".0f"):
    if v is None:
        return "-"
    return f"{v:{fmt}}"


def translate_chamber(val):
    if not val:
        return "-"
    return CHAMBER_MAP.get(val, val)


def translate_areas(areas):
    if not areas:
        return "-"
    return ", ".join(AREA_MAP.get(a, a) for a in areas)


def build_table(material_list, title):
    table = Table(title=title, show_lines=False, pad_edge=False, expand=False)
    table.add_column("品牌", style="cyan", no_wrap=True)
    table.add_column("名称", style="white", no_wrap=True)
    table.add_column("挤出温度", justify="right")
    table.add_column("热床温度", justify="right")
    table.add_column("干燥温度", justify="right")
    table.add_column("干燥h", justify="right")
    table.add_column("密度", justify="right")
    table.add_column("Tg(玻璃化转变温度)", justify="right")
    table.add_column("比热容", justify="right")
    table.add_column("导热X", justify="right")
    table.add_column("导热Y", justify="right")
    table.add_column("导热Z", justify="right")
    table.add_column("发射率", justify="right")
    table.add_column("加热仓", justify="center")
    table.add_column("应用领域", style="dim")

    for m in sorted(material_list, key=lambda x: (x["brand"]["name"], x["name"])):
        table.add_row(
            clean(m["brand"]["name"]),
            clean(m["name"]),
            fmt_temp_range(m.get("minExtrusionTemp"), m.get("maxExtrusionTemp")),
            fmt_temp_range(m.get("bedTempMin"), m.get("bedTempMax")),
            fmt_val(k_to_c(m.get("dryingTemp"))),
            fmt_val(m.get("dryingTimeHours")),
            fmt_val(m.get("density")),
            fmt_val(m.get("tg")),
            fmt_val(m.get("capacity")),
            fmt_val(m.get("conductivityX"), ".3f"),
            fmt_val(m.get("conductivityY"), ".3f"),
            fmt_val(m.get("conductivityZ"), ".3f"),
            fmt_val(m.get("emissivity"), ".2f"),
            translate_chamber(m.get("heatedChamberRequirement")),
            translate_areas(m.get("applicationAreas")),
        )
    return table


def main():
    # 1. 总览
    summary = fetch_summary()
    summary_table = Table(title="Helio API 材料总览", show_header=False, expand=False)
    summary_table.add_column("项目", style="bold")
    summary_table.add_column("数量", justify="right", style="green")
    summary_table.add_row("总数", str(summary["count"]))
    summary_table.add_row("桌面级", str(summary["desktopMaterials"]))
    summary_table.add_row("LFAM", str(summary["lfamMaterials"]))
    summary_table.add_row("实验性", str(summary["experimentalMaterials"]))
    summary_table.add_row("品牌数", str(summary["brands"]))
    console.print(summary_table)
    console.print()

    # 2. 检测新字段
    console.print("正在检测 API 字段变更...")
    check_new_fields()
    console.print()

    # 3. 拉取全部材料
    console.print("正在拉取所有材料...")
    materials = fetch_all_materials()
    console.print(f"\n实际获取: [bold]{len(materials)}[/] 种材料")
    if len(materials) < summary["count"]:
        console.print(f"  (平台共 {summary['count']} 种, 当前 PAT 仅可访问 {len(materials)} 种)")
    console.print()

    # 4. 按 feedstock 分类输出
    filament = [m for m in materials if m["feedstock"] == "FILAMENT"]
    pellet = [m for m in materials if m["feedstock"] == "PELLET"]

    if filament:
        console.print(build_table(filament, f"FILAMENT 线材 ({len(filament)}种)"))
        console.print()
    if pellet:
        console.print(build_table(pellet, f"PELLET 颗粒料 ({len(pellet)}种)"))

    # 5. 保存 Markdown 文件
    md_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "README.md")
    save_markdown(summary, materials, md_path)
    console.print(f"\n已保存到 [bold]{md_path}[/]")


def md_table_row(m):
    """生成一行 Markdown 表格数据。"""
    return (
        f"| {clean(m['brand']['name'])} "
        f"| {clean(m['name'])} "
        f"| {fmt_temp_range(m.get('minExtrusionTemp'), m.get('maxExtrusionTemp'))} "
        f"| {fmt_temp_range(m.get('bedTempMin'), m.get('bedTempMax'))} "
        f"| {fmt_val(k_to_c(m.get('dryingTemp')))} "
        f"| {fmt_val(m.get('dryingTimeHours'))} "
        f"| {fmt_val(m.get('density'))} "
        f"| {fmt_val(m.get('tg'))} "
        f"| {fmt_val(m.get('capacity'))} "
        f"| {fmt_val(m.get('conductivityX'), '.3f')} "
        f"| {fmt_val(m.get('conductivityY'), '.3f')} "
        f"| {fmt_val(m.get('conductivityZ'), '.3f')} "
        f"| {fmt_val(m.get('emissivity'), '.2f')} "
        f"| {translate_chamber(m.get('heatedChamberRequirement'))} "
        f"| {translate_areas(m.get('applicationAreas'))} |"
    )


MD_HEADER = "| 品牌 | 名称 | 挤出温度 | 热床温度 | 干燥温度 | 干燥h | 密度 | Tg(玻璃化转变温度) | 比热容 | 导热X | 导热Y | 导热Z | 发射率 | 加热仓 | 应用领域 |"
MD_SEP = "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: | --- |"


def save_markdown(summary, materials, path):
    filament = sorted(
        [m for m in materials if m["feedstock"] == "FILAMENT"],
        key=lambda x: (x["brand"]["name"], x["name"]),
    )
    pellet = sorted(
        [m for m in materials if m["feedstock"] == "PELLET"],
        key=lambda x: (x["brand"]["name"], x["name"]),
    )

    lines = [
        f"# Helio API 材料列表",
        f"",
        f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f">",
        f"> 总数: {summary['count']} | 桌面级: {summary['desktopMaterials']} | LFAM: {summary['lfamMaterials']} | 实验性: {summary['experimentalMaterials']} | 品牌: {summary['brands']}",
        f">",
        f"> 实际获取: {len(materials)} 种",
        f"",
        f"## FILAMENT 线材 ({len(filament)}种)",
        f"",
        MD_HEADER,
        MD_SEP,
    ]
    for m in filament:
        lines.append(md_table_row(m))

    lines += [
        f"",
        f"## PELLET 颗粒料 ({len(pellet)}种)",
        f"",
        MD_HEADER,
        MD_SEP,
    ]
    for m in pellet:
        lines.append(md_table_row(m))

    lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
