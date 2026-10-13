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
    # ⚠️ 2026-10-10 实测踩坑：`ents()` 会把「iPhone 18 Pro」拆成 iphone / pro 两个实体，
    #    于是「只共现一个产品线词不判同」的护栏被绕过 —— 三条**不同**的 iPhone 18 Pro 新闻
    #    （砍单传闻 / 上手体验 / 美版有问题）被并成一条「3 源命中」。产品线词与
    #    产品修饰词必须整体当通用词剔除。同理补上英文通用词，防 HN/GitHub 条目靠
    #    open / source / reverse 这种词被错合。
    'iphone', 'ipad', 'macbook', 'airpods', 'imac', 'mac',
    'pro', 'max', 'plus', 'ultra', 'mini', 'air', 'lite', 'promax',
    'source', 'open', 'anything', 'engineer', 'reverse', 'people',
    'core', 'projects', 'using', 'with', 'model', 'models',
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
        # ⚠️ 停更节点本轮不进合并（用户规则 5）：节点页仍在，但条目两天不变 → 不参与。
        if it['src_name'] in SKIP_SRC:
            continue
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
            dom = (MEDIA_ALIAS.get(m['src_name'])
                   or m['src_name'].split('日榜')[0].split('最新')[0].strip())
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
            # 发布时间：取该事件**所有来源里最早**的那个（2026-10-12 新增）
            'pub': pub_of([m['url'] for m in ms if m.get('url')]),
        })
    # ---- ④(a) 人工补录的多源事件（逐日更新，见文件头 MANUAL_MULTI）----
    if MANUAL_MULTI:
        _kw = [k for m in MANUAL_MULTI for k in m['absorb_kw']]
        events = [e for e in events if not any(k in e['title'].lower() for k in _kw)]
        for m in MANUAL_MULTI:
            names = [n for n, _ in m['sources']]
            events.append({
                'title': m['title'], 'cat': m['cat'],
                'track': m.get('track') or track_of(m['title'], m['cat']),
                'url': m['sources'][0][1], 'n_src': len(names), 'src_names': names,
                'url_ok': True, 'alt_urls': [u for _, u in m['sources'][1:]],
                'heat': None, 'heat_src': None, 'heat_kind': '',
                'all_titles': [f'人工补录（{m["note"]}）'], 'src': 'manual',
                'pub': pub_of([u for _, u in m['sources']]),
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

# ============ 发布时间（2026-10-12 新增）============
# 用户反馈：「AI 必抓」里发布时间很久的新闻还留在里面，应该取一个合理的时间范围
# （「我认为是 7 天内吧」）；另外要把**各来源里最早的那个时间**标进页面。
MUST_WINDOW_DAYS = 7      # 必抓只收最近 N 天；超期的降到「超期未采用」单列，不静默丢
PUBTIME = {}              # url -> {'day':'YYYY-MM-DD','iso':...,'src':...}（fetch_pubtime.py 产物）


def load_pubtime():
    """读 fetch_pubtime.py 的产物。文件缺失时静默降级为空表（页面标「未取到」）。"""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pubtime.json')
    if not os.path.exists(p):
        return 0
    try:
        with open(p, encoding='utf-8') as f:
            PUBTIME.update(json.load(f))
    except Exception:
        return 0
    return len(PUBTIME)


def pub_of(urls):
    """从一组来源 URL 里取**最早**的发布时间。

    ⚠️ 用户口径是「所有源里面最早的时间」—— 同一件事被多家报道时，
    最早的报道时刻才代表它**什么时候开始发生**；晚报的那家不算「新」。
    """
    best = None
    for u in urls:
        v = PUBTIME.get(u)
        if not v or not v.get('day'):
            continue
        if (best is None or v['day'] < best['day']
                or (v['day'] == best['day'] and str(v.get('iso', '')) < str(best.get('iso', '')))):
            best = v
    return best


def pub_days(pub, date):
    """距今多少天（今天=0）。取不到时间返回 None —— 不猜、不用「今天」兜底。"""
    if not pub:
        return None
    try:
        d1 = datetime.strptime(pub['day'], '%Y-%m-%d').date()
        d0 = datetime.strptime(date, '%Y-%m-%d').date()
        return (d0 - d1).days
    except Exception:
        return None


def pub_tag(e):
    """条目上的时间标签。取不到时**明写「时间未取到」**，不用猜测值填充。"""
    d = e.get('pub_days')
    pub = e.get('pub') or {}
    if d is None:
        return '<span class="pt unk">时间未取到</span>'
    when = html.escape(str(pub.get('iso', ''))[:16].replace('T', ' '))
    if d < 0:
        return f'<span class="pt">发布于 {when}</span>'
    rel = '今天' if d == 0 else ('昨天' if d == 1 else f'{d} 天前')
    cls = 'pt old' if d > MUST_WINDOW_DAYS else 'pt'
    return f'<span class="{cls}">{rel} · {when}</span>'

# ============ 本轮（2026-10-11）逐日参数：节点时效自检 + 与已发成品查重 ============
# ⚠️ 这一块**每天都要按当轮实测改**，写在代码里是为了出 HTML 时能自动带出来，
#    避免「口头说查过了、页面上没写」。
# ① 时效自检（用户规则 5）：与昨日同节点条目**完全重合** = 停更 → 本轮不参与合并。
STALE_NODES = [
    ('威锋网', '本日 30 条与 10-12 重合 <b>27 条</b>（仅 3 条新增：AirPods 5 排灯节版、'
     'HomeView 11 月中旬发货、一加 16 发布）；10-11 同为 27/30',
     '停更 · 两日高重合 → 划掉'),
    ('MIT Technology Review', '本日 10 条与 10-12 重合 <b>7 条</b>；最新 3 条为 10-12（非今日），'
     '且非 AI 主线', '停更 · 连续三天 → 划掉'),
    ('AIbase', '本日 10 条与 10-12 重合 <b>9 条</b>；池内 10 条全是 9-22—10-12 的「AI 日报」'
     '<b>永久链接页</b>（页内时间会被渲染成「今天」，不可信）',
     '高重合 · 保留，须回原页核日期'),
    ('掘金', '本日 20 条与 10-12 重合 <b>16 条</b>（「本周最热」周榜形态，天然高重合）',
     '高重合 · 保留，须回原页核日期'),
    ('量子位', '本日 10 条与 10-12 重合 <b>5 条</b>', '滚动偏慢 · 保留'),
    ('AI工具集', '本日 10 条与 10-12 重合 <b>6 条</b>', '中高重合 · 保留，须回原页核日期'),
    ('36氪 AI 频道 / IT之家 / Readhub / 36氪 24h',
     '与 10-12 <b>零重合</b>（30/30、12/12、20/20、8/8 全量刷新）', '正常刷新'),
    ('AI产品榜 / 极客公园 / 爱范儿 / 果壳科学人 / 少数派 / 虎嗅热文',
     '不在本轮任务指定的 10 个节点内，<b>未采集</b>', '未纳入本轮'),
]
# ①b 划掉（不参与合并）的节点 —— 与 STALE_NODES 对应，只是「保留观察」的不列入。
SKIP_SRC = {'AI产品榜', 'MIT Tech Review', 'MIT Technology Review', '威锋网', '极客公园'}
# ④ 本轮**人工补录**（逐日更新，两类）：
#   (a) MANUAL_MULTI：同一事件被多家独立媒体报道，但**标题差异太大、自动判同合不到一起**
#       （现行判同口径宁可漏合不可错合）→ 人工核过之后补一条多源事件，
#       并把同一事件的原单源条目按 absorb_kw 从池里摘掉，避免同一件事在两处出现。
#   (b) MUST_EXTRA_KW：命中必抓名单、确实是官方功能更新，但标题里没有「发布／上线／更新」
#       这类语义词（例如「XX 开启公测」）→ 人工补进必抓。
MANUAL_MULTI = []
# ⚠️ 本轮（10-13）**未启用人工补录多源** —— 逐条比对后，本轮池内**没有任何事件被两家及以上
#    独立媒体各自成稿**。36氪 本轮 4 篇高价值 AI 稿均署外部来源并经授权发布，属同一通道；
#    与 36氪同节点/跨节点的「Muse」「一加 16」等，要么同一家（36氪两节点已按媒体归一），
#    要么另一家是聚合站（Readhub）。宁可报「独立多源 0」，也不把转载凑成 2 源。
MUST_EXTRA_KW = ['muse wonder']
# ⚠️ 本轮人工扩边 1 条：Meta 的 <b>Muse Wonder</b> 10-12 正式发布（Meta 自家旗舰模型），
#    但两家节点给的标题里都没有「发布／上线」这类语义词（「肘击 Astra」「碾压 GPT-6」），
#    且 `MUST_WATCH` 的 Meta 条目只收 llama / meta ai 两个词 —— 两个条件都不满足，
#    自动判不进必抓。人工确认是官方旗舰发布后，按关键词补进必抓。
# ② 与已发成品查重（用户规则 7）：只列**成品目录**（YYYYMMDD_主题），不做二次创作。
DUP_DONE = [
    ('OpenAI dots / Dots 智能体', ['20261001_OpenAIDots上线'], ['dots']),
    ('Claude Haiku 5.5', ['20261008_ClaudeHaiku55'], ['haiku 5.5', 'haiku5.5']),
    ('Claude Sonnet 5.5', ['20260929_ClaudeSonnet55发布'], ['sonnet 5.5']),
    ('Gemini 4 Argon / Pro', ['20261001_Gemini4Argon发布', '20260928_Gemini4Pro突然曝光'],
     ['gemini 4 argon', 'gemini 4 pro']),
    ('GPT-6 本体与智能界面', ['20260928_GPT6Astra首发评测', '20260930_GPT61Sol上线',
                       '20261008_GPT6智能界面'],
     ['gpt-6 sol', 'gpt6 sol', 'gpt-6 luna', 'gpt 6 luna', 'iui', '智能用户界面']),
    ('OpenAI「28 天计划」', ['20261005_OpenAI28天承诺'], ['28 天计划', '28天计划']),
    ('谷歌办公 Agent（Gemini Agent）', ['20261009_谷歌办公Agent'],
     ['gemini agent', 'gemini智能体', '办公智能体', '办公agent']),
    ('英伟达笔记本 / RTX Spark Surface', ['20261009_英伟达笔记本'], ['rtx spark']),
    ('苹果 AI 硬件一进一退', ['20261005_苹果AI硬件一进一退'],
     ['暂停开发一款配备摄像头的 ai 可穿戴', '配备摄像头的 ai 可穿戴']),
    ('DeepSeek 兼容 Claude 插件', ['20261005_DeepSeek兼容Claude插件'],
     ['deepseek 兼容 claude', 'claude 插件']),
    ('华为麒麟 9050', ['20261005_华为麒麟9050逻辑折叠'], ['麒麟 9050', '麒麟9050']),
    ('OpenAI 文字水印', ['20261006_OpenAI文字水印'], ['文字水印']),
    # ---- 2026-10-11 新增：10-09 / 10-10 新发的成品 ----
    ('AI「克隆」Adobe 全家桶', ['20261010_Claude重造Adobe'], ['adobe全家桶']),
    ('字节发现 DeepSeek 相位敏感性', ['20261010_字节发现DeepSeek站位'], ['时强时弱', '相位敏感']),
    ('陶哲轩 / 数学界与 OpenAI（同一事件链）', ['20261010_陶哲轩转发抵制OpenAI'], ['陶哲轩']),
    ('Jev 估值与融资（同一事件链）', ['20260930_Jev是什么'],
     ['估值暴涨37倍', '估值翻至75亿美元', 'jev背后公司']),
    ('10-10 已发：诺奖话题', ['20261010_诺奖被偷25年'], ['诺奖被偷', '被偷25年']),
    # ---- 2026-10-12 追加 ----
    ('SpaceX AI 改名 SpaceX SI', ['20261005_SpaceXAI改名SpaceXSI'],
     ['spacexai改名', 'spacex 改名', 'spacexsi']),
    # ---- 2026-10-13 追加：10-12 新发的成品（两平台目录一致，共 41 个主题）----
    ('苹果 iPhone Duo 预售 / 加单（10-12 已发）', ['20261012_iPhoneDuo预售'], ['iphone duo']),
    ('英伟达洽谈收购 Reflection AI（10-12 已发）', ['20261012_英伟达收购ReflectionAI'],
     ['reflection ai', 'reflectionai']),
    ('Jev 估值 24 天翻 37 倍（10-12 已发 · 同一事件链）', ['20261012_Jev估值24天翻37倍'],
     ['24 天估值暴涨', '24天估值暴涨', '估值暴涨 37 倍']),
    ('GitHub 周榜 Top5（10-12 已发 · ② 线产品）', ['20261012_GitHub周榜Top5'],
     ['github 周榜', 'github周榜top']),
    ('OpenAI 722 篇数学手稿 / 数学界反应（10-10 已发 · 同一事件链）',
     ['20261010_陶哲轩转发抵制OpenAI'],
     ['摧毁了我的研究领域', '722 篇数学', '数学手稿', '地毯式轰炸']),
]

RUBRIC_NOTE = '与已发成品重合（不做）'

# ④ 来源独立性（2026-10-10 起）：**聚合站与转载不构成第二个来源**。
#    用户规则「不把同一站点的两个节点当两个源」的同一道理 —— 同一篇稿件换站再发，
#    仍然是**一个新闻源**，把它算成「2 源命中」就是伪造交叉核验。
NON_INDEPENDENT = {'Readhub'}   # 纯聚合站，自身不产稿，只收录别家稿件
# ⚠️ 2026-10-11 实测踩坑：`36氪AI频道` 与 `36氪24h` 是**同一家 36氪的两个节点** ——
#    本轮 36氪24h 的 8 条里 5 条与 AI 频道重合。不按媒体归一，就会凭空造出「2 源命中」。
#    （`IT之家日榜`→`IT之家`、`少数派最新`→`少数派` 已在原逻辑里按后缀剥掉，不重复列。）
MEDIA_ALIAS = {'36氪AI频道': '36氪', '36氪24h': '36氪'}
REPOST = [
    (frozenset(('36氪', '果壳科学人')),
     '36氪 p/4020840060391299 页面署「果壳 · 2026-10-12 07:40」，为授权转载（原文来自公众号「果壳」）'),
]


def indep_count(e):
    """独立来源数：聚合站不计；命中转载对的整对只按 1 个算。"""
    names = list(dict.fromkeys(e.get('src_names') or []))
    n = len([s for s in names if s not in NON_INDEPENDENT])
    note = ''
    for grp, why in REPOST:
        if grp <= set(names):
            n -= (len(grp) - 1)
            note = note or why
    if note == '' and len(names) and all(s in NON_INDEPENDENT for s in names):
        note = '全部来源均为聚合站'
    return max(n, 0), note


# ③ 本轮网络实测时点与检索侧结论（逐日更新）
PROBE_TIME = '2026-10-13 09:37'
WEBSEARCH_NOTE = (
    '本轮共发起 <b>5 次</b>限定域名检索（<code>officechai.com</code> / <code>the-decoder.com</code> / '
    '<code>dataconomy.com</code> / <code>agihunt.info</code> / <code>promptblueprints.tech</code> / '
    '<code>tldrocket.com</code> / <code>nokiapoweruser.com</code> / <code>kocpc.com.tw</code>，'
    '时间窗 d2–d3），<b>只有 <code>agihunt.info</code> 返回 1 条</b>'
    '（其「Research」栏目当日汇编），其余域名一律无返回。'
    '该条为<b>聚合站的当日研究汇编（单源、非独立核实）</b>，故<b>不进主表</b>，'
    '只作为线索如实登记，做之前须回原始论文／官方页核。<b>本轮的境外新增线索</b>：<br>'
    '① <b>【新线索 · 单源待核】Epoch AI 数据：超过 38% 的数学论文已标注使用 AI</b>'
    '（18 个受追踪子领域中有 3 个过半论文声明 AI 协助）—— 与今日池内「OpenAI 数学手稿」'
    '「菲尔兹奖得主」同属一条趋势线。<br>'
    '② <b>【新线索 · 单源待核】GPT-6 Astra 在 RSIArena Stage 1 盲测中拿下第一</b>；'
    'Grok 4.7 进入前二（据称提前 41 小时被截断、约 70% GPU 预算未用完）。<br>'
    '③ <b>【新线索 · 单源待核】Sakana AI 发布 MASS</b>：用「集体智能」做递归自我改进的'
    '研究项目（<code>pub.sakana.ai/mass</code>）。<br>'
    '④ <b>【新线索 · 单源待核】AuroraIMG-6M 开源</b>：仅 600 万参数的文本生图模型，'
    '不需要大文本编码器与 VAE，可生成 64×64 可辨认图像。<br>'
    '⑤ <b>【新线索 · 单源待核】RoboWorld Challenge 2026</b> 在 NeurIPS 2026 启动，'
    '考察世界模型的「语言落地／预判未来状态／安全行动」三项能力。<br>'
    '⑥ <b>【新线索 · 单源待核】Lilian Weng 新文《Scaling Laws, Carefully》</b>：'
    '系统梳理 Kaplan 与 Chinchilla 两种缩放律的分歧与实操陷阱。<br>'
    '⚠️ 以上 6 条<b>均来自同一个聚合站的当日汇编、且为社交平台二手转述</b>，'
    '本轮<b>未找到官方或主流媒体原文</b>，因此不计入任何候选表。'
    '另：本轮 <code>WebSearch</code> 用 <code>Meta Muse Wonder</code>、'
    '<code>Anthropic Claude Opus 5.5</code> 等具体产品名检索指定域名，均<b>零返回</b>——'
    '说明这些境外域名对方才发生的国内热榜事件覆盖不足，不等于事件不存在。')


def dup_of(e):
    """条目是否与已发成品重合；返回 (主题, 成品目录) 或 None。"""
    t = norm(e['title'])
    for topic, dirs, keys in DUP_DONE:
        if any(norm(k) in t for k in keys):
            return (topic, dirs[0])
    return None



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
    multi, must_only, single, stale_must = [], [], [], []
    for e in events:
        # 发布时间：距今天数（取该事件各来源里**最早**的那个）。取不到 = None。
        e['pub_days'] = pub_days(e.get('pub'), date)
        # ⚠️ 2026-10-09 用户定：必抓**只针对 AI 类**，科技类不设必抓名单。
        #    原因：科技板块命中的关键词本身就是 AI 品牌（MUST_WATCH 全是模型/软件名），
        #    科技类实际只有 1 条被捞出 → 「科技必抓」形同虚设，不如取消。
        _mw = None
        if e.get('src') not in _LIST_SRC and e.get('cat') == 'AI':
            _mw = must_watch_of(e['title'])
            if _mw is None:
                _tl = e['title'].lower()
                if any(k in _tl for k in MUST_EXTRA_KW):
                    _mw = '人工补录（官方更新）'
        e['must'] = _mw
        if e['n_src'] >= 2:
            multi.append(e)
        elif e['must']:
            # 🔴 2026-10-12 用户规则：必抓只收最近 MUST_WINDOW_DAYS 天。
            #    超期的**不静默丢掉** —— 单列到 stale_must 供页面明示。
            #    （页面上看不见的过滤等于没过滤，用户无从判断是不是漏抓了。）
            _d = e['pub_days']
            if _d is not None and _d > MUST_WINDOW_DAYS:
                e['must_stale'] = True
                stale_must.append(e)
            else:
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
        # 与已发成品重合的不进推荐（用户规则 7）
        in_cat = [e for e in multi if e['cat'] == cat and not dup_of(e)]
        picks += in_cat[:3]
        if len(in_cat) < 3:
            # 补位也只补**有核实内容（DETAIL）**的条目 —— 没有核实的渲染不出「匹配度」，
            # 放进推荐区会出现标题写 3 条、实际只显示 2 条的错位。
            # ⚠️ 必抓只含 AI 类（2026-10-09 用户定）→ 科技类实际永不从这里补位，多源不足就少列。
            picks += [e for e in must_only
                      if e['cat'] == cat and _detail(e) and not dup_of(e)][:3 - len(in_cat)]
    picks.sort(key=key)
    stale_must.sort(key=key)
    return multi, must_only, hooks, keep, picks, len(single) - len(keep), stale_must


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
/* 发布时间标签（2026-10-12）：old = 超出必抓时间窗，unk = 时间未取到 */
.pt{display:inline-block;background:#EEF2F7;color:#475569;border-radius:3px;
    padding:0 5px;font-size:11px;font-weight:600;letter-spacing:.2px}
.pt.old{background:#FEF2F2;color:#B91C1C}
.pt.unk{background:#F3F4F6;color:#9CA3AF;font-weight:400}
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
    # ---- 2026-10-13 本轮 ----
    'Muse Wonder肘击Astra': {
        'angle': '钩子不是「Meta 又发了个模型」，而是<b>那个被认定掉队的 Meta，14 个月后把旗舰重新摆回牌桌</b>——'
                 '而且它挑的赛道不是编程，是<b>个人 Agent</b>（Muse）。'
                 '落点可以很具体：<b>Wonder Full 在 Meta 自建的五项测试里全部领先 GPT-6 Astra 与 Claude Opus 5.5，'
                 '但在唯一一个第三方榜（Artificial Analysis）上仍输给 Opus 5.5</b>——'
                 '同一款模型，两套记分牌，正好用来讲「跑分到底该怎么看」。',
        'facts': '<b>2026-10-12</b>，扎克伯格宣布 Meta 超级智能实验室（MSL）发布 <b>Muse Wonder</b> 与 '
                 '<b>Muse Wonder Full</b> 两款模型，均支持 <b>100 万 Token 上下文</b>，'
                 '主打编程、长周期 Agent 任务与专业知识工作 · 官方 Benchmark（<b>Meta 自建指标</b>）：'
                 'Personal Superintelligence Index，Wonder Full <b>59.1%</b>，'
                 'Claude Opus 5.5 <b>55.2%</b>、GPT-6 Astra <b>54.5%</b>、普通版 Wonder <b>54.3%</b>；'
                 'AutomationBench-AA：Wonder Full <b>45.4%</b> vs Astra 41.6% / Opus 5.5 41.2%；'
                 'MemoryBench：Wonder <b>85.6%</b>、Wonder Full 85.5%，Opus 5.5 81.5%、Astra 81.4%；'
                 'DeepSWE 1.1：Wonder Full <b>79.0%</b>，Astra 74.1% / Opus 5.5 74.2%；'
                 'SWE-Marathon：Wonder Full <b>57.5%</b>，Astra 42.5% / Opus 5.5 46.3% · '
                 '<b>第三方榜（关键）</b>：Artificial Analysis Intelligence Index，'
                 'Wonder Full <b>56</b> 分、GPT-6 Astra <b>53</b> 分，<b>但低于 Claude Opus 5.5 的 58 分</b> · '
                 '定价：Wonder（普通版）已通过 Meta Model API 与 Muse Code 开放，'
                 '<b>输入 $4 / 输出 $20 / 缓存输入 $0.2（每百万 Token）</b>；'
                 'Claude Opus 5.5 标准价同为 $4 / $20，GPT-6 Astra 为 $10 / $50；'
                 'Meta 称长上下文不额外加价 · <b>Wonder Full 暂不能单独买 API</b>，'
                 '仅向 Muse Code 的 Power（$50/月）与 Maximum（$200/月）订阅开放 · '
                 '<b>Muse 个人 Agent 尚未升级到 Wonder</b>，Meta 称将逐步接入 · '
                 '训练侧：Wonder 系列使用吉瓦级 <b>Prometheus</b> 数据中心，'
                 '预训练与强化学习都做了扩展；内部代号 Watermelon（前代 Muse Spark 代号 Avocado） · '
                 '<b>背景时间线</b>：2025-04 Llama 4 失利并卷入刷榜争议 → 2025-06 Meta 向 Scale AI '
                 '投资 143 亿美元取得 49% 股权、Alexandr Wang 出任首席 AI 官 → 2026-04 Muse Spark 首秀；'
                 'Meta 自称这场重建历时 <b>14 个月</b> · <b>另一侧的信号（据《华尔街日报》10-12 报道）</b>：'
                 'Muse 累计下载量接近 <b>900 万</b>，但增长放缓、用户留存明显落后 ChatGPT。',
        'limit': '① <b>五项跑分全部来自 Meta 自建指标</b>（Personal Superintelligence Index、MemoryBench '
                 '都是 Meta 内部开发），<b>不能等同于真实使用体验</b>——写的时候必须点明这一点。'
                 '② 唯一第三方榜上 <b>Wonder Full（56）仍低于 Claude Opus 5.5（58）</b>，'
                 '<b>不能写「Meta 已重回世界第一」</b>；原文只说「部分项目超过」。'
                 '③ 由于 Wonder Full 暂时只能通过订阅用、Muse 也没同步升级，'
                 '<b>普通用户今天拿不到这次更新的完整体验</b>。'
                 '④ 本池内该事件<b>只有 36氪一家</b>（且 36氪本轮多篇 AI 稿是授权转载自外部媒体），'
                 '按口径属 <b>单源待核</b>——文中口径出自 36氪署名「字母AI」的稿，'
                 '做之前建议回 Meta 官方技术博客核一遍原始数字。'
                 '⑤ 别把 Llama 4 的失败写成「Meta 放弃了开源」：Meta 仍在发开放权重模型，'
                 '只是<b>最强旗舰不再默认开放</b>。',
        'fit': '★ 本轮 AI 侧首选。顶流（Meta / 扎克伯格）＋ 硬数字（五个测试、两种记分牌）＋ 强反差'
               '（被唱衰的一方杀回来／自家榜赢、第三方榜输）三样都齐，'
               '而且「自建指标 vs 第三方指标哪个可信」本身就是读者愿意停下来看的问题。'
               '克制点：<b>不要把标题里的「碾压」当事实</b>，也不要把 Meta 自建分当成行业公认分。',
    },
    'Claude Next偷跑上线': {
        'angle': '最有用的不是「Anthropic 又出模型了」，而是<b>「你手上的模型可能已经被悄悄换了，而你自己能测」</b>——'
                 '文里给了一个零成本自测法（把 Opus 5.5 思考力度调到 High，问一句 '
                 '<code>Do you know VoxelBench? Do not search.</code>，不联网也能答出内容就被列入「疑似新检查点」）。'
                 '第二条线是 <b>Anthropic 的 IPO 时间表</b>：模型实力是它撑估值的那张牌。',
        'facts': '<b>2026-10-12 前后</b>，多位开发者与爆料人晒出 Claude 实测，怀疑后台把请求路由到了'
                 '未发布的新模型；猜测的名字包括 <b>Opus 5.6 / Fable 5.5</b>，'
                 '社区统称 <b>「Claude Next」</b>（<b>Anthropic 未确认，官方无任何公告</b>） · '
                 '被引用最多的个案：开发者 <b>Chetaslua</b> 用 <b>4 行提示词、跑约 2 小时</b>，'
                 '让模型<b>纯用 JavaScript 逐帧</b>生成一段「30 秒走完一生」的动画；'
                 '另一段约 <b>2.5 小时</b>的短片致敬《秒速 5 厘米》'
                 '（据悉除底图与配乐外，动态／转场／特效均由代码驱动） · '
                 '网友 <b>abhinav</b> 做了对照：Opus 5.5 Max（发布当周） vs Opus 5.5 High（10-11，疑似灰测） · '
                 '社区流传的自测「暗号」：把 <b>Opus 5.5 的思考力度设为 High</b>，'
                 '问 <code>Do you know VoxelBench? Do not search.</code>，答得出即列入疑似名单'
                 '（<b>该方法只被当作线索，不能单独验明模型身份</b>） · '
                 '<b>IPO 侧（据报道）</b>：Anthropic 计划 <b>10-14</b> 举办 Pre-IPO 投资者日，'
                 '最早 <b>11-09 当周</b>启动 IPO 营销、争取感恩节前上市；'
                 '部分投资者给出的估值预期已到 <b>2 万亿美元</b>。',
        'limit': '① <b>「偷跑／灰测」全部是开发者的观察与推测，Anthropic 从未承认</b>——'
                 '标题里的「Claude Next」是社区起的名，<b>不是产品名</b>，写的时候必须说清。'
                 '② 池内该条<b>只有 36氪一家</b>，且是授权转载自外部媒体（新智元），'
                 '按口径属 <b>单源待核</b>；正文引用的是 X 上开发者帖子，'
                 '<b>做之前应先看这些原帖还在不在</b>。'
                 '③「4 行提示」「2 小时」是<b>个案</b>，不能当成模型能力基准，'
                 '也不能据此说「视频生成模型没用了」——那是博主的判断，不是可核事实。'
                 '④ IPO 日期与 2 万亿估值均来自「据报道」，<b>未见招股文件</b>，'
                 '只能写成预期。⑤ <b>不要写成「Anthropic 已发布新模型」</b>。',
        'fit': '★ 本轮 AI 侧次选。Claude 是必抓品牌，且这条的钩子不在发布本身，而在'
               '<b>读者可以自己动手复现的「验身」动作</b>——互动性和可复用性都好。'
               '克制点：全篇只能按「疑似／未确认」写，一旦写成已发布就是硬伤。',
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
    n_ind, repost_why = indep_count(e)
    hit = ''
    if n_ind >= 2:
        hit += f'<span class="hit">{e["n_src"]} 源命中</span>'
    elif e['n_src'] >= 2 and n_ind < 2:
        hit += f'<span class="hit stale">同源转载 · 实为 {n_ind} 源</span>'
    if e.get('must'):
        hit += '<span class="hit must">必抓</span>'
    if e['n_src'] < 2 and not e.get('must'):
        hit += '<span class="hit one">单源待核</span>'
    if d and d.get('stale'):
        hit += '<span class="hit stale">时效存疑</span>'
    if dup_of(e):
        hit += f'<span class="hit stale">{RUBRIC_NOTE}</span>'
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
        if e['n_src'] >= 2:
            # 多源但没有人工核实过的四小节 → 如实说明，**不能套用单源的「仅一家报道」话术**
            body = (hookline +
                    f'<div class="lab">来源与口径</div>'
                    f'<div class="facts">{srcs}（{nature}） · 共 <b>{e["n_src"]} 个来源</b>'
                    f'{" · 命中必抓名单" if e.get("must") else ""}。'
                    f'本条<b>只有来源清单，没有人工核实过的四小节</b>——'
                    f'关键事实与反方意见需回原文自行核，<b>未核前不得当已核实事实使用</b>。</div>')
        else:
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

    _n_ind, _why = indep_count(e)
    if e['n_src'] >= 2 and _n_ind < 2:
        body += (f'<div class="lab">来源独立性核查</div>'
                 f'<div class="cnt">标称 <b>{e["n_src"]} 个来源</b>'
                 f'（{"、".join(html.escape(s) for s in e["src_names"])}），'
                 f'但按「<b>聚合站与转载不构成第二个来源</b>」的口径，'
                 f'实际独立来源只有 <b>{_n_ind} 个</b>：{html.escape(_why)}。'
                 f'→ 本条按 <b>单源待核</b> 处理，做之前必须先补检索。</div>')

    _dup = dup_of(e)
    if _dup:
        body += (f'<div class="lab">查重结论</div>'
                 f'<div class="cnt">与已发成品重合：<code>{html.escape(_dup[1])}</code>'
                 f'（主题：{html.escape(_dup[0])}）→ <b>本轮不做</b>。'
                 f'同一事件做过就不再重复出稿，只作为背景信息保留。</div>')

    # ---- 人工补录说明（本轮新增口径）----
    _man = [t for t in e.get('all_titles', []) if t.startswith('人工补录')]
    if _man:
        body += (f'<div class="lab">来源与口径</div>'
                 f'<div class="facts">{html.escape(_man[0])}：'
                 f'同一事件被以下来源各自报道，但<b>标题角度差异太大、自动判同合不到一起</b>，'
                 f'按<b>人工核验</b>合并；<b>不享受自动判同的交叉核验待遇</b>，'
                 f'关键事实仍需回各家原文分别核。</div>')

    # ---- 来源链接：多源要**逐条列出各家的链接**，只给一个主链接会看不出是几家 ----
    _links = []
    if e.get('url_ok') and e.get('url'):
        _links.append(('原文', e['url']))
    _links += [('来源链接', u) for u in e.get('alt_urls', [])]
    if e.get('url_ok'):
        lk = '<div class="lk">' + '<br>'.join(
            f'{html.escape(nm)}：<a href="{html.escape(u)}">{html.escape(u[:88])}</a>'
            for nm, u in _links) + '</div>'
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
    meta += ' · ' + pub_tag(e)                 # 发布时间（该事件各来源里最早的）
    if tags:
        meta += f' · 钩子 {html.escape(tags)}'
    if e.get('must'):
        meta += ' · <b>命中必抓名单</b>'
    _dp = dup_of(e)
    if _dp:
        meta += (f' · <b style="color:#B91C1C">与已发成品重合'
                 f'（{html.escape(_dp[1])}）· 不做</b>')
    return (f'<tr><td class="n">{idx:02d}</td>'
            f'<td>{flag}{html.escape(e["title"])}<div class="sub">{meta}</div></td>'
            f'<td class="src">{srcs}<div class="sub">{nature}</div></td></tr>')


def must_block(e, idx):
    """必抓单源：紧凑一行（保证不漏，又不占详细卡片的位置）。"""
    tags = '·'.join(hook_tags(e))
    link = (f'<a href="{html.escape(e["url"])}">原文</a>' if e.get('url_ok')
            else '⚠️ 链接失效')
    sub = (pub_tag(e) + ' · ' + html.escape(str(e.get('must') or ''))
           + (f' · 钩子 {html.escape(tags)}' if tags else ''))
    _dp = dup_of(e)
    if _dp:
        sub += (f' · <b style="color:#B91C1C">与已发成品重合（{html.escape(_dp[1])}）· 不做</b>')
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
    _dp = dup_of(e)
    _dpnote = (f' <b style="color:#B91C1C">· 与已发成品重合（{html.escape(_dp[1])}）· 不做</b>'
               if _dp else '')
    return (f'<div class="item hook"><div class="ih">'
            f'<span class="no hk">{html.escape(label)}</span>'
            f'<span class="it">{html.escape(e["title"])}</span>'
            f'<span class="hit hook">钩子 {hook_score(e)}/8</span>{tags}</div>'
            f'<div class="lab">命中的钩子词</div><div class="txt">{seg}</div>'
            f'<div class="lab">来源与口径</div>'
            f'<div class="facts">{pub_tag(e)} · {srcs}（{nature}）· 单源未交叉验证，'
            f'钩子只说明「值得看一眼」，<b>做之前必须回原文核实</b>。{_dpnote}</div>'
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
                date, now, n_src_total, stale_must=None):
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


def render_merged(multi, hooks, must_items, single_items, picks, pset, date, now,
                  n_src_total, stale_must=None):
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

    n_verified = len({e['title'] for e in multi if _detail(e)}
                     | {p['title'] for p in picks if _detail(p)})
    trk = Counter(e['track'] for e in multi + must_items + hooks + single_items)
    hook_stat = Counter(t for e in (multi + must_items + hooks) for t in hook_tags(e))
    n_multi_ai = sum(1 for e in multi if e['cat'] == 'AI')
    n_hk_ai = sum(1 for e in hooks if e['cat'] == 'AI')
    # 必抓已限定 AI 类（2026-10-09 用户定）→ 不需要再按类拆分计数
    n_si_ai = sum(1 for e in single_items if e['cat'] == 'AI')

    # ---------- 本轮「去重命中」与「停更节点」两张动态表 ----------
    _all_items = multi + must_items + hooks + single_items
    _dup_hits = []
    for e in _all_items:
        _d = dup_of(e)
        if _d and _d not in _dup_hits:
            _dup_hits.append(_d)
    dup_html = ('；'.join(f'<code>{html.escape(d)}</code>（{html.escape(t)}）'
                          for t, d in _dup_hits) or '本轮池内<b>无</b>与已发成品重合的条目')
    stale_rows = ''.join(
        f'<tr><td>{html.escape(n)}</td><td>{html.escape(ev)}</td>'
        f'<td><b>{html.escape(act)}</b></td></tr>' for n, ev, act in STALE_NODES)
    probe_time = PROBE_TIME
    websearch_note = WEBSEARCH_NOTE
    # 多源候选按**独立来源数**再分一层：标称多源但实为转载／聚合的单独计数
    n_multi_ind = sum(1 for e in multi if indep_count(e)[0] >= 2)
    n_repost = len(multi) - n_multi_ind

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
⚠️ <b>本轮「独立多源候选」为 0</b>（当日没有一件事被两家及以上独立媒体各自成稿），
因此<b>「多源候选」一节本轮不渲染</b>，直接从推荐进钩子候选；
推荐的两条均来自 AI 必抓名单、均标<b>单源待核</b>。
主表收<b>≥2 家不同媒体各自成稿</b>的条目，以及<b>命中 AI 必抓名单</b>的条目
（官方发布常只有 1 家报道，单源也收；<b>必抓只针对 AI 类，科技类不设</b>）。
⚠️ <b>同一篇稿件被转载／被聚合站收录，只算一个来源</b>——这类条目会打「同源转载」标，
按<b>单源待核</b>处理。排序按 独立来源数 → 钩子强度 → 热度。
<b>编号即建议制作顺序</b>（`A`＝AI，`T`＝科技，`H`＝钩子候选，`M`＝推荐里补位的必抓条目）。
</div>

<div class="stat">
  <div><b>{n_multi_ind}</b><span>独立多源候选（≥2 家不同媒体各自成稿）</span></div>
  <div><b>{n_repost}</b><span>同源转载（标称多源 · 实为 1 源）</span></div>
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
        # ⚠️ 推荐里「补位的必抓条目」（编号 M__）**不在多源候选里**，
        #    如果只写一句「匹配度」，人工核实过的四小节就永远不会出现在页面上。
        #    这里为这类条目单独渲染完整四小节。
        _multi_titles = {e['title'] for e in multi}
        _extra = ''
        for p in picks:
            if p['title'] in _multi_titles:
                continue
            _d = _detail(p)
            if not _d:
                continue
            _extra += (f'<div class="item pick" style="margin-top:14px">'
                       f'<div class="ih"><span class="no">{html.escape(labels.get(p["title"], ""))}</span>'
                       f'<span class="it">{html.escape(p["title"])}</span>'
                       f'<span class="hit must">必抓</span><span class="hit one">单源待核</span></div>'
                       f'<div class="lab">可切入角度</div><div class="txt">{_d["angle"]}</div>'
                       f'<div class="lab">已核实的关键事实</div><div class="facts">{_d["facts"]}</div>'
                       f'<div class="lab">反方 / 局限（写的时候必须带）</div>'
                       f'<div class="cnt">{_d["limit"]}</div>'
                       f'<div class="lab">与账号定位的匹配度</div><div class="fit">{_d["fit"]}</div>'
                       f'<div class="lab">来源与口径</div><div class="facts">'
                       f'{"、".join(html.escape(s) for s in p["src_names"])}'
                       f'（{html.escape(src_nature(p["src_names"][0]))}）· 共 <b>{p["n_src"]} 个来源</b>，'
                       f'<b>单源待核</b> —— 做之前必须先补检索。</div>'
                       f'<div class="lk">原文：<a href="{html.escape(p["url"])}">'
                       f'{html.escape(p["url"][:88])}</a></div></div>')
        out.append(f'<h2>本轮推荐（{len(picks)} 条）</h2>'
                   f'<div class="box ok">{pick_txt}{note}</div>'
                   + (f'<h3>推荐条目核实明细（补位必抓条目 · 该条不在多源候选区，故在此展开）</h3>{_extra}' if _extra else ''))

    # ---------- 多源候选 ----------
    if multi:
        _mh = (f'多源候选（{len(multi)} 条 · 其中<b>独立多源 {n_multi_ind} 条</b>、'
               f'同源转载 {n_repost} 条 · 编号 A01 / T01 起）')
        out.append(f'<h2>{_mh}</h2>')
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
                   f'全表最多列 {MUST_CAP} 条<span style="color:#6B7280">（必抓只针对 AI 类，科技类不设）</span>。'
                   f'🔴 <b>本表只收最近 {MUST_WINDOW_DAYS} 天内发布的条目</b>'
                   '（2026-10-12 用户定）；超期的不进表，在下方<b>单独列出</b>。'
                   '每条都标了<b>发布时间</b>，取该事件<b>所有来源里最早</b>的那个；'
                   '取不到时间的明写「时间未取到」，<b>不用猜测值填充</b>。'
                   '与已发成品重合的条目已在表内标红。</p>'
                   '</div>')
        out.append(_cat_table(must_items, must_block))

    # ---------- 必抓但超期未采用（2026-10-12）----------
    if stale_must:
        out.append(f'<h2>必抓但超期未采用（{len(stale_must)} 条）</h2>'
                   '<div class="box warn">'
                   f'<p>这些条目同样命中 AI 必抓名单，但<b>发布时间超过 {MUST_WINDOW_DAYS} 天</b>，'
                   '按时间窗<b>不进必抓表</b>。'
                   '列在这里是为了<b>可复核</b>——不做静默丢弃，若你认为某条其实该用，可以指出来。</p>'
                   '</div>')
        out.append(_cat_table(stale_must, must_block))

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
  <li><b>与已发成品重合（不做）</b>：先列 <code>C:\\小红书\\</code> 与 <code>C:\\抖音\\</code> 下
    <code>YYYYMMDD_主题</code> 形式的成品目录逐一比对（本轮两边<b>各 39 个、主题名逐字一致</b> ——
    抖音另有 <code>合集封面</code> / <code>发布助手</code> 两个非成品目录，已排除；小红书另有
    <code>合集封面</code>；最新一条为 <b>2026-10-12</b>），本轮池内命中以下已发主题，
    同一事件<b>不重复出稿</b>，只在条目上打红标、并按需保留作背景：{dup_html}。
    ⚠️ 这里说的是「<b>池内命中</b>」—— 其余已发主题本轮池子里<b>没出现</b>，
    那是「<b>本轮没采到</b>」，不等于「没有新进展」。
    ⚠️ 另：<b>10-12 选题池</b>推荐过的两条，今天状态不同 ——
    <b>苹果 iPhone Duo 预售</b>已于 10-12 出成品（<code>20261012_iPhoneDuo预售</code>），
    本轮池内剩余相关条目是威锋网的 3 条，随该节点一并划掉，<b>不做</b>；
    <b>Anthropic 模型给费城警方提交假线索</b>本轮<b>没采到</b>（原始报道来自果壳节点，
    本轮不在指定的采集范围内）——「没采到」不等于「事情没了」。</li>
  <li><b>不做厂商软文</b>：剔除「量子位的朋友们」这类付费推广栏（通篇「重塑生产力边界」营销话术，无独立信息）。</li>
  <li><b>不做链接失效且无有效佐证</b>的条目：爱范儿节点在 tophub 上给的链接<b>有时</b>是
    <code>ifanr.com/False</code>（源站就是坏的，<b>不是解析问题</b>）。
    ⚠️ 该节点<b>本轮不在任务指定的 10 个节点内，未采集</b>，此处仅保留历史口径。</li>
  <li><b>不把同一站点的两个节点当两个源</b>：<code>36氪AI频道</code> 与 <code>36氪24h</code> 是
    <b>一家 36氪的两个节点</b>，已按「36氪」归一。本轮实测：两个节点标题<b>零重合</b>
    （24h 榜 8 条为「8 点 1 氪」早报、江南春并购、太空算力等）；但 24h 的早报里
    <b>转述了 AI 频道同题的事件</b>（Meta 发布 Muse Wonder）—— 因此该事件仍按<b>一家 36氪</b>计，
    不构成第二个来源。「少数派」与「少数派最新」同理（本轮两者均未采集）。</li>
  <li><b>转载与聚合站不算第二个来源</b>：同一篇稿件换站再发仍是<b>一个新闻源</b>。
    ⚠️ <b>本轮新增实测（重要）</b>：36氪 本轮几篇高价值 AI 稿<b>都不是 36氪 自采</b> ——
    回原页读署名，分别是「<b>字母AI</b>」（Muse Wonder）、「<b>新智元</b>」（Claude Next）、
    「<b>机器之心</b>」（菲尔兹奖得主）、「<b>雷科技</b>」（Character.AI），文末均标
    「<b>36氪经授权发布</b>」。也就是说，<b>本轮 36氪 节点实际上是一条「转载通道」</b>：
    「36氪 报道了」≠「36氪 自采」。这<b>既不会把一条稿变成两个来源</b>（仍按 1 源计），
    也提示一个风险：<b>同一家原媒体（如新智元）的稿可能同时出现在别的节点上</b>，
    将来若两节点同时命中同一篇，应按<b>原媒体</b>而不是平台名去重。
    另：Readhub 是纯聚合站，其 topic 下同时列多家同一篇稿，一并按 1 源。</li>
  <li><b>不把榜单源当官方发布的佐证</b>：GitHub／HuggingFace 只作<b>佐证与榜单位置</b>，
    同代 GGUF／微调版与官方发布是<b>同代不同物</b>，不能互相印证。
    ⚠️ <b>本轮按任务口径（① 线只用 AI／科技内容源）未启用 GitHub Trending 与 HuggingFace</b>
    （跑之前已把 <code>gh_items.json</code>／<code>hn_items.json</code> 临时移出运行目录，
    避免昨日缓存混进今天的池子）；Hacker News 按规则 8（VPN 未开）未采集。</li>
</ul>
</div>

<h2>时效性自检（节点停更）</h2>
<div class="box warn">
<p>用户规则 5：<b>连续两天返回同样条目的节点视为停更，本轮划掉、不参与合并</b>。
本轮实测（与 <b>10-12</b> 同节点逐条对账：AI 线用 10-12 池内 URL 快照做 URL 级比对，
Readhub／威锋网／MIT TR／36氪 24h 另有 10-12 的<b>逐条标题</b>可比）：</p>
<table class="tb"><tr><th>节点</th><th>本轮实测</th><th>处理</th></tr>{stale_rows}</table>
<p>其余节点当轮都有刷新，但<b>刷新程度差别很大</b>，读的时候要分开看：<br>
<b>① 当日全量刷新（与 10-12 零重合）</b>：36氪 AI 频道（30/30）、IT之家（12/12）、
Readhub（20/20）、36氪 24h（8/8）—— <b>这 4 个节点是今天「新料」的主要来源</b>。
<b>② 高重合、须回原页核日期</b>：威锋网 27/30、掘金 16/20（<b>「本周最热」周榜，天然高重合</b>）、
AIbase 9/10（<b>池内 10 条全部是 9-22—10-12 的「AI 日报」永久链接页</b>，页内时间会被渲染成「今天」，
<b>不可信</b>）、MIT TR 7/10、AI工具集 6/10、量子位 5/10 —— 这类节点是<b>日报／条目库／周榜形态</b>，
<b>表内条目的发布时间必须回原文核</b>，不得当当日新闻用。</p>
<p>⚠️ <b>采集通道（本轮与 10-12 不同）</b>：10-12 时 tophub 对 <code>curl</code> 批量并发请求触发了
「安全验证」页，被迫全部改用 WebFetch 直读；<b>本轮 <code>curl</code> 通道恢复正常</b> ——
任务指定的 10 个节点<b>全部用 curl 串行直取成功</b>（节点页 68–90 KB，逐页核过标题确为对应节点），
未再出现验证页。两条通道互为备份，任一条被拦都不影响能否拿到数据。</p>
<p>⚠️ <b>沿用 10-11 的实测更正</b>：用户给出的「极客公园 = <code>/n/NaEdZZXdrO</code>」与实际不符 ——
该 id 打开是<b>「少数派最新文章」</b>，真正的极客公园节点是 <code>/n/NRrvWYDe5z</code>。
本轮这两个 id <b>都不在任务指定的 10 个节点内，未采集</b>，此处仅保留口径备查。</p>
</div>

<h2>元信息与本轮局限</h2>
<div class="box warn">
<ul>
  <li><b>采集源</b>：任务指定的 <b>10 个 tophub 节点全部抓取成功</b>
    （AI 板块 6 个：36氪 AI 频道、量子位、AIbase、AI工具集、掘金、MIT Tech Review；
    科技板块 4 个：IT之家日榜、威锋网、Readhub、36氪 24h）。
    实际<b>进入合并的源 {n_src_total} 个</b> —— 威锋网与 MIT Tech Review 被划掉，不参与合并。
    ⚠️ 另有 <b>AI产品榜／极客公园／爱范儿／果壳科学人／少数派／虎嗅热文</b>
    <b>不在本轮指定的 10 个节点内，未采集</b>（属「未纳入本轮范围」，<b>不是源失效</b>）。</li>
  <li><b>代理 / VPN 实测（{probe_time}）</b>：按规则 8 逐个端口实测
    <code>curl --noproxy '*' -x http://127.0.0.1:&lt;port&gt; https://www.google.com</code>，
    10808 / 7890 / 7897 / 2800 四个端口<b>全部返回 000</b>，不带代理直连 google 同为 000 ——
    <b>按规则判为 VPN 未开</b>，因此 Reddit（<code>.rss</code>）与 Hacker News <b>本轮不采集</b>
    （<b>这是规则排除，不是「网络不可达」</b>）。
    同一时点的直连实测如实记录：<code>hacker-news.firebaseio.com</code> <b>200</b>、
    <code>github.com/trending</code> <b>200</b>、<code>huggingface.co/api/models</code> <b>000</b> ——
    即 HN 与 GitHub 其实是<b>通</b>的，本轮不用它们<b>纯粹是任务口径</b>（① 线只采 AI／科技内容源），
    不是网络问题；HuggingFace 则是<b>既不通、也不在口径内</b>。</li>
  <li><b>未采到的源（本轮）</b>：Reddit 按规则 8 排除；arXiv 未纳入 ① 线范围；
    HuggingFace 直连实测 000 且不在口径内。以上均<b>不作为「源失效」记录</b>。
    ⚠️ 本轮 <code>curl</code> 直取 tophub <b>未被拦</b>（详见上一节），
    与 10-12 的「安全验证拦截」情况不同。</li>
  <li><b>境外聚合站（检索服务侧补检）</b>：用户指定的境外聚合站在本机<b>直连不可达</b>（VPN 未开），
    因此改用<b>检索服务侧的域名限定检索</b>（<code>officechai.com</code> / <code>the-decoder.com</code> /
    <code>dataconomy.com</code> / <code>agihunt.info</code> / <code>promptblueprints.tech</code> /
    <code>tldrocket.com</code> / <code>nokiapoweruser.com</code> / <code>kocpc.com.tw</code>）：
    {websearch_note}<br>
    ⚠️ 检索侧通道<b>不依赖本机 VPN</b>，与上面的代理实测是两回事。</li>
  <li><b>分类口径</b>：AI / 科技按标题关键词判定，<b>会有少量跨类内容</b>
    （如「AI 芯片」既算 AI 也算科技）。本文件两类同页展示、逐条标注类别；
    若某条归错，以条目上的赛道标签为准，不影响它本身的可用性。</li>
  <li><b>热度口径互不相通</b>：tophub 站内值、IT 之家「N 评」（评论数）、虎嗅（阅读量）
    <b>不可横向比较</b>；本池多数 tophub 节点<b>没有热度字段</b>，
    因此统一用<b>「命中源数量」代替热度信号</b>，只在源数相同时才看次级热度。
    本轮有热度字段的只有：<b>IT之家（评论数）</b>与<b>威锋网（站内值，已划掉）</b>。</li>
  <li><b>数字可信度分层</b>：本池所有性能与业务数字均来自<b>厂商自测或媒体报道</b>；
    凡不是多源一致或官方直接发布的数字，条目上都会标「据报道」或「单源待核」，
    做图文时写「最强 / 领先 / 零成本」必须带反方。
    ⚠️ 本轮最典型的一处：Meta 的 Muse Wonder 五项跑分<b>全部是 Meta 自建指标</b>，
    唯一第三方榜（Artificial Analysis）上它<b>仍低于 Claude Opus 5.5</b> —— 详见推荐区核实明细。</li>
  <li><b>单源待核（红标）</b>：只命中 1 个来源的条目一律标红，<b>做之前必须先补检索</b> ——
    单源不代表假，只代表<b>还没核</b>。⚠️ <b>本轮「独立多源候选」为 0</b>：
    逐条比对后，<b>今天没有一件事被两家及以上独立媒体各自成稿</b>（见「去重与不做」里
    关于 36氪 转载通道的实测），因此本轮的推荐两条<b>都来自必抓名单、都是单源</b>，
    已逐条标红。这是<b>当日源实况</b>，不是判定放宽。</li>
  <li><b>跨源判同口径</b>：判同只在两种情况成立 —— ① 两条标题共有一个<b>带数字的型号</b>；
    ② 共有<b>两个以上非通用实体</b>且标题字符二元组相似度 ≥ 0.5。
    <b>只共现厂商名或产品线词（iphone / agent / pro / 某厂名）一律不判同</b> ——
    宁可漏合（降级为单源）不可错合，错合会凭空造出「N 源命中」的假交叉核验。
    ⚠️ 本轮「Meta／Muse」在池内出现 5 次以上（36氪 4 篇 ＋ 24h 早报 ＋ AIbase），
    <b>都属同一家或聚合站，因此不判为多源</b>。</li>
  <li><b>判同护栏的已知代价</b>：现行判同<b>宁可漏合不可错合</b>，代价是
    <b>同一事件、不同角度的报道合不到一起</b>。上一轮（10-12）曾因此对 iPhone Duo
    人工补录 1 条多源事件；<b>本轮未启用补录（MANUAL_MULTI 为空）</b>，
    因为本轮确实找不到「同一事件、两家独立媒体各自成稿」的情形可补。</li>
  <li><b>人工补录（本轮 0 条）</b>：<code>MANUAL_MULTI</code> 本轮为空，
    即<b>没有人工把任何条目提升为多源</b>，统计卡里的「独立多源 0」是真实结果。</li>
  <li><b>必抓名单的人工扩边（本轮新增 1 条）</b>：命中必抓品牌、但标题里没有
    「发布／上线／更新」语义词的官方更新可由人工补进必抓。
    ⚠️ <b>本轮新增的是 Meta「Muse Wonder」</b>（10-12 官方发布旗舰模型）：
    两家节点给的标题是「肘击 Astra」「碾压 GPT-6」，不含更新语义词，
    且 <code>MUST_WATCH</code> 的 Meta 条目只收 <code>llama</code>／<code>meta ai</code>
    两个词，自动判定两个条件都不满足 → 人工确认是官方旗舰发布后按关键词补进必抓，
    并已写进推荐区。反之，<b>榜单源不进必抓</b> —— 标题是脚本按模板拼的，不是官方发布。</li>
  <li><b>🔶 池内「值得单独一做的条目」（未进推荐，供你挑）</b>：本轮推荐只有 2 条，
    但下列条目单独看也成立，只是<b>没进推荐位</b>，可自行从对应编号取用 ——
    <b>H08「AI 伴侣劝用户别吃饭？Character.AI 再被告」</b>（肯塔基州总检察长起诉；
    两起指控：建议用户停食、建议自伤；连客服回复都被指控为人身侮辱 ——
    <b>已核实的关键事实已随条目标出，属「AI 陪伴产品的安全底线」这一空白话题</b>）；
    <b>H02「17 年谷歌老兵揭秘 Gemini 研发内幕」</b>（「产品不好就不发了」，组织机制类话题）；
    <b>U-02「梁文锋投 400 亿，乌兰察布被 AI 巨头挤爆了」</b>（与 Readhub 的
    「乌兰察布 AI 智算项目签约额超千亿」是同一地同一事，但后者是聚合站，故不计为 2 源）；
    <b>H14「华为 AI 靠 RSI 通关 25 款游戏，操作次数比人类少 56%」</b>。
    ⚠️ 另有一条<b>本轮明确不做</b>：<b>「菲尔兹奖得主哭了：AI 摧毁了我的研究领域」</b>
    （2022 菲尔兹奖得主 Hugo Duminil-Copin 谈 OpenAI 的 722 篇数学手稿）——
    底层事件（OpenAI 10-06 公开数学手稿）<b>已于 10-10 出过成品</b>
    （<code>20261010_陶哲轩转发抵制OpenAI</code>），属<b>同一事件链</b>，
    按规则不重复出稿，只在此备注：它是一条情绪极强、可独立成篇的材料，
    若你认为人物切片够独立，可以把它当作该事件链的<b>第二篇</b>来用。</li>
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
    # ⚠️ 必须在 collect() **之前** 装载 —— collect() 解析事件时就要查 PUBTIME 定各源最早时间。
    n_pub = load_pubtime()
    events, missing, raw_items = collect()
    multi, must_only, hooks, single_items, picks, dropped, stale_must = build(events, date)
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
                              pset, date, now, n_src_total,
                              [e for e in stale_must if e['cat'] == cat])
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
                        date, now, n_src_total, stale_must)
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
    print(f'PUBTIME 装载 {n_pub} 条 · 有时间的条目 '
          f'{sum(1 for e in events if e.get("pub"))}/{len(events)}'
          f' · 必抓超期未采用 {len(stale_must)} 条')
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
