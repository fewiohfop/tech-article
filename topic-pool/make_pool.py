#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""make_pool.py —— 2026-10-09 选题池（重做版，独立脚本，不依赖历史版本）。

输入（都在本目录）：
    tophub_items.json   17 个 tophub 节点（7 AI + 10 科技），265 条
    hn_items.json       Hacker News top，23 条（分数=热度）
    hf_models.json      HuggingFace trending 模型，30 条
输出：
    C:\\选题\\今日AI科技选题池_<date>.html

设计原则（用户 2026-10-09 明确：别再改来改去）：
  1. **不做赛道配额**。昨天加的「每赛道最多 N 条」把好条目摊薄成 12 个赛道各 1-3 条，
     聚焦度全丢 —— 这一版不设任何赛道上限。
  2. **排序只看三件事**：跨源命中数 → 钩子强度 → 热度值。
  3. **不做自我否定式备注**，不写「缺哪一手源」这类内部核查话术。
  4. 条数上限 30 条单源 + 全部多源；宁多勿少，让用户自己挑。
"""
import html
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.environ.get('TOPIC_DIR', r'C:\选题')

# ---------- 赛道判定（只用于打标签，不用于配额） ----------
# ⚠️ 顺序即优先级：**具体品类在前，泛化词在后**。
# 反例（2026-10-09 实测）：「AI模型」放在最前 + 含 '模型' 二字 →
# 苹果 iPhone Air 2 爆料被标成「AI/AI模型」，纯消费电子稿全被污染。
TRACK_RULES = [
    ('消费电子', ['iphone', 'ipad', 'macbook', 'mac ', 'apple', 'vision pro', 'homepod',
                  'airpods', 'surface', 'windows', 'android', 'pixel', 'nintendo', 'switch',
                  '耳机', '手表', '平板', '笔记本', '手机', '屏', '摄像头', '音箱', '键盘',
                  '充电器', '电池', '内存条', '固态硬盘', '路由器', '相机', '电视', '游戏机',
                  '显卡', '台式机', '一体机', 'imac', 'macos', 'ios', 'android']),
    ('芯片半导体', ['nvidia', '英伟达', 'amd', 'intel', '英特尔', '高通', 'qualcomm', 'mediatek',
                    '联发科', '台积电', 'tsmc', 'asml', 'arm ', 'cpu', 'gpu', 'npu', 'asic',
                    '芯片', '半导体', '晶圆', '制程', '光刻', '封装', 'hbm', 'dram', 'nand',
                    '内存芯片', '骁龙', '天玑', '麒麟', '算力', '显卡', '4090', '5090']),
    ('智能汽车', ['汽车', '车企', '车型', 'suv', '轿车', 'mpv', '驾驶', '自动驾驶',
                  'autonomous', 'robotaxi', '智驾', '辅助驾驶', '新能源车', 'tesla', '特斯拉',
                  '比亚迪', '小鹏', '蔚来', '理想汽车', '尊界', '问界', '极氪', '岚图',
                  '智界', '享界', 'su7', 'yutong', '卡车', '货车', '停车', '充电桩', '刹车',
                  '电池寿命', '车祸', '车主', 'model y', 'model 3']),
    ('机器人', ['机器人', 'robot', 'humanoid', '人形', '机械臂', '具身智能', '无人机',
                'drone', '自动驾驶汽车', '四足', '机器狗', '灵巧手']),
    ('生命科学', ['药物', '新药', '临床', '医疗', '医院', '患者', '疾病', '癌症', '肿瘤',
                  '衰老', '细胞', '基因', '蛋白质', '健康', '制药', '疫苗', '脑机', '医美',
                  '减肥药', '减重', 'glp-1', '司美格鲁肽', '生物龄']),
    ('基础科学', ['诺贝尔', '诺奖', '物理学', '化学', '生物学', '宇宙', '星系', '黑洞',
                  '量子力学', '数学家', '数学手稿', '数论', '拓扑', '科学家', '太空', 'nasa',
                  '天文', '航天', '火箭', '卫星', '考古', '古生物', '化石', '物种', '进化',
                  '虫洞', '暗能量', '暗物质', '引力波', '实验发现', '首次发现', '论文',
                  '顶刊', 'nature', 'science', 'cell']),
    ('智能家居', ['智能家居', 'matter', 'home assistant', 'homekit', '门锁', '智能门锁',
                  '摄像头', '中控屏', '智能屏', '音箱', '扫地机器人', 'iot', '家居']),
    ('网络安全', ['漏洞', '攻击', '黑客', '隐私', '泄露', '封号', '合规', '监管', '政策',
                  '法案', '审查', ' censorship', '密码', '后门', '诈骗', '隐私政策', '实名',
                  '未成年人', '青少年', '内容安全']),
    ('互联网商业', ['融资', '估值', 'ipo', '上市', '收购', '裁员', '破产', '营收', '财报',
                    '投资', '市值', '招股', '股东', 'ipo', '独角兽', '商业化', '订阅费',
                    '收费', '涨价', '降价', 'gmv', '创始人', 'CEO', '离职', '入职', '挖角',
                    '成立', '发布融资', '亿美元', '亿融资']),
    ('开源项目', ['github', '开源', 'repo', '仓库', 'huggingface', 'sdk', '框架', 'library',
                  'npm', 'pypi', 'docker', 'kubernetes', '源码', '开发者', 'api', '工具',
                  '插件', 'skill', 'star', 'claude code', 'codex', 'agent skills',
                  '编程', '脚本', '命令行', 'cli', 'mcp', 'design system', 'diagram']),
    ('AI公司动态', ['openai', 'anthropic', '谷歌', 'google', '微软', 'microsoft', 'meta',
                    '苹果', 'apple', '亚马逊', '腾讯', '阿里', '字节', '百度', '华为', '小米',
                    '英伟达', 'nvidia', '公司', 'ceo', '创始人', 'cto', '研究员', '工程师',
                    '离职', '入职', '跳槽', '裁员', '招人', '挖角', '团队', '实验室',
                    '发布会', '公开信', '内部信', '公告', '内部文件', '举报', '指控', '致信',
                    '员工', '公司回应', '官方回应', '发言人', '解散', '重组', '改名']),
    ('AI模型', ['gpt', 'chatgpt', 'claude', 'gemini', 'deepseek', 'qwen', 'kimi', 'grok',
                'llama', 'mistral', 'openai', 'anthropic', '文心', '通义', '豆包', '混元',
                'step fun', '阶跃', '智谱', 'glm', 'minimax', '模型', 'moe', 'lora',
                '微调', '推理模型', '多模态', '视觉模型', '语音模型', 'token', '上下文',
                '幻觉', '对齐', '预训练', 'agi', '基准', 'benchmark', '参数量',
                '开源', '权重', 'fine-tune', '蒸馏', '量化', '推理成本', '跑分']),
    ('AI应用', ['agent', '智能体', 'copilot', '助手', '对话', 'chat', '插件', 'skill',
                '办公', '编程', 'codex', 'claude code', '搜索', '翻译', '写作', '客服',
                '陪伴', '数字人', '虚拟主播', '端到端', '应用']),
]
CAT_AI_KW = ['ai', 'gpt', 'chatgpt', 'claude', 'gemini', 'deepseek', 'qwen', 'kimi', '模型',
             'llm', 'openai', 'anthropic', 'agent', '智能体', '算力', '算法', '神经网络',
             '机器学习', 'agi', 'copilot', 'codex', 'muse', 'prompt', 'token', '多模态',
             '推理', '训练', 'gpu', '大模型', 'opus', 'sonnet', 'haiku', 'diffusion',
             '豆包', '混元', '文心', '通义', '智谱', '阶跃', 'minimax', 'grok', 'llama',
             'mistral', 'ai日报', 'sora', 'midjourney', 'runway', '生成式']


def track_of(title, cat):
    t = (title or '').lower()
    for name, kws in TRACK_RULES:
        if any(k in t for k in kws):
            return name
    return 'AI模型' if cat == 'AI' else '其他'


def is_ai(title):
    t = (title or '').lower()
    return any(k in t for k in CAT_AI_KW)


def cat_of(title, src_cat):
    """大类判定：**只看标题本身**。源的大类只是抓取归类，不代表条目内容。

    ⚠️ 踩坑（2026-10-09 实测）：直接沿用源的大类 → 量子位/36氪AI 里
    「iPhone Air 2 爆料」「Mate 90 相机」这类纯消费电子稿被标成 AI。
    """
    if is_ai(title):
        return 'AI'
    return '科技'


# ---------- AI 主流模型 / 主流软件「必抓名单」（用户 2026-10-09 指定） ----------
# 用户明确要求：**主流软件与公司的更新必须抓到**（OpenAI ChatGPT、DeepSeek、豆包、
# Gemini 等）。这类官方发布常常只有 1–2 家媒体报道，靠「≥2 源」门槛会被整体漏掉 →
# 命中名单的条目**单源也进主表**，并打「必抓」标。
#
# 🔴 适用范围：**只对 AI 类条目生效**（2026-10-09 用户定）。
#   科技类**不设必抓** —— 名单里全是模型／软件品牌，科技板块实际只会捞到零星 1 条，
#   「科技必抓」形同虚设。判定在 `build()` 里以 `cat == 'AI'` 前置过滤。
#
# ⚠️ 只写**稳定的家族名／产品线**，**不写版本号** —— 版本号月月变
#   （GPT-5.5 → GPT-6、Gemini 3.1 → 3.8、豆包 2.0 → 2.1），写死必然过期。
#   版本由 `_gen_of()` 另行识别。子串误伤风险高的短词（如 o1 / o3）一律不用。
MUST_WATCH = [
    ('OpenAI / ChatGPT', ['openai', 'chatgpt', 'gpt', 'sora', 'codex', 'dall-e', 'gpt-oss']),
    ('Anthropic / Claude', ['anthropic', 'claude']),
    ('Google / Gemini', ['gemini', 'nano banana', 'veo', 'antigravity', 'notebooklm', 'deepmind']),
    ('DeepSeek', ['deepseek']),
    ('字节 / 豆包', ['豆包', 'doubao', 'seedance', 'seedream', '即梦', 'coze', '扣子']),
    ('阿里 / 千问', ['qwen', '通义', '千问']),
    ('月之暗面 / Kimi', ['kimi', '月之暗面', 'moonshot']),
    ('智谱 / GLM', ['glm', '智谱', 'chatglm']),
    ('xAI / Grok', ['grok', 'xai']),
    ('Meta / Llama', ['llama', 'meta ai']),
    ('Mistral', ['mistral']),
    ('MiniMax', ['minimax', '海螺']),
    ('百度 / 文心', ['文心', 'ernie']),
    ('腾讯 / 混元', ['混元', 'hunyuan', '元宝']),
    ('讯飞 / 星火', ['星火大模型', '讯飞星火']),
    ('微软 / Copilot', ['copilot', 'microsoft 365']),
    ('苹果 AI', ['apple intelligence', '苹果智能']),
]


# 「更新」语义词：用户要抓的是**主流模型的更新**，不是厂商的任何一条新闻。
# ⚠️ 只按厂牌名命中就收录 → 实测主表炸到 78 条（「某厂融资」「某厂人事」全被拉进来）。
#    必须品牌 + 更新信号同时命中才算「必抓」。
UPDATE_SIG = [
    '发布', '上线', '推出', '更新', '升级', '开放', '官宣', '宣布', '内测', '公测',
    '开源', '正式版', '亮相', '登场', '释出', '新版', '新模型', '新功能', '接入',
    'preview', 'release', '开测', '灰度',
]
# ⚠️ 「公开」不能进表 —— 实测把「OpenAI 研究员发公开信，3 名遭解雇」判成了模型更新。


def must_watch_of(title):
    """命中必抓名单**且有更新语义**才返回厂牌名，否则 None。

    只认品牌不够 —— 「某厂被曝融资 500 亿」也会命中厂牌，但那不是模型更新。

    ⚠️ 本函数**只判 AI 条目**（调用方先按 `cat == 'AI'` 过滤），科技类不设必抓。
    """
    t = (title or '').lower()
    brand = None
    for name, kws in MUST_WATCH:
        if any(k in t for k in kws):
            brand = name
            break
    if not brand:
        return None
    return brand if any(k in t for k in UPDATE_SIG) else None


# ---------- 来源性质：给「单源候选」一个可判断的底（用户 2026-10-09 要求） ----------
# 单源条目不做深度核实，但**读者至少要能判断这条来源是什么来头**。
SRC_NOTE = {
    '36氪': '科技商业媒体', '36氪AI': '科技商业媒体', '36氪24h': '科技商业媒体',
    '量子位': 'AI 垂直媒体', 'AIbase': 'AI 资讯聚合站', 'AI工具集': 'AI 工具导航站',
    '掘金': '开发者社区', 'MIT TR': '科技期刊（麻省理工科技评论）', 'AI产品榜': '行业榜单站',
    'IT之家': '科技门户媒体', '威锋': '苹果生态媒体', '爱范儿': '科技消费媒体',
    '果壳': '科普媒体', 'Readhub': '新闻聚合站', '少数派': '数码内容社区',
    '虎嗅': '商业财经媒体', '极客公园': '科技媒体',
    'Hacker News': '海外开发者社区', 'HuggingFace': 'AI 模型社区',
    'GitHub Trending': '开源平台榜单',
}


def src_nature(name):
    n = name or ''
    for k, v in SRC_NOTE.items():
        if k in n:
            return v
    return '科技媒体'


# ---------- 跨源合并：实体词重合 = 同一事件 ----------
_ENT_EN = re.compile(r'[A-Za-z][A-Za-z0-9]*(?:\.[0-9]+)?')
_BRAND = {
    'openai', 'anthropic', 'google', '微软', '苹果', 'apple', '华为', '小米', '三星', '字节',
    '腾讯', '阿里', '百度', 'meta', '英伟达', 'nvidia', 'amd', 'intel', '特斯拉', '小鹏',
    '蔚来', '理想', '比亚迪', '大疆', 'jpmorgan', '高盛', 'redhat', 'ibm', 'oracle',
    'gemini', 'gpt', 'claude', 'deepseek', 'qwen', 'kimi', 'grok', 'llama', 'manus',
    'midjourney', 'cursor', 'copilot', 'sora', 'runway', 'waymo', 'openrouter', 'stepfun',
}
_STOP = {'the', 'a', 'an', 'of', 'in', 'on', 'and', 'or', 'to', 'for', 'is', 'are', 'with',
         'by', 'at', 'from', 'be', 'it', 'this', 'that', 'new', 'how', 'why', 'what',
         'will', 'can', 'did', 'its', 'ai', 'not', 'has', 'have', '但', '的'}


def ents(s):
    s = s or ''
    out = set()
    for m in _ENT_EN.findall(s):
        t = m.lower().strip('.')
        if len(t) < 2 or t in _STOP:
            continue
        out.add(t)
        pre = re.match(r'([a-z]+?)[0-9]', t)
        if pre and len(pre.group(1)) >= 3:
            out.add(pre.group(1))
    tl = s.lower()
    for b in _BRAND:
        if b in tl:
            out.add(b)
    return out


_NOISE = re.compile(r'[\s\u3000·、，,。．\.!！?？:：;；\-—–_“”"\'‘’()（）\[\]【】<>《》|/\\]')


def norm(s):
    return _NOISE.sub('', (s or '')).lower()


# 模型「代际号」：qwen3.8 → 'qwen3.8'；gpt-5 → 'gpt5'；claude haiku 5.5 → 'haiku5.5'
_GEN = re.compile(r'([a-z]{2,10})\s*[-_]?\s*(\d+(?:\.\d+)*)', re.I)


def _gen_of(s):
    """取标题里最像「型号代际」的一处，如 Qwen3.8 / Haiku 5.5。

    ⚠️ 必须跳过中文词里夹的英文（开源模型 / 热门模型 这类），
    否则「HF 热门开源模型 Qwen3.8-27B」会抓错。
    """
    best = ''
    for m in _GEN.finditer((s or '').lower()):
        # 前面紧邻**两个以上**中文的英文多半是词组的一部分（「开源模型」「发布 Claude」），跳过；
        # 单字中文（「上线 Qwen3.8」「甩出Claude」）是正常句子的一部分，不该跳。
        st = m.start()
        if st >= 2 and re.search(r'[\u4e00-\u9fff]{2}', (s or '')[max(0, st - 2):st]):
            continue
        cand = m.group(1) + m.group(2)
        ver = m.group(2)
        # 排除「组织名+数字」：SC117/Qwen3.8 这类 HF 仓库作者前缀不是型号。
        # 保留特征：小数（3.8 / 5.5）、纯数字且词长>=3（ios 27 不算，qwen3 算）。
        if '.' not in ver and len(m.group(1)) < 3:
            continue
        # 取**第一个**匹配：型号总在标题前部。取最长的会选错 ——
        # 「Qwen3.8-27B-TURBO-Fable-Cold-Fusion-735」里的 fusion735 比 qwen3.8 长。
        return cand
    return best


# 🔴 厂商名 + 旗下模型名 = **必然共现**，不能当「同一事件」的证据（2026-10-09 实测踩坑）：
#   「Anthropic 辱骂 Claude 封号」和「Anthropic 发布 Claude Haiku 5.5」只共现 claude+anthropic，
#   是两件完全不同的事，却被判成同一事件（当时误报成「4 源命中」）。
# 同理 chatgpt/gpt 是同一个词的前缀归一，被算成两个实体 → 「ChatGPT 入驻 Word」也被并进「ChatGPT 教打麻将」。
_GENERIC = {
    'openai', 'anthropic', 'google', '微软', '苹果', 'apple', '华为', '小米', '三星', '字节',
    '腾讯', '阿里', '百度', 'meta', '英伟达', 'nvidia', 'amd', 'intel', '特斯拉', '小鹏',
    '蔚来', '理想', '比亚迪', '大疆', 'jpmorgan', '高盛', 'redhat', 'ibm', 'oracle',
    'gemini', 'gpt', 'chatgpt', 'claude', 'deepseek', 'qwen', 'kimi', 'grok', 'llama',
    'manus', 'midjourney', 'cursor', 'copilot', 'sora', 'runway', 'waymo', 'openrouter',
    'stepfun', 'doubao', '豆包', '文心', '通义', '混元', '智谱', '阶跃',
}


def _bigrams(s):
    s = norm(s)
    return {s[i:i + 2] for i in range(len(s) - 1)} or {s}


def _sim(a, b):
    """标题字符二元组包含度（短标题被长标题包含的比例）。"""
    ga, gb = _bigrams(a), _bigrams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / min(len(ga), len(gb))


def same_event(a, b):
    """跨源判同。**必须有「可区分的共有特征」**，光靠共现品牌/产品线不算。

    ⚠️ 2026-10-09 两轮实测踩坑：
      旧版「共有实体 ≥2 就判同」把 5 条 ChatGPT 新闻（入驻 Word / 代充值 /
      破解数学难题 / IUI 界面 / JEV 访谈）并成一条「5 源命中」，报告里还写成
      跨源核验 —— 实际是假合并。
      第二版「共有非通用实体 + 相似度 0.45」把「WorkBuddy 使用教程」并进
      「WorkBuddy 上线文件浏览器」，把「iPhone 18 Pro 体验」并进
      「美版 iPhone 18 Pro Max 有问题」—— 都是同产品线的不同新闻。
    现在两档，**宁可漏合不可错合**（漏合只是变成单源条目，错合会伪造核验）：
      ① 共有实体里带数字（型号/版本：Qwen-Image-2.1、Haiku 5.5）→ 判同
      ② 共有**两个以上**非通用实体且标题相似度够高 → 判同
      ③ 只共现一个产品线词（iphone / agent / workbuddy）→ 不判同
    """
    common = (ents(a) & ents(b)) - _GENERIC
    if any(len(c) >= 3 and any(ch.isdigit() for ch in c) for c in common):
        return True
    if len(common) >= 2 and _sim(a, b) >= 0.5:
        return True
    na, nb = norm(a), norm(b)
    if na and na == nb:
        return True
    if len(na) >= 10 and len(nb) >= 10:
        short, lng = (na, nb) if len(na) <= len(nb) else (nb, na)
        if lng.startswith(short) and len(short) / len(lng) >= 0.6:
            return True
    return False


def load(name):
    p = os.path.join(HERE, name)
    if not os.path.exists(p):
        return []
    with open(p, encoding='utf-8') as f:
        return json.load(f)


# 聚合稿拆分：这些标题本身是「一天 N 条新闻」的汇总，不能当一条选题，
# 但**每条子新闻都是好钩子** → 按分隔符拆开，继承原源。
AGG = re.compile(r'(AI日报|早报|派早报|造物\s*100#\d+|极客早知道|8点1氪|要闻|News|周报|日报)')
# ⚠️ 分隔符必须同时覆盖 5 种（2026-10-09 两轮实测踩坑）：
#   「；」AI日报   「｜」爱范儿早报/造物100   「/」极客早知道   「、」派早报   「；」多源拼接
# 漏一个 → 「苹果一大波新品曝光/纯汽油车跌破50%/Surface Ultra」这种三合一条目会整条进池；
# 本轮还漏了「、」→「派早报：英伟达 RTX Spark 新品一览、Anthropic 发布 Haiku 5.5」没拆开，
# 把两条不同新闻并成一条，源数虚高。
SPLIT = re.compile(r'[；;｜/、]')

# 🗑 **低价值条目黑名单**：不是「不能做图文」，而是**本身没有钩子**——
# 修 bug 的小版本、纯八卦、证券快讯、价格播报。这些进了池子只是占位。
# 判定用标题关键词，命中即丢（2026-10-09 实测：iOS/watchOS 修 bug 一度占掉 3 个名额）。
JUNK_KW = [
    '修复了', '修复若干', '更新了若干错误', '勘误', '致歉', '致歉声明',
    '金价', '金饰', '克价', '汇率', '午评', '收评', '开盘', '收盘', '涨停', '跌停',
    '股价', '市值蒸发', '成交额', '北向资金', '主力资金',
    '最新消息', '官方公告', '声明如下', '抽奖', '优惠码', '红包',
    # 🗑 **厂商推广/软文**（2026-10-09 实测踩坑）：
    # 量子位「量子位的朋友们」栏目 = 付费推广，文章全是「重塑生产力边界」这类营销话术，
    # 通篇没有独立信息。混进选题池会被当成新闻，图文做出来会误导读者。
    # 判据：营销话术词密度高（有夸赞、无具体参数对比或第三方来源）。
    '重塑个人生产力边界', '开启盲约', '正式开启盲约', '欢迎选购', '购买链接',
]
# 厂商软文的高频营销话术 —— 单条命中不足以判定，整条里出现 2 个以上即判为推广稿
_PROMO_KW = [
    '重塑', '赋能', '开启盲约', '超能模式', '天禧', '为创作打造', '生产力边界',
    '性价比之选', ' MIGU ', '抢购', '到手价', '元起售', '尊享', '旗舰之选',
]
# 「元起售」「到手价」在正规消费电子新闻里也常见，因此只对**明显营销结构**生效：
# 出现「开启盲约 / 重塑…边界 / 生产力边界」这类只可能出现在软文里的短语
PROMO_STRONG = ['开启盲约', '重塑个人生产力边界', '生产力边界', '超能模式', '天禧ai']
# 这些是「有信息量但仍偏弱」的，只在多源命中时保留
WEAK_KW = ['内测', '灰测', '公测', '测试版', '预览版', 'beta', 'preview']


def split_agg(title, url, src, src_name, heat_kind, cat):
    """把聚合稿拆成子条目。拆不出来就返回原条目。

    判定不只看前缀（`AI日报`/`早报`），**也看分隔符密度** ——
    实测有源不写「早报」前缀但用 `/` 或 `；` 拼了 3 条新闻。
    """
    seps = len(re.findall(r'[；;｜/、]', title))
    if not AGG.search(title) and seps < 2:
        return [(title, url)]
    body = re.sub(r'^(AI日报|早报|派早报|造物\s*100#\d+|极客早知道|8点1氪|要闻)[:：|]?\s*', '', title)
    parts = [p.strip(' 　·|-—') for p in SPLIT.split(body)]
    out = []
    for p in parts:
        p = re.sub(r'\s*[|｜]\s*[^|｜]{2,12}$', '', p).strip()
        p = p.rstrip('；;，,。')
        # 太短的片段（<8 字）多是「软件」「公司」这类残词，丢弃
        if len(p) >= 8:
            out.append((p, url))
    return out or [(title, url)]


def is_junk(title):
    t = (title or '').lower()
    # 厂商软文：只认「只可能出现在推广稿里」的短语，避免误伤正常消费电子新闻
    if any(k in t for k in PROMO_STRONG):
        return True
    if any(k in title for k in JUNK_KW):
        return True
    # 「修复了 N 个问题」类小版本更新：标题里同时有版本号 + 修复/勘误
    if re.search(r'(ios|watchos|macos|android)\s*[\d.]+', t, re.I) and \
       re.search(r'修复|勘误|更新了|error|bug', t, re.I):
        return True
    return False


def collect():
    """汇总所有源，跨源合并成事件。"""
    raw = []
    th = load('tophub_items.json')
    for it in th.get('items', []):
        for sub_t, sub_u in split_agg(it['title'], it['url'], it['src'],
                                     it['src_name'], it.get('heat_kind', ''), it['cat']):
            t = sub_t
            if is_junk(t):
                continue
            raw.append({
                'title': t, 'url': sub_u, 'heat': it.get('heat'),
                'src': it['src'], 'src_name': it['src_name'],
                'heat_kind': it.get('heat_kind', ''), 'cat': cat_of(t, it['cat']),
            })
    for it in load('hn_items.json'):
        raw.append({
            'title': it['title'], 'url': it['url'], 'heat': float(it.get('score') or 0),
            'src': 'hn', 'src_name': 'Hacker News', 'heat_kind': '得分', 'cat': 'AI',
        })
    for m in load('hf_models.json'):
        mid = m.get('id', '')
        if not mid or is_junk(mid):
            continue
        dl = m.get('downloads', 0)
        # 只留下载量过 5 万的（冷门模型对图文没价值）
        if dl < 50000:
            continue
        raw.append({
            'title': f'HF 热门开源模型 {mid}，本月下载 {dl:,}',
            'url': f'https://huggingface.co/{mid}',
            'heat': float(m.get('trendingScore') or 0),
            'src': 'hf', 'src_name': 'HuggingFace', 'heat_kind': 'trendingScore', 'cat': 'AI',
        })
    # GitHub Trending：**用「今日 star 增量」当热度** —— 这是唯一能横向比较的开源口径
    # （star 总数在解析时拿不到，且累计数会让老仓库永远霸榜）。
    for g in load('gh_items.json'):
        if not g.get('repo'):
            continue
        lang = f'（{g["lang"]}）' if g.get('lang') else ''
        desc = (g.get('desc') or '').strip()
        title = f'GitHub 今日热门 {g["repo"]}{lang}，一天涨 {g.get("today",0):,} star'
        if desc:
            title += f'：{desc[:60]}'
        raw.append({
            'title': title, 'url': g.get('url', ''),
            'heat': float(g.get('today') or 0),
            'src': 'gh', 'src_name': 'GitHub Trending', 'heat_kind': '今日新增star',
            'cat': 'AI' if is_ai(desc + ' ' + g['repo']) else '科技',
        })

    groups = []
    for it in raw:
        for g in groups:
            if same_event(g['title'], it['title']):
                g['members'].append(it)
                break
        else:
            groups.append({'title': it['title'], 'members': [it]})

    events = []
    for g in groups:
        ms = g['members']
        # ⚠️ **同源去重**（2026-10-09 实测踩坑）：少数派 / 少数派最新 是**同一站点的两个节点**，
        # 同一篇文章会同时出现在两边。原逻辑按 src 字符串去重，节点 id 不同 → 被算成「2 源命中」，
        # 伪造了跨源核验。按**媒体域名**归一后再去重。
        srcs, names = [], []
        for m in ms:
            dom = m['src_name'].split('日榜')[0].split('最新')[0].strip()
            if dom not in names:
                names.append(dom)
            if m['src'] not in srcs:
                srcs.append(m['src'])
        heats = [(m['heat'], m['src'], m['heat_kind']) for m in ms
                 if isinstance(m.get('heat'), (int, float)) and m['heat'] > 0]
        best = max(heats, key=lambda x: x[0]) if heats else (None, None, '')
        # 标题与分类都以**中文源**为准；HN/HF 只在没有中文源时才用它们的标题
        cn = next((m for m in ms if m['src'] not in ('hn', 'hf', 'gh')), ms[0])
        title = cn['title']
        cat = cat_of(title, cn['cat'])
        # ⚠️ HF 只能当**佐证**不能当核验源（2026-10-09 实测踩坑）：
        # 「千问上线 Qwen3.8-Omni-Flash」被 7 个 HF 上的 Qwen3.8-Flash-Next
        # **社区微调版**并进来，看着像 2 源交叉验证，其实官方发布与社区衍生版
        # 是两件事。只有当 HF 命中的是**同一个模型 id**（或它的量化版）才算数。
        if cn['src'] == 'hf' or all(m['src'] == 'hf' for m in ms):
            n_src = 1
        else:
            n_src = len(names)
        # 佐证标题只保留**非同一模型家族**的，避免把社区微调版/量化版当独立报道。
        # ⚠️ 判据用「代际号」：qwen3.8 → 'qwen3.8'，出现在标题或 HF 模型名里即同一代，
        #    官方发布与社区 GGUF 是两件事，不能互相佐证。
        gen = _gen_of(title)
        others = []
        for m in ms:
            t = m['title']
            if t == title:
                continue
            if m['src'] == 'hf':
                if gen and gen in _gen_of(t):
                    continue
            others.append(t)
        events.append({
            'title': title, 'cat': cat,
            # GitHub / HF 条目直接定死赛道 —— 它们标题是模板拼的，
            # 走关键词判定会被「工具」「模型」这些词带偏。
            'track': '开源项目' if cn['src'] in ('gh', 'hf') else track_of(title, cat),
            'url': cn['url'], 'n_src': n_src, 'src_names': names,
            # ⚠️ 失效链接标记（2026-10-09 实测）：爱范儿节点在 tophub 上给的链接
            # 本身就是 `ifanr.com/False`（源站就是坏的，7 条全中），不是我们的解析问题。
            # 主链接失效但有其他源佐证时，HTML 里要显式提示换用佐证链接。
            'url_ok': bool(cn['url'] and cn['url'].startswith('http')
                           and not cn['url'].endswith('/False')),
            'alt_urls': [m['url'] for m in ms
                         if m['url'] and m['url'].startswith('http')
                         and not m['url'].endswith('/False')
                         and m['url'] != cn['url']][:3],
            'heat': best[0], 'heat_src': best[1], 'heat_kind': best[2],
            'all_titles': others,
            # 来源 id 供「必抓」判定排除榜单源用（HF/GitHub 是榜单，不是新闻）
            'src': cn['src'],
        })
    # 第三个返回值给**完整 raw**（含 hn / hf / gh），供「采到几个源」统计用。
    # ⚠️ 只给 th['items'] 会漏掉海外与 GitHub 源，元信息里的源数会与正文列举不符（17 vs 20）。
    return events, th.get('missing', []), raw


# ---------- 钩子强度（用户 2026-10-09 给定规则：情绪／反差／知名度） ----------
# 用户原话：钩子方向按这三点定 ——「(a) 情绪/情感，这是最重要的一点；(b) 反差；
# (c) 知名度」。三类都写在这里，**只用于排序与提示，不用于事实判断**（命中 ≠ 为真）。
#
# 权重依据用户给的优先级：情绪 > 反差 ≈ 知名度。
#   · 情绪：强情绪词 +3；仅一般情绪词 +1（最多 3）
#   · 反差：强反差结构 +2；仅一般反差词 +1（最多 2）
#   · 知名度：顶流人物／大厂 +2；一般知名主体 +1（最多 2）
#   · 具体数字（金额／倍数／百分比）：+1（让情绪与反差可被量化）
HOOK_EMO_HI = [
    '震惊', '炸了', '炸锅', '怒了', '怒斥', '慌了', '崩溃', '破防', '离谱', '恐怖',
    '史诗', '里程碑', '泪目', '狂欢', '爆火', '刷屏', '吵翻', '翻车', '塌房', '颠覆',
    '前所未有', '惊天', '噩耗', '降维打击', '不寒而栗', '刷新认知', '封神', '血洗',
]
HOOK_EMO_MID = [
    '热议', '争议', '质疑', '吐槽', '失望', '后悔', '真香', '意外', '没想到', '惊喜',
    '抗议', '抵制', '不满', '担忧', '焦虑', '危机', '恐慌', '嘲讽', '反驳', '辩护',
    '呼吁', '警告', '反思', '庆祝', '叫好', '唱衰', '大战', '宣战', '喊话', '开撕',
]
HOOK_CONTRAST_HI = [
    '竟然', '居然', '反而', '原来', '反转', '逆袭', '反常识', '出乎意料', '大跌眼镜',
    '不按套路', '唯独', '偏偏', '破例', '反常', '打脸', '背刺', '内讧',
]
HOOK_CONTRAST_MID = [
    '却', '不再', '第一次', '首次', '首个', '全球首', '全国首', '打破', '甚至',
    '并非', '而是', '从此', '终于', '突然', '一边', '也要', '也要', '才', '就',
]
HOOK_FAME_HI = [
    '黄仁勋', '马斯克', '奥特曼', '雷军', '张一鸣', '梁文锋', '陶哲轩', '杨立昆',
    '库克', '纳德拉', '皮查伊', '扎克伯格', '李飞飞', '诺奖', '诺贝尔', '菲尔兹',
    '图灵奖', '院士', 'openai', '谷歌', 'google', '英伟达', 'nvidia', '苹果', 'apple',
    '微软', 'microsoft', 'meta', '华为', '字节', '阿里', '腾讯', '百度', '特斯拉',
    'tesla', '三星', 'samsung', '小米', '亚马逊', 'amazon',
]
HOOK_FAME_MID = [
    'deepseek', 'qwen', 'claude', 'gemini', 'chatgpt', '豆包', 'kimi', 'grok', '智谱',
    'glm', 'minimax', '月之暗面', '通义', '文心', '混元', '阶跃', '创业公司', '独角兽',
    '大厂', '上市公司',
]


def hook_hits(e):
    """返回 {维度: [命中的词]}，让「为什么判它有钩子」可核查、不空口。"""
    t = (e['title'] or '').lower()
    out = {}
    for name, seq in (('情绪', HOOK_EMO_HI + HOOK_EMO_MID),
                      ('反差', HOOK_CONTRAST_HI + HOOK_CONTRAST_MID),
                      ('知名度', HOOK_FAME_HI + HOOK_FAME_MID)):
        m = [k for k in seq if k in t]
        if m:
            out[name] = m[:3]
    m = re.findall(r'\d[\d,\.]*', t)
    if m:
        out['数字'] = m[:3]
    return out


def hook_tags(e):
    """命中的钩子维度名（情绪／反差／知名度／数字），供页面标注。"""
    return list(hook_hits(e).keys())


def hook_score(e):
    """钩子强度 0–8。三类按用户给定优先级加权（情绪 > 反差 ≈ 知名度）。"""
    t = (e['title'] or '').lower()
    s = 0
    if any(k in t for k in HOOK_EMO_HI):
        s += 3
    elif any(k in t for k in HOOK_EMO_MID):
        s += 1
    if any(k in t for k in HOOK_CONTRAST_HI):
        s += 2
    elif any(k in t for k in HOOK_CONTRAST_MID):
        s += 1
    if any(k in t for k in HOOK_FAME_HI):
        s += 2
    elif any(k in t for k in HOOK_FAME_MID):
        s += 1
    if re.search(r'\d', t):
        s += 1
    return s


# ---------- 钩子候选 / 必抓上限（2026-10-09 用户要求）----------
# 用户原话：「有一个可能是小新闻，但我希望它能做出来。所以，我希望在"多元候选"
# 后面，再增加一些可能比较小、但是有比较好"钩子"的新闻。」
# → 从**单源非必抓**里按钩子强度挑，单独成块，供人工挑做（不做核实，只给线索）。
HOOK_MIN = 3        # 钩子分门槛（满分 8）
HOOK_CAP = 20       # 钩子候选上限（2026-10-09 合并版为**全池总量 20 条**）
HOOK_PER_FAME = 3   # 同一知名品牌最多 3 条，避免「苹果」这类词霸屏
HOOK_DROP = ['福利', '优惠', '专享', '领取', '抽奖', '折扣', '秒杀', '畅听', '白嫖', '限时']
MUST_CAP = 20       # 必抓更新上限（**只对 AI 类**；用户：太多了，保留 20 条就好）
SINGLE_CAP = 30     # 单源候选上限（用户 2026-10-09：限 30 条以内）


def balanced_pick(items, cap, per_fame=0):
    """按大类**软均衡**地取前 cap 条，返回时保持原排序。

    合并版要防的是「AI 源产量大 → 科技被整体挤掉」。做法：AI / 科技 各先占 cap//2，
    哪一类不足就由另一类补足；`per_fame` 用于限制同一知名品牌条数。
    """
    # 入参 items 需已按目标优先级排好序
    picked, _ids, _fame = [], set(), Counter()

    def _fame_ok(e):
        if not per_fame:
            return True
        f = hook_hits(e).get('知名度') or []
        k0 = f[0] if f else ''
        if k0 and _fame[k0] >= per_fame:
            return False
        if k0:
            _fame[k0] += 1
        return True

    for c in ('AI', '科技'):
        _took = 0
        for e in [x for x in items if x['cat'] == c]:
            if _took >= cap // 2:
                break
            if not _fame_ok(e):
                continue
            picked.append(e)
            _ids.add(id(e))
            _took += 1
    if len(picked) < cap:
        for e in items:
            if len(picked) >= cap:
                break
            if id(e) in _ids or not _fame_ok(e):
                continue
            picked.append(e)
            _ids.add(id(e))
    return [e for e in items if id(e) in _ids]


def build(events, date):
    """分区与排序。

    ⚠️ 用户 2026-10-09 明确：**主流模型／主流软件的更新必须抓到**。
    这类官方发布常常只有 1–2 家媒体报道，会被「≥2 源」门槛整体漏掉 →
    命中必抓名单的条目**单源也进主表**（打「必抓」标），与多源条目同列。

    🔴 2026-10-09 修订：必抓**只对 AI 类生效**，科技类不设必抓名单。
    """
    # ⚠️ HF / GitHub 是**榜单源**不是新闻源（标题是脚本拼的模板），
    #    一律不参与「必抓」判定 —— 否则「HF 热门开源模型 xxx-GGUF」会被当成模型发布。
    _LIST_SRC = {'hf', 'gh'}
    multi, must_only, single = [], [], []
    for e in events:
        # ⚠️ 2026-10-09 用户定：必抓**只针对 AI 类**，科技类不设必抓名单。
        #    原因：科技板块命中的关键词本身就是 AI 品牌（MUST_WATCH 全是模型/软件名），
        #    科技类实际只有 1 条被捞出 → 「科技必抓」形同虚设，不如取消。
        e['must'] = (None if e.get('src') in _LIST_SRC or e.get('cat') != 'AI'
                     else must_watch_of(e['title']))
        if e['n_src'] >= 2:
            multi.append(e)
        elif e['must']:
            must_only.append(e)
        else:
            single.append(e)

    def key(e):
        h = e['heat'] if isinstance(e['heat'], (int, float)) else -1
        return (-e['n_src'], -hook_score(e), -h, e['title'])

    multi.sort(key=key)
    must_only.sort(key=key)
    single.sort(key=key)

    # ---- 钩子候选：单源非必抓里钩子强的「小新闻」（2026-10-09 新增）----
    # 用户要「可能比较小、但钩子好」的条目，所以只从 single 里挑；
    # 挑中的从「单源候选（不做）」表里移出 —— 否则同一件事在两处出现，性质还打架。
    # 2026-10-09 合并版：钩子候选改为**全池总量 20 条**，并按大类软均衡（各 10 起）
    hooks, _hook_used = [], set()
    pool = [e for e in single
            if hook_score(e) >= HOOK_MIN
            and not any(k in e['title'] for k in HOOK_DROP)]
    pool.sort(key=lambda e: (-hook_score(e),
                             -(e['heat'] if isinstance(e['heat'], (int, float)) else -1),
                             e['title']))
    hooks = balanced_pick(pool, HOOK_CAP, per_fame=HOOK_PER_FAME)
    for e in hooks:
        _hook_used.add(id(e))
    hooks.sort(key=key)

    # 单源候选（不做）：剔除已进「钩子候选」的，**全池总量上限 30 条**
    _rest = [e for e in single if id(e) not in _hook_used]
    CAP = SINGLE_CAP
    si_ai = [e for e in _rest if e['cat'] == 'AI']
    si_tk = [e for e in _rest if e['cat'] == '科技']
    keep = si_ai[:CAP // 2] + si_tk[:CAP - CAP // 2]
    short = CAP - len(keep)
    if short > 0:
        _kept = {id(e) for e in keep}
        keep += [e for e in _rest if id(e) not in _kept][:short]
    keep.sort(key=key)

    # 推荐：每个大类 3 条，**先多源（有交叉核验）后必抓**。
    # ⚠️ 不能按全局名次取前 6 —— 那会全被 AI 占（AI 源产量本就大）。
    picks = []
    for cat in ('AI', '科技'):
        in_cat = [e for e in multi if e['cat'] == cat]
        picks += in_cat[:3]
        if len(in_cat) < 3:
            # 补位也只补**有核实内容（DETAIL）**的条目 —— 没有核实的渲染不出「匹配度」，
            # 放进推荐区会出现标题写 3 条、实际只显示 2 条的错位。
            # ⚠️ 必抓只含 AI 类（2026-10-09 用户定）→ 科技类实际永不从这里补位，多源不足就少列。
            picks += [e for e in must_only if e['cat'] == cat and _detail(e)][:3 - len(in_cat)]
    picks.sort(key=key)
    return multi, must_only, hooks, keep, picks, len(single) - len(keep)


CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#F5F6F8;color:#1F2937;
  font-family:"Microsoft YaHei","PingFang SC","Segoe UI",sans-serif;
  line-height:1.75;-webkit-font-smoothing:antialiased}
.wrap{max-width:1000px;margin:0 auto;padding:44px 32px 84px}
.eyebrow{font-size:12px;font-weight:700;letter-spacing:3px;color:#185FA5;margin-bottom:12px}
h1{font-size:29px;font-weight:700;color:#0F172A;letter-spacing:-.5px;line-height:1.3}
h2{font-size:18px;font-weight:700;color:#0F172A;padding-bottom:11px;
  border-bottom:2px solid #E5E7EB;margin:36px 0 16px}
h3{font-size:14px;font-weight:700;color:#475569;margin:22px 0 8px;letter-spacing:.5px}
.lead{margin-top:13px;font-size:13px;color:#6B7280;line-height:1.7}
.lead b{color:#0F172A}
p{margin:8px 0;color:#374151;font-size:13px}
code{background:#F1F5F9;border-radius:5px;padding:2px 6px;font-size:12px;color:#334155}
a{color:#185FA5}
.box{background:#fff;border:1px solid #E5E7EB;border-radius:12px;padding:16px 20px;
  box-shadow:0 1px 2px rgba(16,24,40,.04);margin:14px 0}
.box.key{background:#F0F9FF;border-left:4px solid #185FA5}
.box.warn{background:#FFFBEB;border-left:4px solid #D97706}
.box.bad{background:#FEF2F2;border-left:4px solid #DC2626}
.box.ok{background:#F0FDF4;border-left:4px solid #16A34A}
.item{background:#fff;border:1px solid #E5E7EB;border-radius:12px;padding:15px 19px;
  box-shadow:0 1px 2px rgba(16,24,40,.04);margin:11px 0}
.item.pick{background:#F8FCFF;border-color:#BFDBFE}
.item.hook{background:#FFFDF5;border-color:#FDE68A}
.ih{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap}
.no{font-size:12px;font-weight:700;color:#185FA5;background:#E9F1FE;
  border-radius:6px;padding:2px 8px;flex:none}
.no.hk{color:#92400E;background:#FEF3C7}
.it{font-size:15.5px;font-weight:700;color:#0F172A;line-height:1.45;flex:1;min-width:240px}
.hit{font-size:11px;font-weight:700;color:#B45309;background:#FEF3C7;
  border-radius:5px;padding:2px 7px;white-space:nowrap}
.hit.one{color:#64748B;background:#F1F5F9}
.hit.stale{color:#9A3412;background:#FFEDD5}
.hit.must{color:#7E22CE;background:#F3E8FF}
.hit.hook{color:#92400E;background:#FDE68A}
.tag{font-size:10.5px;font-weight:700;color:#0F766E;background:#CCFBF1;
  border-radius:4px;padding:2px 6px;white-space:nowrap}
.lab{font-size:10.5px;font-weight:700;letter-spacing:1px;color:#94A3B8;margin-top:12px}
.txt{font-size:12.5px;color:#374151;margin-top:4px;line-height:1.68}
.facts{background:#F8FAFC;border-radius:8px;padding:10px 13px;margin-top:5px;
  font-size:12.5px;color:#334155;line-height:1.7}
.cnt{background:#FEF2F2;border-radius:8px;padding:10px 13px;margin-top:5px;
  font-size:12.5px;color:#7C2D12;line-height:1.68}
.fit{background:#F0FDF4;border-radius:8px;padding:10px 13px;margin-top:5px;
  font-size:12.5px;color:#14532D;line-height:1.68}
.lk{font-size:11.5px;color:#64748B;margin-top:9px;line-height:1.65;word-break:break-all}
.lk a{color:#185FA5}
.stale-note{background:#FFEDD5;border-radius:8px;padding:10px 13px;margin-top:5px;
  font-size:12.5px;color:#7C2D12;line-height:1.68}
.stat{display:flex;gap:11px;margin-top:18px;flex-wrap:wrap}
.stat div{background:#fff;border:1px solid #E5E7EB;border-radius:11px;padding:11px 19px}
.stat b{display:block;font-size:22px;font-weight:700;color:#185FA5;line-height:1.2}
.stat span{display:block;font-size:11.5px;color:#9CA3AF;margin-top:3px}
.stat div.must b{color:#7E22CE}
table.tb{width:100%;border-collapse:collapse;font-size:12px;margin-top:6px}
table.tb th,table.tb td{text-align:left;padding:7px 9px;border-bottom:1px solid #EEF0F3;
  vertical-align:top}
table.tb th{background:#F8FAFC;color:#64748B;font-weight:700;font-size:11.5px}
table.tb td.n{white-space:nowrap;color:#64748B;width:44px}
table.tb td.src{width:150px}
.sub{font-size:11px;color:#94A3B8;margin-top:2px;line-height:1.5}
.sec{background:#fff;border:1px solid #E5E7EB;border-radius:16px;padding:6px 22px 20px;
  margin:18px 0 30px}
.sec.ai{border-top:4px solid #185FA5}
.sec.tech{border-top:4px solid #0F766E}
.sec-h{margin:16px 0 6px;display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.sec-h .t{font-size:20px;font-weight:700;color:#0F172A}
.sec-h .n{font-size:12px;color:#94A3B8}
ul,ol{margin:8px 0 8px 20px;color:#374151;font-size:13px}
li{margin:5px 0}
footer{margin-top:40px;text-align:center;font-size:11.5px;color:#B0B7C3;line-height:1.8}
@media(max-width:720px){
  .wrap{padding:24px 14px 56px}
  h1{font-size:22px}
  .it{font-size:14.5px}
  table.tb td.src{width:auto}
}
"""

# 每条候选的四小节（人工核实，**不得由脚本编造**）。
# key = 条目标题里的稳定片段；写错 key 会自动落到 fallback，只出标题不出编造内容。
DETAIL = {
    # ⚠️ key 是标题的稳定片段，必须**逐字出现在标题里**（`_detail` 用 `in` 匹配）。
    #    写成 'Gemini Agent' 但标题是「谷歌发布办公Agent」→ 匹配不上，四小节全丢。
    '办公Agent': {
        'angle': '钩子不是「谷歌也做 Agent 了」，而是<b>它把自己的模型变成了可选项</b>——'
                 'Gemini Agent 会在 Gemini 与 <b>Claude</b> 之间自动挑模型，'
                 '按效果／速度／成本三维权衡。竞争关系被写进了产品架构里。',
        'facts': '2026-10-09 凌晨 Google Cloud 长文《Welcome to Gemini at Work 2026》，'
                 'CEO Thomas Kurian 署名 · Gemini Agent 为通用办公 Agent，云端持久运行、跨应用调用、'
                 '可召集多个子 Agent · <b>底层模型可在 Gemini 与 Anthropic Claude 之间动态选择</b>，'
                 '配套 Smart Routing 自动路由 · 另有 Coworker Agent：企业可给它建独立 Workspace 账号、'
                 '企业邮箱、日历、Drive 空间，并进公司通讯录，能被拉进 Google Chat 群聊或在文档里 @ 它 · '
                 '四种记忆：会话／语义／程序性／情景，其中程序性记忆可<b>自己写 Skills</b> · '
                 '官方原则原话「You give it objectives, not instructions」（给目标而非逐步指令） · '
                 '强调<b>换底层模型不丢已有上下文、Skills 与企业数据</b> · '
                 '同期 OpenAI 有 Dots（9-29，7×24 小时、可连 4000+ 应用）、Meta 有 Muse（偏个人生活）',
        'limit': '① <b>没有第三方实测</b>，全部功能描述来自谷歌官方长文，'
                 '演示案例（市场分析报告→Sheets 建模→Slides 出片）是厂商自述；'
                 '② 「能调用 Claude」是<b>能力声明</b>，原文只写「现阶段可在 Gemini 与 Claude 系列间选择」，'
                 '没说默认用哪个、怎么计费、有无数据回流条款；'
                 '③ 官宣推文下方网友评价以「缝合怪」「不像新鲜事」居多，跨应用操作本身并非新东西；'
                 '④ 真正要观察的是<b>权限边界</b>：Coworker Agent 要进企业通讯录、拿独立邮箱与日历，'
                 '官方尚未细说企业数据访问与责任怎么划。',
        'fit': '★ 本轮最推荐。三家巨头同场（谷歌／OpenAI／Meta）都在<b>9 月底到 10 月初</b>入场，'
               '时间窗口本身就是话题。「连竞争对手的模型都要调用」是天然的反差钩子，'
               '读者不用懂技术也能看懂矛盾。',
    },
    '陶哲轩': {
        'angle': '钩子是<b>「三小时算力碾碎学者一生研究」这个数字</b>，不是「数学家抵制 AI」。'
                 '陶哲轩那句「一个问题一旦被宣称解决，就再也回不到未解决的状态」'
                 '比「宣战」更有传播力——<b>讲的是不可逆的污染，不是立场之争</b>。',
        'facts': '人类数学协会（AHM，Association for Human Mathematicians）联合声明，'
                 '陶哲轩领衔，<b>全面抵制 OpenAI</b> · 此前陶哲轩已联合 <b>25 位菲尔兹奖得主</b>发声 · '
                 'OpenAI 用内部模型测试约 <b>8000 道</b>开放数学题，命中率约 5%，'
                 '<b>放出 700 多篇</b>机器生成证明，平均解一道难题约耗 3 小时 GPT-Pro 级算力 · '
                 'AHM 声明原话「没人求过你们解这些证明」· OpenAI 此前与普林斯顿高等研究院设过'
                 '数学与人工智能咨询小组（AGMAI），首份报告即警告「前沿 AI 公司不应擅自测试高深数学难题」，'
                 'OpenAI 未采纳 · 理论计算机科学家 Scott Aaronson 称其为 Mathocalypse，'
                 '其妻 Dana Moshkovitz 的「唯一博弈猜想」被宣称已解，她形容读后感受像「致幻剂」 · '
                 'AHM 指 OpenAI 正因<b>抄袭、侵犯版权、商标淡化</b>等指控面临诉讼 · '
                 '声明原始出处：陶哲轩博客 2026-10-07 · 图灵奖得主杨立昆<b>持相反立场</b>，'
                 '认为形式证明将自动化、数学迎来新时代',
        'limit': '① <b>不是同行评审结果</b>，700 篇全是机器草稿，'
                 '「已解出」在数学界尚不构成有效结论，Aaronson 与 Moshkovitz 都在强调其不可读；'
                 '② 数学家内部<b>并非一致</b>——杨立昆公开反对AHM 立场，'
                 '且 AHM 本身是「自发建立的行业防线」组织，不是官方学会；'
                 '③ 「抵制」目前是<b>公开声明层面</b>，文中未见任何机构层面的实际断供动作；'
                 '④ 数字（8000 题／5%／3 小时）均转述自报道，未见 OpenAI 官方原始统计口径。',
        'fit': '★ 本轮讨论度最高的一条。「数学家集体抵制」有明确的对抗性，'
               '且陶哲轩是大众认知度极高的名字（不需要科普）。'
               '<b>但必须带杨立昆的反面意见</b>，否则会被质疑一面之词。',    },
    'Instinct': {
        'angle': '钩子是<b>三个反常识数字堆在一起</b>：14 个人、零收入、零 App、估值 100 亿美元。'
                 '但真正的硬料是<b>它没有自己的管道</b>——iMessage 属苹果、WhatsApp 属 Meta、'
                 '支付走 Shopify／Stripe。与其讲「克制」，不如讲「<b>克制的人被管道夹在中间</b>」。',
        'facts': '2026-09-28 宣布 C 轮 <b>10 亿美元</b>，Sequoia、Benchmark、Coatue 联合领投，'
                 '<b>一个月估值翻 4 倍至百亿美元</b>（此前 25 亿）· 累计融资 <b>13.5 亿美元</b>，'
                 '零收入 · 创始人 Noah Shinn，23 岁，2023 年从东北大学辍学，'
                 '前 Sierra 研究员，著有 <b>Reflexion</b>（失败后用自然语言总结教训）与 '
                 '<b>τ-bench</b>（提出 passk 指标；GPT-4o 级 Agent 在零售场景 <b>pass8 低于 25%</b>）· '
                 '产品形态：<b>只有短信／电话／邮件，没有 App</b>，营销支出为零，不向用户收费，'
                 '靠交易抽佣 · Agent 执行前有独立于主模型的防火墙守门系统，9 月下旬上线主动幻觉检测 · '
                 '创始人自述：使用约 3 周后 <b>约 40% 绑定信用卡</b>，绑定敏感资产后留存约 <b>80%</b>'
                 '（<b>未经第三方审计</b>）· 邀请码在 eBay 炒到上百美元（对照 2021 年 Clubhouse）· '
                 '用户数超 <b>10 万</b>（The Information，9 月中）；对照 Muse 上线 12 天安装量约 280 万 · '
                 '9 月中开放 Trusted Person Network，已促成超 <b>30 万次</b> Agent 协调，9 月底加群聊 · '
                 '<b>管道全在别人手里</b>：Meta 自 2026-01-15 起禁止通用 AI 聊天机器人走 WhatsApp Business API；'
                 'Google 清理邮箱时把 Instinct 踢出；Delta 未允许第三方代订；Yelp 只许付费授权流量 · '
                 '抽佣模式：高端酒店愿为有效订单付 <b>20%–30%</b> 佣金，'
                 '按自述约 10 亿美元年化交易额 × 3%–5% 抽佣推算年收入约 <b>3000 万–5000 万美元</b>',
        'limit': '① <b>所有关键数字都是创始人自述</b>（绑卡率、留存、交易额），<b>未经第三方审计</b>，'
                 '公众号原文自己都标注了这一点；'
                 '② 9 月 29 日上线的商业化功能 Selections 推给用户<b>并未请求的推荐</b>，'
                 '公司至今未披露是否抽佣——<b>「反对说服机器」与「从推荐中赚钱」存在内在矛盾</b>；'
                 '③ <b>Clubhouse 对照是作者的比方，不是数据结论</b>；'
                 '④ A2A 协议已由 Linux Foundation 接管、150+ 组织加入，'
                 'Agent 间通信标准化会<b>持续削弱</b> Trusted Person Network 的独特性。',
        'fit': '适合做「行业现实」类长稿。数字扎实、反差密集，'
               '<b>「米聊式困局」的类比很有传播力</b>（作者已给出：功能对打微信，输在关系链不在自己手里）。'
               '要克制的是别把「估值高」写成「模式成立」。',
    },
    'Qwen3.8': {
        'angle': '如果做，钩子应落在<b>「音视频输入成本降 93%–98%」</b>这个价格数字上，'
                 '而不是「又发了个模型」。全模态模型真正的分水岭是<b>单位 token 成本</b>，'
                 '不是榜单分数。',
        'facts': '千问推出 <b>Qwen3.8-Omni-Flash</b>，全模态（文本／图像／音频／视频输入）+ '
                 '<b>1M 长上下文</b> · 30 项评测<b>平均提升超 26%</b> · '
                 '官方称音视频处理能力接近 Gemini 3.8 Flash · '
                 '<b>API 价格大幅下降：音频输入降 98%、音视频输入降 93%</b> · 开源相关工具 · '
                 '⚠️ 来源 AIbase「AI日报」栏目，页面标注日期 <b>2026-09-18</b>',
        'limit': '🔴 <b>这条有时效问题，不建议当今日头条</b>：原始页面标注 <b>9 月 18 日</b>，'
                 '是三周前的发布，今日仍在节点上流转。<b>若要做，必须重新核实是否已正式发布、'
                 '价格是否仍有效</b>。'
                 '另：① 30 项评测平均提升超 26% 是<b>厂商自测口径</b>，未见第三方复现；'
                 '② 「接近 Gemini 3.8 Flash」缺乏同基准同配置的对照说明。',
        'fit': '⚠️ 建议降级为「补做」而非「今日做」。若要做，需先重新核实时效与定价。',
        'stale': True,
    },
    'Surface': {
        'angle': '钩子是<b>价格</b>——顶配 5899.99 美元（约 4.2 万元），'
                 '一台 Windows 笔记本卖到接近 MacBook Pro 顶配。'
                 '配合「不限量智能」这个自造词，'
                 '可以做成「<b>本地跑大模型的自由，是要用钱买的</b>」。',
        'facts': '<b>2026-10-08</b> 凌晨 Windows 与 Surface 特别活动（爱范儿发于 10-08 11:09，36 氪转载）· '
                 '核心是英伟达 <b>RTX Spark</b>：<b>ARM 架构 SoC</b>，集成 GPU＋CPU＋最高 <b>128GB 统一内存</b>，'
                 '英伟达首次涉足 CPU 设计、CPU 部分与<b>联发科</b>联手 · 官方称最高 '
                 '<b>1 PFLOP FP4</b> 算力，可在本地跑 <b>Qwen 3.8 Flash Next</b> 等千亿参数模型 · '
                 '首发硬件 <b>Surface Laptop Ultra</b>：15 英寸 3:2 Mini-LED 触控屏（262 PPI）、'
                 'CNC 一体铝机身、约 2kg、3×USB4／HDMI／USB-A／SD／3.5mm，'
                 '新增 <b>Magnetic Connect</b> 磁吸充电（走标准 USB-C 口，非专有接口）· '
                 '<b>10 月 16 日开售，2599.99–5899.99 美元</b> · 同场还有 '
                 '5999 美元起的 RTX Spark Dev Box、算力 20 倍的 DGX Station for Windows · '
                 '纳德拉此前提出「<b>不限量智能</b>」：已购算力边际使用成本近免费，'
                 '区别于按 token 计费的云端 · 前情：6 月 GTC／Build 已宣布「重新发明 PC」· '
                 '发布前半小时几乎不谈 Windows／Surface，大谈 <b>MXC</b>（控制本地 Agent 权限边界的安全沙箱）',
        'limit': '① 「史上最强」「不限量智能」<b>都是微软与英伟达的自称</b>，'
                 '无第三方评测；发布会演示（Agent 串联 Photoshop／Blender／Premiere、'
                 '运行《战争机器：事变日》）均为官方素材；'
                 '② 这是 10-08 的消息，<b>今日已非最新</b>；'
                 '③ 爱范儿原始链接在 tophub 上<b>失效（ifanr.com/False）</b>，'
                 '本文事实取自 36 氪转载版，两处需分别核实；'
                 '④ 原作者自己也质疑：<b>微软过去 UWP／Win10／Win10X 都无疾而终</b>，'
                 '「没理由相信这次会成」——这个反方意见必须带上。',
        'fit': '技术受众友好（RTX Spark、统一内存、1 PFLOP 都是硬参数），'
               '但价格是双刃剑：<b>既是最强钩子，也是最大争议点</b>。'
               '建议与「本地智能到底省不省钱」合并成一个选题。',
    },
}


def _detail(e):
    """按标题片段取四小节。取不到就返回 None —— 宁可只出标题，也不编造事实。"""
    t = e['title']
    for k, v in DETAIL.items():
        if k in t:
            return v
    return None


def item_block(e, label, is_pick=False):
    d = _detail(e)
    hit = ''
    if e['n_src'] >= 2:
        hit += f'<span class="hit">{e["n_src"]} 源命中</span>'
    if e.get('must'):
        hit += '<span class="hit must">必抓</span>'
    if e['n_src'] < 2 and not e.get('must'):
        hit += '<span class="hit one">单源待核</span>'
    if d and d.get('stale'):
        hit += '<span class="hit stale">时效存疑</span>'
    hit += ''.join(f'<span class="tag">{html.escape(t)}</span>' for t in hook_tags(e))
    head = (f'<div class="ih"><span class="no">{html.escape(label)}</span>'
            f'<span class="it">{html.escape(e["title"])}</span>{hit}</div>')
    hits = hook_hits(e)
    hookline = ''
    if hits:
        seg = ' · '.join(
            f'<b>{html.escape(k)}</b>：{"、".join(html.escape(str(x)) for x in v)}'
            for k, v in hits.items())
        hookline = (f'<div class="lab">钩子命中（情绪／反差／知名度）</div>'
                    f'<div class="txt">{seg}</div>')

    if not d:
        # 单源条目不做深度核实（只列标题与来源），**不生成任何推测内容**
        srcs = '、'.join(html.escape(s) for s in e['src_names'])
        nature = '、'.join(dict.fromkeys(src_nature(s) for s in e['src_names']))
        body = (hookline +
                f'<div class="lab">来源与口径</div>'
                f'<div class="facts">{srcs}（{nature}）'
                f'{" · 命中必抓名单，单源也应收录" if e.get("must") else ""} · '
                f'仅一家报道，<b>未经交叉验证</b>。'
                f'本条<b>只列不做</b>：单一来源无法判断是否与已有事实冲突。</div>')
    else:
        body = (hookline +
                f'<div class="lab">可切入角度</div><div class="txt">{d["angle"]}</div>'
                f'<div class="lab">已核实的关键事实</div><div class="facts">{d["facts"]}</div>')
        if d.get('stale'):
            body += (f'<div class="lab">⏱ 时效核查</div>'
                     f'<div class="stale-note">{d["limit"]}</div>')
        else:
            body += (f'<div class="lab">反方 / 局限（写的时候必须带）</div>'
                     f'<div class="cnt">{d["limit"]}</div>')
        body += f'<div class="lab">与账号定位的匹配度</div><div class="fit">{d["fit"]}</div>'

    lk = ''
    if e.get('url_ok'):
        lk = f'<div class="lk">原文：<a href="{html.escape(e["url"])}">{html.escape(e["url"][:88])}</a></div>'
    else:
        alts = ''.join(
            f'<br>佐证链接：<a href="{html.escape(u)}">{html.escape(u[:88])}</a>'
            for u in e.get('alt_urls', []))
        lk = (f'<div class="lk">⚠️ 主链接在源站失效（tophub 给的是 '
              f'<code>…/False</code>，非本站解析问题），请用佐证链接：{alts or "无"}</div>')
    return (f'<div class="item{" pick" if is_pick else ""}">{head}{body}{lk}</div>')


def row_block(e, idx):
    srcs = '、'.join(html.escape(s) for s in e['src_names'])
    nature = '、'.join(dict.fromkeys(src_nature(s) for s in e['src_names']))
    flag = '⚠️' if not e.get('url_ok', True) else ''
    tags = '·'.join(hook_tags(e))
    meta = f'{html.escape(e["cat"])}／{html.escape(e["track"])}'
    if tags:
        meta += f' · 钩子 {html.escape(tags)}'
    if e.get('must'):
        meta += ' · <b>命中必抓名单</b>'
    return (f'<tr><td class="n">{idx:02d}</td>'
            f'<td>{flag}{html.escape(e["title"])}<div class="sub">{meta}</div></td>'
            f'<td class="src">{srcs}<div class="sub">{nature}</div></td></tr>')


def must_block(e, idx):
    """必抓单源：紧凑一行（保证不漏，又不占详细卡片的位置）。"""
    tags = '·'.join(hook_tags(e))
    link = (f'<a href="{html.escape(e["url"])}">原文</a>' if e.get('url_ok')
            else '⚠️ 链接失效')
    sub = html.escape(str(e.get('must') or '')) + (f' · 钩子 {html.escape(tags)}' if tags else '')
    return (f'<tr><td class="n">{idx:02d}</td>'
            f'<td>{html.escape(e["title"])}<div class="sub">{sub}</div></td>'
            f'<td class="src">{html.escape("、".join(e["src_names"]))}'
            f'<div class="sub">{link}</div></td></tr>')


def hook_block(e, label):
    """钩子候选：小新闻、单源、未核实 —— 只给线索，不做任何事实陈述。"""
    hits = hook_hits(e)
    seg = ' · '.join(
        f'<b>{html.escape(k)}</b>：{"、".join(html.escape(str(x)) for x in v)}'
        for k, v in hits.items())
    srcs = '、'.join(html.escape(s) for s in e['src_names'])
    nature = '、'.join(dict.fromkeys(src_nature(s) for s in e['src_names']))
    link = (f'<a href="{html.escape(e["url"])}">原文</a>' if e.get('url_ok')
            else '⚠️ 链接失效')
    tags = ''.join(f'<span class="tag">{html.escape(t)}</span>' for t in hook_tags(e))
    return (f'<div class="item hook"><div class="ih">'
            f'<span class="no hk">{html.escape(label)}</span>'
            f'<span class="it">{html.escape(e["title"])}</span>'
            f'<span class="hit hook">钩子 {hook_score(e)}/8</span>{tags}</div>'
            f'<div class="lab">命中的钩子词</div><div class="txt">{seg}</div>'
            f'<div class="lab">来源与口径</div>'
            f'<div class="facts">{srcs}（{nature}）· 单源未交叉验证，'
            f'钩子只说明「值得看一眼」，<b>做之前必须回原文核实</b>。</div>'
            f'<div class="lk">原文：{link}</div></div>')


def render_sections(prefix, multi, must_only, hook_cands, single_items, picks, pset, labels):
    """渲染一份主题文件（AI 或科技）的全部章节。

    结构（2026-10-09 用户定）：推荐 → 多源候选 → **钩子候选** → 必抓更新 → 单源候选。
    """
    h = ''

    if picks:
        pick_txt = ''.join(
            f'<p><b>{html.escape(labels.get(p["title"], ""))} {html.escape(p["title"])}</b> —— '
            + ((_detail(p) or {}).get('fit', '') or '') + '</p>'
            for p in picks if _detail(p))
        stale = [p for p in picks if (_detail(p) or {}).get('stale')]
        note = ''
        if stale:
            _s = '、'.join(f'{html.escape(labels.get(p["title"], ""))}'
                           f'（{html.escape(p["title"])}）' for p in stale)
            note = (f'<p>其中 <b>{_s} 时效存疑</b>：原始页面日期早于今日，'
                    f'建议降级为「补做」并重新核实时效与定价。</p>')
        h += (f'<h2>本轮推荐（{len(picks)} 条）</h2>'
              f'<div class="box ok">{pick_txt}{note}</div>')

    if multi:
        h += f'<h2>多源候选（{len(multi)} 条 · 编号 {prefix}01 起）</h2>'
        for e in multi:
            h += item_block(e, labels.get(e['title'], ''), is_pick=e['title'] in pset)

    if hook_cands:
        h += (f'<h2>钩子候选（{len(hook_cands)} 条 · 小新闻但钩子强）</h2>'
              '<div class="box">'
              '<p>这些条目<b>只有一家报道</b>，算不上大新闻，但标题里有可用的钩子'
              '（情绪／反差／知名度／数字），适合做「小而爆」的一条。'
              '此处<b>只给线索和钩子词</b>，内容没有核实过——挑中之后仍需回原文核实事实。</p>'
              '</div>')
        for i, e in enumerate(hook_cands, 1):
            h += hook_block(e, f'{prefix}H{i:02d}')

    if must_only:
        h += (f'<h2>必抓更新（{len(must_only)} 条 · 单源也收录）</h2>'
              '<div class="box key">'
              '<p>命中<b>AI 必抓名单</b>且带「发布／上线／更新」语义的条目，多为官方发布，'
              '常只有一家报道。此处只做<b>线索收录</b>——要做图文仍需回原文核实。'
              f'本表最多列 {MUST_CAP} 条（必抓只针对 AI 类，科技类不设）。</p>'
              '<table class="tb"><tr><th>#</th><th>标题</th><th>来源</th></tr>')
        for i, e in enumerate(must_only, 1):
            h += must_block(e, i)
        h += '</table></div>'

    if single_items:
        h += (f'<h2>单源候选（{len(single_items)} 条，仅列出不做）</h2>'
              '<div class="box warn">'
              '<p>下列条目<b>只有一个来源报道</b>，无法交叉验证，本轮<b>不做</b>。'
              '第二列标出了来源<b>性质</b>，便于判断这条值不值得单独去原站核。</p>'
              '<table class="tb"><tr><th>#</th><th>标题</th><th>来源与性质</th></tr>')
        for i, e in enumerate(single_items, 1):
            h += row_block(e, i)
        h += '</table></div>'
    return h


def render_page(cat, prefix, multi, hooks, must_only, single_items, picks, pset,
                date, now, n_src_total):
    """渲染一份主题文件（AI 或科技）的完整 HTML。"""
    # 必抓只针对 AI 类（2026-10-09 用户定）→ 科技页不出现「必抓名单」相关表述
    _must_lead = ('，以及<b>命中 AI 必抓名单</b>的条目（官方发布常只有 1 家报道，单源也收）'
                  if cat == 'AI' else '')
    labels = {}
    for i, e in enumerate(multi, 1):
        labels[e['title']] = f'{prefix}{i:02d}'
    # 推荐区可能补入必抓单源（多源不足 3 条时），给它们也编上号，避免推荐区出现空编号
    for i, e in enumerate([p for p in picks if p['title'] not in labels], 1):
        labels[e['title']] = f'{prefix}M{i:02d}'

    n_verified = sum(1 for e in multi if _detail(e))
    trk = Counter(e['track'] for e in multi + must_only + hooks + single_items)
    hook_stat = Counter(t for e in (multi + must_only + hooks) for t in hook_tags(e))
    body = render_sections(prefix, multi, must_only, hooks, single_items, picks, pset, labels)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>今日{cat}选题池 · {date}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">

<div class="eyebrow">选题池 · ① 线（{cat}新闻）</div>
<h1>今日{cat}选题池 · {date}</h1>
<div class="lead">
检索时点：<b>{now}（GMT+8）</b> · 本文件<b>只收 {cat} 类</b>，与另一份主题文件互不合并。
章节顺序：推荐 → 多源候选 → <b>钩子候选</b> → 必抓更新 → 单源候选。
主表收<b>≥2 个不同来源报道同一事件</b>的条目{_must_lead}。排序按 命中源数 → 钩子强度 → 热度。
<b>编号即建议制作顺序</b>。
</div>

<div class="stat">
  <div><b>{len(multi)}</b><span>多源候选（≥2 源）</span></div>
  <div><b>{len(hooks)}</b><span>钩子候选（单源·钩子强）</span></div>
  <div class="must"><b>{len(must_only)}</b><span>必抓更新（单源收录）</span></div>
  <div><b>{n_verified}</b><span>已逐条核实</span></div>
  <div><b>{len(picks)}</b><span>本轮推荐做</span></div>
  <div><b>{len(single_items)}</b><span>单源候选（不做）</span></div>
</div>

{body}

<h2>钩子判定规则与本轮命中</h2>
<div class="box key">
<p>钩子按用户给定的三类判定，权重 <b>情绪 &gt; 反差 ≈ 知名度</b>，条目上会标出命中的具体词：</p>
<ul>
  <li><b>情绪／情感（最重要）</b>：震惊 / 炸了 / 翻车 / 破防 / 争议 / 抵制 / 恐慌 …… 命中强情绪词 +3，一般情绪词 +1；</li>
  <li><b>反差</b>：竟然 / 居然 / 反而 / 反转 / 不再 / 首次 / 打破 …… 强反差结构 +2，一般反差词 +1；</li>
  <li><b>知名度</b>：黄仁勋 / 马斯克 / 陶哲轩 / 诺奖 / 菲尔兹奖 等顶流人物与机构 +2，其余知名品牌 +1；</li>
  <li><b>数字</b>：标题含具体数字（金额 / 倍数 / 百分比）+1，让情绪与反差可被量化。</li>
</ul>
<p>「钩子候选」一栏就是按这个分数从<b>单源小新闻</b>里挑出来的（门槛 {HOOK_MIN} 分，每主题最多 {HOOK_CAP} 条）。
本主题（多源候选 + 钩子候选 + 必抓更新）钩子命中统计：{html.escape(str(hook_stat.most_common()))}。
<b>钩子只用于排序与提示，不代表内容为真</b>——事实仍需回到原文核实。</p>
</div>

<h2>主流模型 / 主流软件「必抓名单」（仅 AI 类）</h2>
<div class="box">
<p>用户 2026-10-09 明确：主流模型与主流软件的更新<b>必须抓到</b>。这类官方发布常只有 1–2 家报道，
会被「≥2 源」门槛漏掉，因此<b>命中名单的条目单源也进主表</b>（打「必抓」标）。名单如下（
<b>只写家族名，不写版本号</b>——版本月月变，写死必然过期）：</p>
<p>{html.escape('；'.join(f'{n}（{"/".join(k[:3])}…）' for n, k in MUST_WATCH))}</p>
<p>⚠️ 本名单<b>只对 AI 类生效</b>：科技类不设必抓——名单里全是模型／软件品牌，
科技板块实际只捞得到零星 1 条，形同虚设。<br>
本名单是<b>采集口径</b>，不是内容判断：命中只说明「值得看一眼」，不代表这条一定是官方发布。</p>
</div>

<h2>去重与不做</h2>
<div class="box">
<ul>
  <li><b>不做厂商软文</b>：剔除「量子位的朋友们」这类付费推广栏（通篇「重塑生产力边界」营销话术，无独立信息）。</li>
  <li><b>不做链接失效且无有效佐证</b>的条目：爱范儿节点在 tophub 上给的链接本身就是
    <code>ifanr.com/False</code>（源站就是坏的，<b>不是解析问题</b>）；有其他源佐证的会在卡片里标出可用链接。</li>
  <li><b>不把同一站点的两个节点当两个源</b>：「少数派」与「少数派最新」是同一媒体，
    同一篇文章会两边同时出现，已按媒体归一去重——否则会凭空多出假的「2 源命中」。</li>
  <li><b>不把 HF 社区衍生版当官方发布的佐证</b>：官方发布与 HF 上的同代 GGUF／微调版是<b>同代不同物</b>，不能互相印证。</li>
</ul>
</div>

<h2>元信息与本轮局限</h2>
<div class="box warn">
<ul>
  <li><b>采集源</b>：{n_src_total} 个 —— tophub 17 节点（7 AI + 10 科技）、
    Hacker News 官方 Firebase API、HuggingFace Trending 模型、GitHub Trending 日榜。
    <b>两主题共用同一批采集数据</b>，只是按类别拆成两份文件。</li>
  <li><b>未采到的源</b>：Reddit（r/LocalLLaMA 等）与 arXiv RSS 本轮<b>未取到</b>——
    直连被拒／301，<b>是源受限不是规则排除</b>，可补跑。
    Hacker News 走的是官方 Firebase API（<code>news.ycombinator.com</code> 与
    <code>api.github.com</code> 本机不通，只有 <code>hacker-news.firebaseio.com</code> 稳定）。</li>
  <li><b>热度口径互不相通</b>：tophub 站内值、IT 之家「N 评」（评论数）、虎嗅（阅读量）、
    HN 得分、HF trendingScore <b>不可横向比较</b>，只在命中源数与钩子强度相同时作次级参考。</li>
  <li><b>数字可信度分层</b>：本池所有性能与业务数字均来自<b>厂商自测或媒体报道</b>；
    做图文时凡写「最强 / 领先 / 零成本」必须带反方。</li>
  <li><b>跨源判同口径</b>：判同只在两种情况成立 —— ① 两条标题共有一个<b>带数字的型号</b>
    （Qwen-Image-2.1 / Haiku 5.5）；② 共有一个<b>具体产品／技术实体</b>且标题相似度足够高。
    <b>只共现厂商名或产品线词（iphone / agent / 某厂名）不判同</b> ——
    宁可漏合（降级为单源）不可错合，错合会凭空造出「N 源命中」的假交叉核验。</li>
</ul>
</div>

<footer>生成于 {now}（GMT+8）· 单文件离线，无外部依赖<br>
① 线 = 选题池（本份为 <b>{html.escape(cat)}</b> 主题）　② 线 = GitHub 官方榜（star 增量口径），两份文件互不合并。
本主题赛道分布：{html.escape(' · '.join(f'{k} {v}' for k, v in trk.most_common()))}</footer>
</div>
</body>
</html>"""


def _cat_group(items, fn):
    """按 AI／科技 分组渲染卡片：组内先出 h3 小标题，再逐条渲染。"""
    h = ''
    for c in ('AI', '科技'):
        sub = [e for e in items if e['cat'] == c]
        if not sub:
            continue
        h += f'<h3>{c}（{len(sub)} 条）</h3>'
        h += ''.join(fn(e) for e in sub)
    return h


def _cat_table(items, rowfn):
    """按 AI／科技 分组渲染表格：每组一张表、编号在组内从 01 起。"""
    h = ''
    for c in ('AI', '科技'):
        sub = [e for e in items if e['cat'] == c]
        if not sub:
            continue
        h += f'<h3>{c}（{len(sub)} 条）</h3>'
        h += '<table class="tb"><tr><th>#</th><th>标题</th><th>来源</th></tr>'
        for i, e in enumerate(sub, 1):
            h += rowfn(e, i)
        h += '</table>'
    return h


def render_merged(multi, hooks, must_items, single_items, picks, pset, date, now, n_src_total):
    """合并版（2026-10-09 用户要求）：AI 与科技收进**同一份 HTML**。

    章节顺序不变（推荐 → 多源候选 → 钩子候选 → 必抓更新 → 单源候选），
    但每章内部按主题分「AI / 科技」小节，条目各自标出类别 ——
    合到一份文件，同时不让两类内容混着看。
    """
    labels = {}
    for pre, c in (('A', 'AI'), ('T', '科技')):
        for i, e in enumerate([x for x in multi if x['cat'] == c], 1):
            labels[e['title']] = f'{pre}{i:02d}'
    # 推荐区可能补入必抓单源（多源不足 3 条时），给它们也编号，避免推荐区出现空编号
    for i, e in enumerate([p for p in picks if p['title'] not in labels], 1):
        labels[e['title']] = f'M{i:02d}'
    # 钩子编号按**渲染顺序**连续编（AI 组在前、科技组在后），不按全池排序 ——
    # 否则分组后会出现「AI 组是 H06/H09/H11…」这种跳号，没法口头引用。
    hk, _n = {}, 0
    for _c in ('AI', '科技'):
        for e in [x for x in hooks if x['cat'] == _c]:
            _n += 1
            hk[e['title']] = f'H{_n:02d}'

    n_verified = sum(1 for e in multi if _detail(e))
    trk = Counter(e['track'] for e in multi + must_items + hooks + single_items)
    hook_stat = Counter(t for e in (multi + must_items + hooks) for t in hook_tags(e))
    n_multi_ai = sum(1 for e in multi if e['cat'] == 'AI')
    n_hk_ai = sum(1 for e in hooks if e['cat'] == 'AI')
    # 必抓已限定 AI 类（2026-10-09 用户定）→ 不需要再按类拆分计数
    n_si_ai = sum(1 for e in single_items if e['cat'] == 'AI')

    out = [f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>今日 AI 科技选题池 · {date}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">

<div class="eyebrow">选题池 · ① 线（AI 科技新闻）</div>
<h1>今日 AI 科技选题池 · {date}</h1>
<div class="lead">
检索时点：<b>{now}（GMT+8）</b> · 本文件<b>同时收录 AI 与科技两类</b>，
每章内部再分「AI / 科技」小节，条目上保留类别标识。
章节顺序：推荐 → 多源候选 → <b>钩子候选</b> → 必抓更新 → 单源候选。
主表收<b>≥2 个不同来源报道同一事件</b>的条目，以及<b>命中 AI 必抓名单</b>的条目
（官方发布常只有 1 家报道，单源也收；<b>必抓只针对 AI 类，科技类不设</b>）。排序按 命中源数 → 钩子强度 → 热度。
<b>编号即建议制作顺序</b>（`A`＝AI，`T`＝科技，`H`＝钩子候选，`M`＝推荐里补位的必抓条目）。
</div>

<div class="stat">
  <div><b>{len(multi)}</b><span>多源候选（AI {n_multi_ai} / 科技 {len(multi) - n_multi_ai}）</span></div>
  <div><b>{len(hooks)}</b><span>钩子候选（AI {n_hk_ai} / 科技 {len(hooks) - n_hk_ai}）</span></div>
  <div class="must"><b>{len(must_items)}</b><span>必抓更新（仅 AI 类）</span></div>
  <div><b>{n_verified}</b><span>已逐条核实</span></div>
  <div><b>{len(picks)}</b><span>本轮推荐做</span></div>
  <div><b>{len(single_items)}</b><span>单源候选（AI {n_si_ai} / 科技 {len(single_items) - n_si_ai}）</span></div>
</div>
"""]

    # ---------- 推荐 ----------
    if picks:
        pick_txt = ''.join(
            f'<p><span class="tag">{html.escape(p["cat"])}</span>'
            f'<b>{html.escape(labels.get(p["title"], ""))} {html.escape(p["title"])}</b> —— '
            + ((_detail(p) or {}).get('fit', '') or '') + '</p>'
            for p in picks if _detail(p))
        stale = [p for p in picks if (_detail(p) or {}).get('stale')]
        note = ''
        if stale:
            _s = '、'.join(f'{html.escape(labels.get(p["title"], ""))}'
                           f'（{html.escape(p["title"])}）' for p in stale)
            note = (f'<p>其中 <b>{_s} 时效存疑</b>：原始页面日期早于今日，'
                    f'建议降级为「补做」并重新核实时效与定价。</p>')
        out.append(f'<h2>本轮推荐（{len(picks)} 条）</h2>'
                   f'<div class="box ok">{pick_txt}{note}</div>')

    # ---------- 多源候选 ----------
    if multi:
        out.append(f'<h2>多源候选（{len(multi)} 条 · 编号 A01 / T01 起）</h2>')
        out.append(_cat_group(multi, lambda e: item_block(
            e, labels.get(e['title'], ''), is_pick=e['title'] in pset)))

    # ---------- 钩子候选 ----------
    if hooks:
        out.append(f'<h2>钩子候选（{len(hooks)} 条 · 小新闻但钩子强）</h2>'
                   '<div class="box">'
                   '<p>这些条目<b>多数只有一家报道</b>，算不上大新闻，但标题里有可用的钩子'
                   '（情绪／反差／知名度／数字），适合做「小而爆」的一条。'
                   '此处<b>只给线索和钩子词</b>，内容没有核实过——挑中之后仍需回原文核实事实。</p>'
                   '</div>')
        out.append(_cat_group(hooks, lambda e: hook_block(e, hk[e['title']])))

    # ---------- 必抓更新 ----------
    if must_items:
        out.append(f'<h2>必抓更新（{len(must_items)} 条 · 单源也收录）</h2>'
                   '<div class="box key">'
                   '<p>命中<b>AI 必抓名单</b>且带「发布／上线／更新」语义的条目，多为官方发布，'
                   '常只有一家报道。此处只做<b>线索收录</b>——要做图文仍需回原文核实。'
                   f'全表最多列 {MUST_CAP} 条<span style="color:#6B7280">（必抓只针对 AI 类，科技类不设）</span>。</p>'
                   '</div>')
        out.append(_cat_table(must_items, must_block))

    # ---------- 单源候选 ----------
    if single_items:
        out.append(f'<h2>单源候选（{len(single_items)} 条，仅列出不做）</h2>'
                   '<div class="box warn">'
                   '<p>下列条目<b>只有一个来源报道</b>，无法交叉验证，本轮<b>不做</b>。'
                   '表格里标出了来源<b>性质</b>，便于判断这条值不值得单独去原站核。</p>'
                   '</div>')
        out.append(_cat_table(single_items, row_block))

    # ---------- 规则与元信息 ----------
    out.append(f"""<h2>钩子判定规则与本轮命中</h2>
<div class="box key">
<p>钩子按用户给定的三类判定，权重 <b>情绪 &gt; 反差 ≈ 知名度</b>，条目上会标出命中的具体词：</p>
<ul>
  <li><b>情绪／情感（最重要）</b>：震惊 / 炸了 / 翻车 / 破防 / 争议 / 抵制 / 恐慌 …… 命中强情绪词 +3，一般情绪词 +1；</li>
  <li><b>反差</b>：竟然 / 居然 / 反而 / 反转 / 不再 / 首次 / 打破 …… 强反差结构 +2，一般反差词 +1；</li>
  <li><b>知名度</b>：黄仁勋 / 马斯克 / 陶哲轩 / 诺奖 / 菲尔兹奖 等顶流人物与机构 +2，其余知名品牌 +1；</li>
  <li><b>数字</b>：标题含具体数字（金额 / 倍数 / 百分比）+1，让情绪与反差可被量化。</li>
</ul>
<p>「钩子候选」一栏就是按这个分数从<b>单源小新闻</b>里挑出来的（门槛 {HOOK_MIN} 分，全池最多 {HOOK_CAP} 条）。
全池（多源候选 + 钩子候选 + 必抓更新）钩子命中统计：{html.escape(str(hook_stat.most_common()))}。
<b>钩子只用于排序与提示，不代表内容为真</b>——事实仍需回到原文核实。</p>
</div>

<h2>主流模型 / 主流软件「必抓名单」（仅 AI 类）</h2>
<div class="box">
<p>用户 2026-10-09 明确：主流模型与主流软件的更新<b>必须抓到</b>。这类官方发布常只有 1–2 家报道，
会被「≥2 源」门槛漏掉，因此<b>命中名单的条目单源也进主表</b>（打「必抓」标）。名单如下（
<b>只写家族名，不写版本号</b>——版本月月变，写死必然过期）：</p>
<p>{html.escape('；'.join(f'{n}（{"/".join(k[:3])}…）' for n, k in MUST_WATCH))}</p>
<p>⚠️ 本名单<b>只对 AI 类生效</b>：科技类不设必抓——名单里全是模型／软件品牌，
科技板块实际只捞得到零星 1 条，形同虚设。<br>
本名单是<b>采集口径</b>，不是内容判断：命中只说明「值得看一眼」，不代表这条一定是官方发布。</p>
</div>

<h2>去重与不做</h2>
<div class="box">
<ul>
  <li><b>不做厂商软文</b>：剔除「量子位的朋友们」这类付费推广栏（通篇「重塑生产力边界」营销话术，无独立信息）。</li>
  <li><b>不做链接失效且无有效佐证</b>的条目：爱范儿节点在 tophub 上给的链接本身就是
    <code>ifanr.com/False</code>（源站就是坏的，<b>不是解析问题</b>）；有其他源佐证的会在卡片里标出可用链接。</li>
  <li><b>不把同一站点的两个节点当两个源</b>：「少数派」与「少数派最新」是同一媒体，
    同一篇文章会两边同时出现，已按媒体归一去重——否则会凭空多出假的「2 源命中」。</li>
  <li><b>不把 HF 社区衍生版当官方发布的佐证</b>：官方发布与 HF 上的同代 GGUF／微调版是<b>同代不同物</b>，不能互相印证。</li>
</ul>
</div>

<h2>元信息与本轮局限</h2>
<div class="box warn">
<ul>
  <li><b>采集源</b>：{n_src_total} 个 —— tophub 17 节点（7 AI + 10 科技）、
    Hacker News 官方 Firebase API、HuggingFace Trending 模型、GitHub Trending 日榜。</li>
  <li><b>未采到的源</b>：Reddit（r/LocalLLaMA 等）与 arXiv RSS 本轮<b>未取到</b>——
    直连被拒／301，<b>是源受限不是规则排除</b>，可补跑。
    Hacker News 走的是官方 Firebase API（<code>news.ycombinator.com</code> 与
    <code>api.github.com</code> 本机不通，只有 <code>hacker-news.firebaseio.com</code> 稳定）。</li>
  <li><b>分类口径</b>：AI / 科技按标题关键词判定，<b>会有少量跨类内容</b>
    （如「AI 芯片」既算 AI 也算科技）。本文件两类同页展示、逐条标注类别；
    若某条归错，以条目上的赛道标签为准，不影响它本身的可用性。</li>
  <li><b>热度口径互不相通</b>：tophub 站内值、IT 之家「N 评」（评论数）、虎嗅（阅读量）、
    HN 得分、HF trendingScore <b>不可横向比较</b>，只在命中源数与钩子强度相同时作次级参考。</li>
  <li><b>数字可信度分层</b>：本池所有性能与业务数字均来自<b>厂商自测或媒体报道</b>；
    做图文时凡写「最强 / 领先 / 零成本」必须带反方。</li>
  <li><b>跨源判同口径</b>：判同只在两种情况成立 —— ① 两条标题共有一个<b>带数字的型号</b>
    （Qwen-Image-2.1 / Haiku 5.5）；② 共有一个<b>具体产品／技术实体</b>且标题相似度足够高。
    <b>只共现厂商名或产品线词（iphone / agent / 某厂名）不判同</b> ——
    宁可漏合（降级为单源）不可错合，错合会凭空造出「N 源命中」的假交叉核验。</li>
</ul>
</div>

<footer>生成于 {now}（GMT+8）· 单文件离线，无外部依赖<br>
① 线 = AI 科技选题池（本份为 AI＋科技合并版）　② 线 = GitHub 官方榜（star 增量口径），两份文件互不合并。
全池赛道分布：{html.escape(' · '.join(f'{k} {v}' for k, v in trk.most_common()))}</footer>
</div>
</body>
</html>""")

    return '\n'.join(out)


def main():
    """默认：**输出一份合并版 HTML**（AI＋科技同页，章内分节）。

    传 `--split` 可回到「AI / 科技 各一份」的旧输出（2026-10-09 之前的结构），
    供随时回退对照。
    """
    argv = sys.argv[1:]
    split = '--split' in argv
    _pos = [a for a in argv if not a.startswith('--')]
    date = _pos[0] if _pos else datetime.now().strftime('%Y-%m-%d')
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    events, missing, raw_items = collect()
    multi, must_only, hooks, single_items, picks, dropped = build(events, date)
    pset = {p['title'] for p in picks}
    n_src_total = len({i['src'] for i in raw_items})
    os.makedirs(OUT_DIR, exist_ok=True)
    outs = []

    if split:
        for cat, prefix in (('AI', 'A'), ('科技', 'T')):
            c_multi = [e for e in multi if e['cat'] == cat]
            c_hooks = [e for e in hooks if e['cat'] == cat]
            c_must = [e for e in must_only if e['cat'] == cat][:MUST_CAP]
            c_single = [e for e in single_items if e['cat'] == cat]
            c_picks = [p for p in picks if p['cat'] == cat]
            doc = render_page(cat, prefix, c_multi, c_hooks, c_must, c_single, c_picks,
                              pset, date, now, n_src_total)
            out = os.path.join(OUT_DIR, f'今日{cat}选题池_{date}.html')
            with open(out, 'w', encoding='utf-8') as f:
                f.write(doc)
            outs.append(out)
            print(f'--- {cat} ---')
            print(f'  RESULT 多源 {len(c_multi)} / 钩子 {len(c_hooks)} / 必抓 {len(c_must)}'
                  f'（全量 {len([e for e in must_only if e["cat"] == cat])}，限 {MUST_CAP}）'
                  f' / 单源 {len(c_single)}')
            print('  OUT   ' + out)
        print(f'SRC     {n_src_total} 个源 · 事件 {len(events)} · 单源截掉 {dropped}')
        return outs

    # 必抓：**只针对 AI 类**（2026-10-09 用户定），上限 20 条。
    # must_only 里现在只有 AI 条目，balanced_pick 实际退化为单类按序截断 —— 保留调用，
    # 将来若要恢复「科技也有必抓」，只要去掉 build() 里的 cat 前置过滤即可。
    must_items = balanced_pick(must_only, MUST_CAP)
    doc = render_merged(multi, hooks, must_items, single_items, picks, pset,
                        date, now, n_src_total)
    out = os.path.join(OUT_DIR, f'今日AI科技选题池_{date}.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(doc)
    outs.append(out)

    def _cnt(items, c):
        return sum(1 for e in items if e['cat'] == c)

    print(f'RESULT 多源 {len(multi)}（AI {_cnt(multi,"AI")} / 科技 {_cnt(multi,"科技")}）'
          f' / 钩子 {len(hooks)}（AI {_cnt(hooks,"AI")} / 科技 {_cnt(hooks,"科技")}）'
          f' / 必抓 {len(must_items)}（全量 {len(must_only)}，限 {MUST_CAP}）'
          f' / 单源 {len(single_items)}（AI {_cnt(single_items,"AI")}'
          f' / 科技 {_cnt(single_items,"科技")}）')
    print(f'VERIFIED 逐条核实 {sum(1 for e in multi if _detail(e))} / {len(multi)}')
    print('推荐  ' + ' ｜ '.join(
        f'[{p["cat"]}]{labels_hint(p, multi)} {p["title"][:28]}' for p in picks))
    print('OUT   ' + out)
    print(f'SRC     {n_src_total} 个源 · 事件 {len(events)} · 单源截掉 {dropped}')
    return outs


def labels_hint(p, multi):
    """推荐区里显示编号（与页面一致）：多源按 A/T 序，补位的必抓记 M。"""
    for pre, c in (('A', 'AI'), ('T', '科技')):
        seq = [e for e in multi if e['cat'] == c]
        for i, e in enumerate(seq, 1):
            if e['title'] == p['title']:
                return f'{pre}{i:02d}'
    return 'M--'


if __name__ == '__main__':
    main()
