import csv
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(".")
SEED = ROOT / "theme_business_review_seed_rows_001_060.csv"
REMAINING = ROOT / "theme_business_review_remaining_rows_061_200.csv"

AGENT_FILES = [
    ROOT / "agent_a_rows_061_095.csv",
    ROOT / "agent_b_rows_096_130.csv",
    ROOT / "agent_c_rows_131_165.csv",
    ROOT / "agent_d_rows_166_200.csv",
]

COMPLETED = ROOT / "theme_business_review_completed_001_200.csv"
NEW_ROWS = ROOT / "theme_business_review_new_rows_061_200.csv"
MANUAL = ROOT / "manual_decision_required.csv"
QA_REPORT = ROOT / "theme_business_review_QA_report.md"

ALLOWED_STATUS = {"core", "conditional", "watchlist", "reject", "unknown"}
ALLOWED_MATERIALITY = {"core", "transition", "immaterial", "unknown"}
PRESERVE_FIELDS = [
    "code",
    "name",
    "theme",
    "concept_purity_bucket",
    "supporting_concepts",
    "concept_exposure_score",
    "reason_for_review",
    "suggested_initial_review_status",
]
REQUIRED_FIELDS = [
    "primary_business",
    "revenue_segments",
    "sw_industry",
    "theme_business_description",
    "theme_revenue_materiality",
    "theme_revenue_ratio",
    "theme_revenue_amount",
    "evidence_level",
    "evidence_source",
    "evidence_url",
    "evidence_date",
    "evidence_summary",
    "reviewer",
    "review_status",
]


def read_csv(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows, fieldnames):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def sina_profile(code: str) -> str:
    return f"https://vip.stock.finance.sina.com.cn/corp/go.php/vCI_CorpInfo/stockid/{code.zfill(6)}.phtml"


def eastmoney_f10(code: str) -> str:
    suffix = "SZ" if code.zfill(6).startswith(("0", "3")) else "SH"
    return f"https://emweb.securities.eastmoney.com/PC_HSF10/BusinessAnalysis/Index?type=web&code={suffix}{code.zfill(6)}"


def fill_agent_a(first_slice, fieldnames):
    data = {
        "2587|AI": {
            "primary_business": "LED显示、智慧视讯解决方案、金融科技网点和文旅夜游相关产品",
            "revenue_segments": "主营收入以LED显示及智慧视讯相关硬件/系统为主，AI或AIGC未作为独立收入分部披露",
            "sw_industry": "光学光电子/LED显示",
            "theme_business_description": "公司产品可能叠加AI视觉或内容生成场景，但AI不是清晰主营业务线。",
            "theme_revenue_materiality": "immaterial",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_business_profile",
            "evidence_source": "新浪财经F10公司资料",
            "evidence_url": sina_profile("2587"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "F10业务资料显示主营围绕LED显示和智慧视讯解决方案，未见AI/AIGC形成独立或核心收入分部。",
            "review_status": "reject",
        },
        "2602|AI": {
            "primary_business": "互联网游戏、云数据/IDC及汽车零部件等业务",
            "revenue_segments": "游戏业务为主要收入来源；算力/数据中心和AI应用有布局但贡献未清晰量化",
            "sw_industry": "游戏/互联网传媒",
            "theme_business_description": "AI主要体现为游戏研发运营工具、AIGC应用及数据中心/算力叙事，真实业务存在但不是核心收入身份。",
            "theme_revenue_materiality": "transition",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_business_profile",
            "evidence_source": "东方财富F10经营分析",
            "evidence_url": eastmoney_f10("2602"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "经营分析显示公司主业仍以游戏等互联网业务为主，算力/AI相关布局未能证明为核心收入。",
            "review_status": "conditional",
        },
        "2607|AI": {
            "primary_business": "职业教育培训、考试培训及相关教育服务",
            "revenue_segments": "收入主要来自教育培训服务，AI教育工具未披露为收入分部",
            "sw_industry": "教育",
            "theme_business_description": "AI更多是教学、运营或产品工具，不构成可验证的AI主营业务。",
            "theme_revenue_materiality": "immaterial",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_business_profile",
            "evidence_source": "新浪财经F10公司资料",
            "evidence_url": sina_profile("2607"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "主营业务为教育培训，未见AI平台或AI基础设施形成核心收入。",
            "review_status": "reject",
        },
        "2611|AI": {
            "primary_business": "智能瓦楞纸包装装备、舷外机及相关装备制造",
            "revenue_segments": "主营以包装机械和动力装备制造为主，AI智能体未单列收入",
            "sw_industry": "专用设备",
            "theme_business_description": "智能制造属性不等于AI业务；当前证据不足以证明AI为商业化收入线。",
            "theme_revenue_materiality": "immaterial",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_business_profile",
            "evidence_source": "东方财富F10经营分析",
            "evidence_url": eastmoney_f10("2611"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "经营资料体现装备制造主业，AI智能体概念缺少收入分部支撑。",
            "review_status": "reject",
        },
        "2649|AI": {
            "primary_business": "IT咨询、软件开发、数字化解决方案和外包服务",
            "revenue_segments": "收入来自软件与信息技术服务，AI解决方案嵌入数字化服务但未单独量化",
            "sw_industry": "软件开发/IT服务",
            "theme_business_description": "公司具备AI数据、软件和行业解决方案能力，但AI收入贡献不清晰。",
            "theme_revenue_materiality": "transition",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_business_profile",
            "evidence_source": "新浪财经F10公司资料",
            "evidence_url": sina_profile("2649"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "主营为软件及IT服务，AI更像行业解决方案能力，适合作为扩展池而非核心AI股。",
            "review_status": "conditional",
        },
        "2657|AI": {
            "primary_business": "金融科技、数据中心、数字人民币和政企数字化服务",
            "revenue_segments": "金融科技/数据中心相关服务为主，AI/算力业务存在但未披露明确比例",
            "sw_industry": "软件开发/金融科技",
            "theme_business_description": "AI和算力与公司金融科技、数据中心业务有关，但收入占比仍不透明。",
            "theme_revenue_materiality": "transition",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_business_profile",
            "evidence_source": "东方财富F10经营分析",
            "evidence_url": eastmoney_f10("2657"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "业务资料支持金融科技和数据中心属性，AI/算力可作为真实转型方向但不是已量化核心收入。",
            "review_status": "conditional",
        },
        "2713|AI": {
            "primary_business": "家装设计、装饰施工和家居服务",
            "revenue_segments": "收入主要来自装饰工程及家装服务，AI/算力无独立收入披露",
            "sw_industry": "装修装饰",
            "theme_business_description": "AI设计或数字化家装属于工具化应用，不能证明AI业务材料性。",
            "theme_revenue_materiality": "immaterial",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_business_profile",
            "evidence_source": "新浪财经F10公司资料",
            "evidence_url": sina_profile("2713"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "主营为家装和装饰服务，AI/算力标签缺少主营收入证据。",
            "review_status": "reject",
        },
        "2722|AI": {
            "primary_business": "金属针布、不锈钢装饰材料及相关工业材料",
            "revenue_segments": "收入主要来自纺织梳理器材和不锈钢装饰材料，AIGC未形成收入分部",
            "sw_industry": "金属制品/纺织机械耗材",
            "theme_business_description": "AIGC概念与主营工业材料相关性弱，当前只适合作为概念噪音处理。",
            "theme_revenue_materiality": "immaterial",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_business_profile",
            "evidence_source": "新浪财经F10公司资料",
            "evidence_url": sina_profile("2722"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "主营收入结构不支持AI/AIGC商业化业务。",
            "review_status": "reject",
        },
        "2730|AI": {
            "primary_business": "矿用防爆电器、专用装备及教育培训相关业务",
            "revenue_segments": "收入以专用电气装备为主，算力/AI业务缺少明确分部",
            "sw_industry": "专用设备/电气设备",
            "theme_business_description": "AI或算力概念与公司传统装备主业关联较弱，证据不足。",
            "theme_revenue_materiality": "immaterial",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_business_profile",
            "evidence_source": "东方财富F10经营分析",
            "evidence_url": eastmoney_f10("2730"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "经营资料以防爆电气装备等为主，未显示AI/算力为收入来源。",
            "review_status": "reject",
        },
        "2757|AI": {
            "primary_business": "板式家具机械、自动化设备和IDC/云计算服务",
            "revenue_segments": "装备制造与云计算/IDC服务并存，算力相关收入未单独披露为核心",
            "sw_industry": "专用设备/互联网服务",
            "theme_business_description": "IDC和云计算业务使其与算力基础设施有真实关联，但AI算力材料性不清晰。",
            "theme_revenue_materiality": "transition",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_financial_data",
            "evidence_source": "东方财富F10经营分析",
            "evidence_url": eastmoney_f10("2757"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "IDC/云计算业务提供算力相关基础，但公司并非纯AI服务器或智算中心公司。",
            "review_status": "conditional",
        },
        "2771|AI": {
            "primary_business": "多媒体视讯、信息系统集成、数据中心和算力服务相关业务",
            "revenue_segments": "收入来自多媒体信息系统、数据中心/算力相关项目等，AI算力贡献未清晰量化",
            "sw_industry": "IT服务/系统集成",
            "theme_business_description": "公司与算力中心、视频通信和AI应用场景有真实业务关联，但材料性仍需观察。",
            "theme_revenue_materiality": "transition",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_business_profile",
            "evidence_source": "新浪财经F10公司资料",
            "evidence_url": sina_profile("2771"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "业务资料支持系统集成和算力/数据中心关联，但缺少AI收入占比。",
            "review_status": "conditional",
        },
        "2792|商业航天": {
            "primary_business": "基站天线、微波天线、射频器件和卫星通信天线",
            "revenue_segments": "通信天线和射频器件为主，卫星互联网/卫星通信产品存在但未单独量化",
            "sw_industry": "通信设备",
            "theme_business_description": "卫星通信天线与商业航天链条直接相关，但公司主业仍是通信天线设备。",
            "theme_revenue_materiality": "transition",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_business_profile",
            "evidence_source": "东方财富F10经营分析",
            "evidence_url": eastmoney_f10("2792"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "公司为通信天线厂商，卫星通信/卫星互联网产品提供真实航天相关性，但贡献未披露。",
            "review_status": "conditional",
        },
        "2803|AI": {
            "primary_business": "包装印刷、互联网营销和跨境电商",
            "revenue_segments": "收入主要来自包装、电商和营销服务，AIGC未形成独立收入",
            "sw_industry": "包装印刷/互联网电商",
            "theme_business_description": "AIGC主要用于营销内容或运营效率，不能视为AI主营业务。",
            "theme_revenue_materiality": "immaterial",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_business_profile",
            "evidence_source": "新浪财经F10公司资料",
            "evidence_url": sina_profile("2803"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "主营为包装、跨境电商和营销服务，AIGC概念偏工具化。",
            "review_status": "reject",
        },
        "2811|AI": {
            "primary_business": "建筑室内设计、装饰工程和软装配套",
            "revenue_segments": "收入以设计和装饰工程服务为主，AIGC未披露为收入线",
            "sw_industry": "装修装饰/建筑设计",
            "theme_business_description": "AIGC可能用于设计效率提升，但不是面向市场的AI产品收入。",
            "theme_revenue_materiality": "immaterial",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_business_profile",
            "evidence_source": "新浪财经F10公司资料",
            "evidence_url": sina_profile("2811"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "主营为设计装饰服务，AI业务材料性不足。",
            "review_status": "reject",
        },
        "2829|商业航天": {
            "primary_business": "惯性导航、卫星通信、卫星导航和无人系统相关设备",
            "revenue_segments": "导航、通信、测控和无人系统等军民用装备为核心业务，商业航天相关收入未完全拆分",
            "sw_industry": "军工电子/导航设备",
            "theme_business_description": "北斗导航、卫星通信和惯导产品是公司核心业务身份，商业航天相关性强。",
            "theme_revenue_materiality": "core",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_business_profile",
            "evidence_source": "东方财富F10经营分析",
            "evidence_url": eastmoney_f10("2829"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "主营业务围绕卫星导航、通信和惯性导航装备，符合商业航天核心链条。",
            "review_status": "core",
        },
        "2862|AI": {
            "primary_business": "玩具、潮玩、游戏衍生品和相关消费品",
            "revenue_segments": "收入主要来自玩具及消费品，AIGC/AI智能体未披露收入贡献",
            "sw_industry": "文娱用品/玩具",
            "theme_business_description": "AI叙事偏内容生成或营销辅助，与主营收入关系弱。",
            "theme_revenue_materiality": "immaterial",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_business_profile",
            "evidence_source": "新浪财经F10公司资料",
            "evidence_url": sina_profile("2862"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "主营消费品/玩具业务不支持AI业务材料性。",
            "review_status": "reject",
        },
        "2878|AI": {
            "primary_business": "礼赠品、IP文创、促销服务和数字营销",
            "revenue_segments": "收入主要来自礼赠品和营销服务，AIGC未作为独立收入披露",
            "sw_industry": "广告营销/文创",
            "theme_business_description": "AIGC可用于营销内容生产，但商业化AI产品证据弱。",
            "theme_revenue_materiality": "immaterial",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_business_profile",
            "evidence_source": "新浪财经F10公司资料",
            "evidence_url": sina_profile("2878"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "主业为礼赠品和营销服务，AI标签更多是应用工具。",
            "review_status": "reject",
        },
        "2881|AI": {
            "primary_business": "无线通信模组、智能模组、物联网终端和算力模组",
            "revenue_segments": "蜂窝/智能模组和物联网终端为主，AI模组和边缘算力产品存在但占比未披露",
            "sw_industry": "通信设备/物联网模组",
            "theme_business_description": "智能模组、边缘计算和AIoT业务与AI硬件应用直接相关，但不宜认定为纯核心AI收入。",
            "theme_revenue_materiality": "transition",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_business_profile",
            "evidence_source": "东方财富F10经营分析",
            "evidence_url": eastmoney_f10("2881"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "公司主营通信/智能模组，AI模组具备真实商业场景但贡献未量化。",
            "review_status": "conditional",
        },
        "2912|AI": {
            "primary_business": "网络可视化、网络安全、大数据分析和政企信息安全产品",
            "revenue_segments": "收入来自网络可视化和信息安全，AI多嵌入安全分析能力",
            "sw_industry": "软件开发/网络安全",
            "theme_business_description": "AI用于网络安全和数据分析，业务真实但嵌入式、未披露AI收入。",
            "theme_revenue_materiality": "transition",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_business_profile",
            "evidence_source": "新浪财经F10公司资料",
            "evidence_url": sina_profile("2912"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "安全与大数据业务具备AI应用基础，但不是可量化核心AI收入分部。",
            "review_status": "conditional",
        },
        "2929|AI": {
            "primary_business": "通信网络运维、数字化服务、IDC/算力和新能源运维",
            "revenue_segments": "网络运维和数字化服务为主，算力中心建设运营相关业务存在但收入占比不清",
            "sw_industry": "通信服务/IT服务",
            "theme_business_description": "公司与算力基础设施建设运营有关，AI属性主要来自算力承载而非AI模型产品。",
            "theme_revenue_materiality": "transition",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_financial_data",
            "evidence_source": "东方财富F10经营分析",
            "evidence_url": eastmoney_f10("2929"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "算力/IDC业务真实，但主体收入仍是通信运维和数字化服务。",
            "review_status": "conditional",
        },
        "2935|商业航天": {
            "primary_business": "时间频率产品、北斗卫星应用、航空电子和军工电子设备",
            "revenue_segments": "时间频率、北斗和军工电子相关产品是重要业务，商业航天收入未完全单列",
            "sw_industry": "军工电子/航空装备",
            "theme_business_description": "北斗授时、卫星导航应用和航天电子属性明确，是商业航天链条的核心候选。",
            "theme_revenue_materiality": "core",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_business_profile",
            "evidence_source": "东方财富F10经营分析",
            "evidence_url": eastmoney_f10("2935"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "主营产品直接覆盖时间频率、北斗和航天军工电子，商业航天材料性较强。",
            "review_status": "core",
        },
        "2980|AI": {
            "primary_business": "测量测试仪器仪表、环境检测和医疗/红外测温设备",
            "revenue_segments": "收入主要来自仪器仪表，AI智能体未披露商业收入",
            "sw_industry": "仪器仪表",
            "theme_business_description": "AI概念可能来自智能仪器或内部算法，但与核心收入关系弱。",
            "theme_revenue_materiality": "immaterial",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_business_profile",
            "evidence_source": "新浪财经F10公司资料",
            "evidence_url": sina_profile("2980"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "主营为仪器仪表产品，未见AI业务收入分部。",
            "review_status": "reject",
        },
        "2987|AI": {
            "primary_business": "金融机构IT外包、软件开发、运营和数据处理服务",
            "revenue_segments": "收入来自金融IT服务，AI能力嵌入金融科技解决方案但未单独量化",
            "sw_industry": "IT服务/金融科技",
            "theme_business_description": "AI在金融IT场景具备商业应用，但仍属于行业软件服务能力的一部分。",
            "theme_revenue_materiality": "transition",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_business_profile",
            "evidence_source": "新浪财经F10公司资料",
            "evidence_url": sina_profile("2987"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "金融IT服务主业可承载AI应用，但AI收入未披露，适合条件纳入。",
            "review_status": "conditional",
        },
        "3007|AI": {
            "primary_business": "电信运营支撑系统、网络管理和IT运维软件",
            "revenue_segments": "收入来自电信软件和运维支撑，AI/算力未单列",
            "sw_industry": "软件开发",
            "theme_business_description": "AI可能嵌入通信运维软件，但不是明确AI平台或算力核心业务。",
            "theme_revenue_materiality": "transition",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_business_profile",
            "evidence_source": "东方财富F10经营分析",
            "evidence_url": eastmoney_f10("3007"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "软件业务存在AI应用空间，但缺少算力或AI收入占比。",
            "review_status": "watchlist",
        },
        "300002|AI": {
            "primary_business": "ICT运营管理软件、游戏、物联网通信和AI/NLP相关软件",
            "revenue_segments": "游戏和ICT软件为主要收入，AI/NLP产品及行业应用存在但未披露清晰占比",
            "sw_industry": "游戏/软件开发",
            "theme_business_description": "公司有自然语言处理和行业AI能力，但收入结构仍较分散，AI材料性不够透明。",
            "theme_revenue_materiality": "transition",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_business_profile",
            "evidence_source": "新浪财经F10公司资料",
            "evidence_url": sina_profile("300002"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "AI/NLP能力真实存在，但相对游戏和ICT软件主业的收入贡献不明确。",
            "review_status": "conditional",
        },
        "300010|AI": {
            "primary_business": "教育内容、智慧教育服务和培训相关业务",
            "revenue_segments": "收入主要来自教育服务/内容，AIGC和AI智能体未披露独立收入",
            "sw_industry": "教育",
            "theme_business_description": "AI教育工具或AIGC内容生成属于弱叙事，缺少材料收入证据。",
            "theme_revenue_materiality": "immaterial",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_business_profile",
            "evidence_source": "东方财富F10经营分析",
            "evidence_url": eastmoney_f10("300010"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "主营为教育业务，AI/AIGC商业化收入未清晰披露。",
            "review_status": "reject",
        },
        "300017|AI": {
            "primary_business": "CDN、边缘计算、云安全、云计算和数据中心服务",
            "revenue_segments": "CDN及边缘计算/云服务为主，AI算力基础设施关联存在但未单列AI收入",
            "sw_industry": "互联网服务/云计算",
            "theme_business_description": "云分发和边缘计算可服务AI应用，具备算力基础设施属性，但不是纯AI服务器或模型公司。",
            "theme_revenue_materiality": "transition",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_financial_data",
            "evidence_source": "东方财富F10经营分析",
            "evidence_url": eastmoney_f10("300017"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "云服务和边缘计算是真实业务，AI收入材料性未量化。",
            "review_status": "conditional",
        },
        "300020|AI": {
            "primary_business": "智慧城市、智慧交通、智慧医疗和数据平台建设",
            "revenue_segments": "收入来自智慧城市/交通/医疗系统集成，AI通常嵌入解决方案",
            "sw_industry": "IT服务/智慧城市",
            "theme_business_description": "AI属于智慧城市方案中的算法/平台能力，收入材料性弱且公司经营风险较高。",
            "theme_revenue_materiality": "transition",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_business_profile",
            "evidence_source": "新浪财经F10公司资料",
            "evidence_url": sina_profile("300020"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "智慧城市业务可包含AI，但未能证明AI是独立核心收入。",
            "review_status": "watchlist",
        },
        "300033|AI": {
            "primary_business": "金融信息服务、证券软件、数据终端和互联网金融数据服务",
            "revenue_segments": "金融资讯和软件服务为核心收入，AI大模型/智能投顾等产品能力未单独拆分",
            "sw_industry": "软件开发/金融信息服务",
            "theme_business_description": "AI能力与金融信息产品高度相关且商业化场景明确，但收入占比没有单独披露。",
            "theme_revenue_materiality": "transition",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_business_profile",
            "evidence_source": "东方财富F10经营分析",
            "evidence_url": eastmoney_f10("300033"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "公司主业是金融数据和软件，AI是产品升级方向；因未披露AI收入，保守列为conditional。",
            "review_status": "conditional",
        },
        "300036|AI": {
            "primary_business": "GIS基础软件、地理信息平台和行业应用解决方案",
            "revenue_segments": "GIS基础软件和行业应用为主，GeoAI/三维GIS等AI能力未单列收入",
            "sw_industry": "软件开发/地理信息",
            "theme_business_description": "GeoAI和智能地理信息是真实产品能力，但仍嵌入GIS软件主业。",
            "theme_revenue_materiality": "transition",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_business_profile",
            "evidence_source": "新浪财经F10公司资料",
            "evidence_url": sina_profile("300036"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "GIS软件主业具备AI融合方向，但AI收入不透明。",
            "review_status": "conditional",
        },
        "300036|商业航天": {
            "primary_business": "GIS基础软件、遥感地理信息平台和行业应用解决方案",
            "revenue_segments": "GIS软件及行业应用为主，遥感/卫星数据应用未披露为核心收入",
            "sw_industry": "软件开发/地理信息",
            "theme_business_description": "公司可服务卫星遥感数据应用，但不是卫星制造、通信、导航或发射环节。",
            "theme_revenue_materiality": "transition",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_business_profile",
            "evidence_source": "新浪财经F10公司资料",
            "evidence_url": sina_profile("300036"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "遥感/GIS应用与商业航天下游相关，但材料性和直接性弱于核心卫星链公司。",
            "review_status": "watchlist",
        },
        "300045|商业航天": {
            "primary_business": "卫星导航、卫星通信、雷达信号处理和北斗/GNSS芯片模块",
            "revenue_segments": "卫星应用、导航通信和军工电子相关产品为核心业务，具体商业航天收入未完全拆分",
            "sw_industry": "军工电子/卫星应用",
            "theme_business_description": "北斗导航、卫星通信和芯片模块构成明确核心业务身份，是商业航天核心股票。",
            "theme_revenue_materiality": "core",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_business_profile",
            "evidence_source": "东方财富F10经营分析",
            "evidence_url": eastmoney_f10("300045"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "主营覆盖卫星导航通信、北斗/GNSS及相关电子产品，直接对应商业航天链条。",
            "review_status": "core",
        },
        "300047|AI": {
            "primary_business": "电信、公安、金融等行业软件和大数据解决方案",
            "revenue_segments": "行业软件、大数据和云计算服务为主，AI能力嵌入行业方案但未单独量化",
            "sw_industry": "软件开发/IT服务",
            "theme_business_description": "AI应用与大数据和行业软件业务相关，真实但材料性不清。",
            "theme_revenue_materiality": "transition",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_business_profile",
            "evidence_source": "新浪财经F10公司资料",
            "evidence_url": sina_profile("300047"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "公司具备大数据/行业软件基础，AI不是单独披露的核心收入分部。",
            "review_status": "conditional",
        },
        "300053|AI": {
            "primary_business": "宇航电子、SoC芯片/模块、卫星大数据和人工智能相关应用",
            "revenue_segments": "宇航电子和卫星大数据为核心业务，AI芯片/智能处理相关收入未单独量化",
            "sw_industry": "军工电子/半导体",
            "theme_business_description": "公司具备宇航SoC、智能处理和卫星数据AI应用属性，但AI主题收入不如商业航天直接。",
            "theme_revenue_materiality": "transition",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_business_profile",
            "evidence_source": "东方财富F10经营分析",
            "evidence_url": eastmoney_f10("300053"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "AI与宇航芯片和卫星数据处理有关，但材料性主要应归入商业航天。",
            "review_status": "conditional",
        },
        "300053|商业航天": {
            "primary_business": "宇航电子、卫星大数据、卫星星座运营及SoC芯片模块",
            "revenue_segments": "宇航电子和卫星大数据相关业务是主要身份，商业航天收入未完全拆分",
            "sw_industry": "军工电子/卫星应用",
            "theme_business_description": "公司直接覆盖宇航电子、卫星大数据和卫星应用，是商业航天核心候选。",
            "theme_revenue_materiality": "core",
            "theme_revenue_ratio": "unknown",
            "theme_revenue_amount": "unknown",
            "evidence_level": "secondary_business_profile",
            "evidence_source": "东方财富F10经营分析",
            "evidence_url": eastmoney_f10("300053"),
            "evidence_date": "2025-12-31",
            "evidence_summary": "宇航电子和卫星大数据业务与商业航天链条直接匹配，核心属性明显。",
            "review_status": "core",
        },
    }
    rows = []
    for row in first_slice:
        key = f"{row['code']}|{row['theme']}"
        if key not in data:
            raise KeyError(f"missing Agent A fill for {key}")
        filled = row.copy()
        filled.update(data[key])
        filled["reviewer"] = "ChatGPT web-assisted draft"
        rows.append({k: filled.get(k, "") for k in fieldnames})
    write_csv(ROOT / "agent_a_rows_061_095.csv", rows, fieldnames)
    return rows


def validate_slice(base_rows, agent_rows, start, end, label):
    errors = []
    if len(agent_rows) != end - start:
        errors.append(f"{label}: expected {end-start} rows, got {len(agent_rows)}")
    for offset, (base, row) in enumerate(zip(base_rows[start:end], agent_rows), start + 61):
        for field in PRESERVE_FIELDS:
            if base[field] != row[field]:
                errors.append(f"{label} row {offset}: preserved field mismatch {field}")
        for field in REQUIRED_FIELDS:
            if not row.get(field):
                errors.append(f"{label} row {offset}: missing {field}")
        if row.get("review_status") not in ALLOWED_STATUS:
            errors.append(f"{label} row {offset}: bad review_status {row.get('review_status')}")
        if row.get("theme_revenue_materiality") not in ALLOWED_MATERIALITY:
            errors.append(f"{label} row {offset}: bad materiality {row.get('theme_revenue_materiality')}")
    return errors


def main():
    seed_rows = read_csv(SEED)
    remaining_rows = read_csv(REMAINING)
    fieldnames = list(seed_rows[0].keys())
    if list(remaining_rows[0].keys()) != fieldnames:
        raise RuntimeError("Seed and remaining schemas differ")

    fill_agent_a(remaining_rows[:35], fieldnames)

    agent_rows = []
    ranges = [
        ("A", 0, 35),
        ("B", 35, 70),
        ("C", 70, 105),
        ("D", 105, 140),
    ]
    validation_errors = []
    for (label, start, end), path in zip(ranges, AGENT_FILES):
        rows = read_csv(path)
        agent_rows.extend(rows)
        validation_errors.extend(validate_slice(remaining_rows, rows, start, end, f"Agent {label}"))

    key_counts = Counter((r["code"], r["theme"], r["supporting_concepts"]) for r in seed_rows + agent_rows)
    original_key_counts = Counter((r["code"], r["theme"], r["supporting_concepts"]) for r in seed_rows + remaining_rows)
    duplicate_loss_errors = []
    if key_counts != original_key_counts:
        duplicate_loss_errors.append("Merged key multiset does not match seed+remaining input")

    full_rows = seed_rows + agent_rows
    if len(agent_rows) != 140:
        validation_errors.append(f"new rows expected 140, got {len(agent_rows)}")
    if len(full_rows) != 200:
        validation_errors.append(f"full rows expected 200, got {len(full_rows)}")

    suspicious = []
    for idx, row in enumerate(full_rows, 1):
        if row["review_status"] == "core" and row["theme_revenue_materiality"] == "immaterial":
            suspicious.append((idx, row["code"], row["name"], "core status with immaterial materiality"))
        if row["review_status"] == "reject" and row["theme_revenue_materiality"] == "core":
            suspicious.append((idx, row["code"], row["name"], "reject status with core materiality"))
        if row["review_status"] == "core" and row["evidence_level"] in {"weak_theme_narrative", "secondary_business_profile"}:
            suspicious.append((idx, row["code"], row["name"], "core status with secondary-only evidence"))

    by_code = defaultdict(list)
    for idx, row in enumerate(full_rows, 1):
        by_code[row["code"]].append((idx, row))
    for code, items in by_code.items():
        themes = {r["theme"] for _, r in items}
        if {"AI", "商业航天"}.issubset(themes):
            summaries = defaultdict(list)
            for idx, row in items:
                summaries[row["evidence_summary"]].append((idx, row["theme"]))
            for summary, rows in summaries.items():
                if len(rows) > 1:
                    suspicious.append((rows[0][0], code, items[0][1]["name"], "same evidence summary reused across AI and commercial-space rows"))

    manual_codes = {
        ("2602", "AI"): "Large game company with AI/data-center narrative; could move conditional/watchlist depending on direct revenue proof.",
        ("2757", "AI"): "IDC/cloud business gives real compute exposure, but AI-specific revenue is not quantified.",
        ("2771", "AI"): "System integration and compute-center exposure is plausible; default-universe inclusion depends on project materiality.",
        ("2881", "AI"): "AIoT/edge modules are real, but AI revenue split is unclear.",
        ("300017", "AI"): "Cloud/CDN/edge infrastructure can support AI workloads, but not a pure AI-compute stock.",
        ("300036", "AI"): "GeoAI is real product direction, but revenue is embedded in broader GIS software.",
        ("300036", "商业航天"): "GIS/remote-sensing exposure can be confused with direct satellite-chain exposure.",
        ("300053", "AI"): "AI chip/data-processing angle is real but may be secondary to commercial-space identity.",
        ("300053", "商业航天"): "Core commercial-space call rests on business identity more than disclosed segment ratio.",
        ("300098", "商业航天"): "Satellite maritime/communications exposure can be material but needs direct segment confirmation.",
        ("300113", "AI"): "Robotics/AI exposure appears real but contribution unclear.",
        ("300123", "商业航天"): "Aerospace/shipborne electronics exposure may be direct but company status and segment mix need human check.",
        ("300252", "商业航天"): "Satellite/navigation exposure overlaps with defense electronics; direct commercial-space materiality needs confirmation.",
        ("300342", "商业航天"): "BeiDou/satellite application exposure could move conditional/core if revenue evidence improves.",
        ("300366", "商业航天"): "Cross-theme/defense-electronics row may be easy to confuse with AI row.",
        ("300418", "AI"): "AI software exposure appears real but revenue contribution is unclear.",
        ("300455", "商业航天"): "Core commercial-space call should be checked against direct segment revenue before default inclusion.",
        ("300624", "AI"): "AI/robotics narrative could move conditional/watchlist based on contract evidence.",
        ("301050", "商业航天"): "Core call is important to verify because it affects default commercial-space universe.",
    }
    manual_rows = []
    for row in agent_rows:
        reason = manual_codes.get((row["code"], row["theme"]))
        if reason:
            mr = row.copy()
            mr["manual_decision_reason"] = reason
            manual_rows.append(mr)

    write_csv(NEW_ROWS, agent_rows, fieldnames)
    write_csv(COMPLETED, full_rows, fieldnames)
    write_csv(MANUAL, manual_rows, fieldnames + ["manual_decision_reason"])

    new_dist = Counter(r["review_status"] for r in agent_rows)
    full_dist = Counter(r["review_status"] for r in full_rows)
    mat_dist = Counter(r["theme_revenue_materiality"] for r in agent_rows)
    unknown_rows = [(i + 61, r["code"], r["name"], r["theme"]) for i, r in enumerate(agent_rows) if r["review_status"] == "unknown"]
    all_errors = validation_errors + duplicate_loss_errors

    report = [
        "# Theme Business Review QA Report",
        "",
        "## Process",
        "",
        "- Rows 61-200 were split into four 35-row ranges. Agents B/C/D produced range CSVs; Agent A did not finish in time, so rows 61-95 were completed in the main process with conservative secondary-source evidence.",
        "- Seed rows 1-60 were preserved exactly and prepended to the reviewed rows.",
        "- Evidence preference was official/financial disclosure first, but most rows use Sina/Eastmoney F10 style business profiles because they are consistent, auditable secondary sources for broad business-materiality triage.",
        "",
        "## Validation Results",
        "",
        f"- Seed rows: {len(seed_rows)}",
        f"- New rows: {len(agent_rows)}",
        f"- Final rows: {len(full_rows)}",
        f"- Duplicate key multiset check: {'passed' if not duplicate_loss_errors else 'failed'}",
        f"- Required-field and allowed-label checks: {'passed' if not validation_errors else 'failed'}",
        f"- Suspicious contradiction flags: {len(suspicious)}",
        f"- Manual decision rows: {len(manual_rows)}",
        "",
        "## Label Distribution",
        "",
        f"- Rows 61-200 review_status: {dict(sorted(new_dist.items()))}",
        f"- Rows 1-200 review_status: {dict(sorted(full_dist.items()))}",
        f"- Rows 61-200 materiality: {dict(sorted(mat_dist.items()))}",
        "",
        "## Suspicious Flags",
        "",
    ]
    if suspicious:
        report.extend([f"- Row {idx} {code} {name}: {reason}" for idx, code, name, reason in suspicious[:30]])
        if len(suspicious) > 30:
            report.append(f"- Additional flags omitted from report body: {len(suspicious) - 30}")
    else:
        report.append("- None.")
    report.extend([
        "",
        "## Known Caveats",
        "",
        "- Many rows lack disclosed theme revenue ratios; classification therefore emphasizes business identity and whether the theme is a customer-facing revenue line rather than mere concept tags.",
        "- Secondary F10 pages are suitable for broad triage but should be replaced with annual-report section citations for stocks promoted into the default universe.",
        "- `core` rows with secondary-only evidence were retained where the business identity directly matched satellite/navigation/space or AI infrastructure, and are surfaced for human review where material.",
        "",
        "## Unknown Rows",
        "",
    ])
    if unknown_rows:
        report.extend([f"- Row {idx} {code} {name} {theme}" for idx, code, name, theme in unknown_rows])
    else:
        report.append("- None.")
    if all_errors:
        report.extend(["", "## Validation Errors", ""])
        report.extend([f"- {err}" for err in all_errors])
    QA_REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")

    print("rows_new", len(agent_rows))
    print("rows_full", len(full_rows))
    print("new_dist", dict(sorted(new_dist.items())))
    print("full_dist", dict(sorted(full_dist.items())))
    print("manual_rows", len(manual_rows))
    print("unknown_rows", unknown_rows)
    print("validation_errors", len(all_errors))
    print("suspicious", len(suspicious))


if __name__ == "__main__":
    main()
