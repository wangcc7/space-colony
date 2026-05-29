"""
星际殖民地 V8.0 战争纪元 - FastAPI + aiomysql + Redis
V8: 袭击系统/防御体系/战报中心/派系战争/赏金/竞技场/间谍/跨模块联动
V7.1修复：乱码修复/时区统一/期货面板/每日任务/API路径修正/事件显示修复
"""
import asyncio, json, hashlib, random, logging, time, math, uuid, os
from datetime import datetime, timedelta, date
from contextlib import asynccontextmanager
from typing import Optional
import httpx

from fastapi import FastAPI, HTTPException, Depends, Query, Header, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

import aiomysql
import jwt
import redis.asyncio as aioredis
from passlib.hash import bcrypt

# ============ 配置 ============
DB_HOST = os.getenv("DB_HOST", "sc-db")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER", "game")
DB_PASS = os.getenv("DB_PASS", "gamepass")
DB_NAME = os.getenv("DB_NAME", "spacecolony")
REDIS_URL = os.getenv("REDIS_URL", "redis://sc-redis:6379")
JWT_SECRET = os.getenv("JWT_SECRET", "spacecolony-v6-2026")
JWT_EXPIRE = 86400 * 7

log = logging.getLogger("spacecolony")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ============ Pydantic Models ============
class RegModel(BaseModel):
    username: str; email: str; password: str; colony_name: str; planet_type: str = "terran"
class LoginModel(BaseModel):
    username: str; password: str
class BuildModel(BaseModel):
    building_type: str; slot: int
class TechModel(BaseModel):
    tech_type: str
class PhiloModel(BaseModel):
    philosophy_type: str
class TradeModel(BaseModel):
    resource_type: str; amount: int; trade_type: str
class FuturesModel(BaseModel):
    resource_type: str; direction: str; amount: int; leverage: int = 2
class StockTradeModel(BaseModel):
    code: str; direction: str; amount: int; price: Optional[float] = None
class StockFutureModel(BaseModel):
    code: str; direction: str; amount: int; leverage: int = 2
class ForumPostModel(BaseModel):
    category: str; title: str; content: str
class ReplyModel(BaseModel):
    content: str
class FactionModel(BaseModel):
    name: str; motto: str = ""; ideology: str = "balanced"
class ExpeditionModel(BaseModel):
    target_sector: str; fleet_size: int = 1
class AttackModel(BaseModel):
    target_id: int
class SpecializeModel(BaseModel):
    spec_type: str
class CraftModel(BaseModel):
    recipe_id: str; amount: int = 1
class FactionDonateModel(BaseModel):
    resource_type: str; amount: int
class ChatModel(BaseModel):
    message: str
class GodAIModifyModel(BaseModel):
    table: str; row_id: int; field: str; value: str

# ============ V8: 战争纪元 Models ============
class RaidModel(BaseModel):
    target_id: int; formation: str = "balanced"
class RevengeModel(BaseModel):
    raid_id: int; formation: str = "balanced"
class DefenseBuildModel(BaseModel):
    defense_type: str; slot: int
class DefenseFormationModel(BaseModel):
    formation: str
class DeclareWarModel(BaseModel):
    target_faction_id: int; war_type: str = "declaration"
class PeaceProposalModel(BaseModel):
    target_faction_id: int
class AllianceModel(BaseModel):
    target_faction_id: int
class BountyPlaceModel(BaseModel):
    target_id: int; amount: int; reason: str = ""
class BountyEscalateModel(BaseModel):
    additional_amount: int
class ArenaBetModel(BaseModel):
    match_id: int; predicted_winner: int; amount: int
class EspionageLaunchModel(BaseModel):
    target_id: int; op_type: str
class ShieldActivateModel(BaseModel):
    shield_type: str = "attack"

# 更多资源类型映射
RESOURCE_MAP = {
    "minerals": {"name": "矿物", "col": "minerals"},
    "energy": {"name": "能量", "col": "energy"},
    "food": {"name": "食物", "col": "food"},
    "rare_metals": {"name": "稀有金属", "col": "rare_metals"},
    "crystals": {"name": "水晶", "col": "crystals"},
    "plasma": {"name": "等离子体", "col": "plasma"},
    "dark_matter": {"name": "暗物质", "col": "dark_matter"},
    "antimatter": {"name": "反物质", "col": "antimatter"},
}

# 合成配方
CRAFT_RECIPES = {
    "rare_metals": {"name": "合成稀有金属", "inputs": {"minerals": 50, "energy": 20}, "output": 1},
    "crystals": {"name": "合成水晶", "inputs": {"minerals": 30, "energy": 30}, "output": 1},
    "plasma": {"name": "合成等离子体", "inputs": {"energy": 40, "food": 20}, "output": 1},
    "dark_matter": {"name": "合成暗物质", "inputs": {"rare_metals": 5, "crystals": 5}, "output": 1},
    "antimatter": {"name": "合成反物质", "inputs": {"plasma": 5, "dark_matter": 2}, "output": 1},
}

# 专精加成
SPEC_BONUSES = {
    "military": {"name": "军事专精", "atk_bonus": 0.25, "def_bonus": 0.25, "gold_bonus": 0, "culture_bonus": 0, "tech_bonus": 0, "prod_bonus": -0.1,
                 "desc": "攻击+25% 防御+25% 产出-10%"},
    "economic": {"name": "经济专精", "atk_bonus": 0, "def_bonus": 0, "gold_bonus": 0.3, "culture_bonus": 0, "tech_bonus": 0, "prod_bonus": 0.1,
                 "desc": "金币收入+30% 产出+10%"},
    "cultural": {"name": "文化专精", "atk_bonus": 0, "def_bonus": 0, "gold_bonus": 0, "culture_bonus": 0.3, "tech_bonus": 0.1, "prod_bonus": 0,
                 "desc": "文化+30% 研究+10%"},
    "research": {"name": "科研专精", "atk_bonus": 0, "def_bonus": 0, "gold_bonus": 0, "culture_bonus": 0, "tech_bonus": 0.3, "prod_bonus": 0.05,
                 "desc": "研究+30% 产出+5%"},
}

# ============ V7: 股票板块-资源映射 ============
SECTOR_RESOURCE_MAP = {
    "科技": ["crystals", "rare_metals"],
    "军工": ["rare_metals", "minerals"],
    "能源": ["energy", "plasma"],
    "农业": ["food"],
    "矿业": ["minerals"],
    "金融": [],
    "医药": ["crystals", "plasma"],
    "运输": ["energy", "minerals"],
    "综合": [],
}

# ============ V7: IPO名称生成器 ============
STOCK_PREFIXES = ["星际", "银河", "量子", "暗能", "超光", "等离子", "跃迁", "纳米", "曲率", "脉冲", "超维", "混沌", "永恒", "深渊", "曙光"]
STOCK_SUFFIXES = ["科技", "能源", "矿业", "重工", "电子", "生物", "通信", "运输", "材料", "装备", "工程", "集团", "工业", "系统", "网络"]
SECTORS = ["科技", "军工", "能源", "农业", "矿业", "金融", "医药", "运输", "综合"]

# ============ V8: 战争纪元 配置 ============
FORMATION_BONUSES = {
    "balanced": {"atk_mult": 1.0, "def_mult": 1.0, "loot_bonus": 0, "name": "均衡"},
    "assault":  {"atk_mult": 1.3, "def_mult": 0.8, "loot_bonus": 0, "name": "突击"},
    "siege":    {"atk_mult": 1.15, "def_mult": 0.9, "loot_bonus": 0.10, "name": "攻城"},
}
DEFENSE_FORMATIONS = {
    "fortress": {"def_mult": 1.2, "warehouse_protect": 0.10, "trap_bonus": 0, "name": "堡垒"},
    "ambush":   {"def_mult": 1.0, "warehouse_protect": 0, "trap_bonus": 0.5, "name": "伏击"},
    "retreat":  {"def_mult": 0.9, "warehouse_protect": 0.30, "trap_bonus": 0, "name": "龟缩"},
}
DEFENSE_BUILDINGS = {
    "trap":         {"name": "陷阱阵",    "atk": 0,  "def": 5,  "cost_m": 30, "cost_e": 20, "special": "attacker_debuff"},
    "laser_turret": {"name": "激光炮塔",  "atk": 10, "def": 25, "cost_m": 60, "cost_e": 40, "special": "counter_damage"},
    "missile_silo": {"name": "导弹井",    "atk": 15, "def": 10, "cost_m": 80, "cost_e": 50, "special": "retaliation"},
    "shield_gen":   {"name": "护盾发生器","atk": 0,  "def": 5,  "cost_m": 100,"cost_e": 80, "special": "shield_charge"},
    "autocannon":   {"name": "自动炮台",  "atk": 5,  "def": 15, "cost_m": 50, "cost_e": 30, "special": "auto_retaliate"},
}
ARENA_TITLES = {0: "新兵", 800: "战士", 1000: "精英", 1200: "骑士", 1400: "将军", 1600: "传奇"}
ESPIONAGE_CONFIG = {
    "recon":         {"cost_gold": 200, "cost_dm": 0,  "base_rate": 0.70, "name": "侦察"},
    "sabotage":      {"cost_gold": 500, "cost_dm": 50, "base_rate": 0.40, "name": "破坏"},
    "steal":         {"cost_gold": 300, "cost_dm": 0,  "base_rate": 0.50, "name": "窃取"},
    "counter_intel": {"cost_gold": 200, "cost_dm": 0,  "base_rate": 1.00, "name": "反间谍"},
}
def get_arena_title(rating):
    t = "新兵"
    for threshold, title in sorted(ARENA_TITLES.items()):
        if rating >= threshold: t = title
    return t

# ============ NPC人格系统 ============
NPC_PERSONALITIES = {
    "trader": {
        "name": "星商", "style": "精明", "emoji": "💰",
        "traits": ["话多", "爱吹牛", "关注行情", "精打细算"],
        "chat_style": "啰嗦",
        "chat_freq": 0.8,
        "post_freq": 0.7,
        "trade_freq": 1.5,
        "phrases": [
            "我跟你们说，今天{resource}肯定要涨！",
            "我这波操作赚了{amount}金币，嘿嘿",
            "有内幕消息，{stock}要起飞了！",
            "买涨不买跌，这是我的原则",
            "资源市场的水很深，你们把握不住",
            "别问我怎么知道的，问我就是经验",
            "行情不好就观望，好就加仓",
        ]
    },
    "miner": {
        "name": "矿工", "style": "朴实", "emoji": "⛏️",
        "traits": ["话少", "务实", "勤劳", "闷声发大财"],
        "chat_style": "简短",
        "chat_freq": 0.4,
        "post_freq": 0.3,
        "trade_freq": 0.6,
        "phrases": [
            "挖矿去了",
            "今天产出不错",
            "矿脉快枯竭了",
            "埋头苦干才是正道",
            "别吵了，挖矿",
            "又发现一条矿脉",
        ]
    },
    "scholar": {
        "name": "学者", "style": "博学", "emoji": "📚",
        "traits": ["爱科普", "引经据典", "冷静", "话多但有条理"],
        "chat_style": "学术",
        "chat_freq": 0.7,
        "post_freq": 0.9,
        "trade_freq": 0.4,
        "phrases": [
            "根据我的研究，{tech}的突破将改变格局",
            "量子纠缠的最新论文你们看了吗？",
            "暗物质的采集效率还有很大提升空间",
            "知识就是力量，投资研究永远不会亏",
            "数据显示，{resource}的供需正在失衡",
            "反物质引擎的理论框架已经完善了",
        ]
    },
    "warrior": {
        "name": "战士", "style": "豪爽", "emoji": "⚔️",
        "traits": ["冲动", "好战", "直率", "话糙理不糙"],
        "chat_style": "粗暴",
        "chat_freq": 0.6,
        "post_freq": 0.5,
        "trade_freq": 0.3,
        "phrases": [
            "谁敢挑战我？",
            "武力才是硬道理！",
            "我的防御工事坚不可摧",
            "战场上见真章",
            "别废话，来打一架",
            "今天又赢了{count}场",
        ]
    },
    "merchant": {
        "name": "商人", "style": "圆滑", "emoji": "🏪",
        "traits": ["八面玲珑", "爱聊天", "消息灵通", "话痨"],
        "chat_style": "话痨",
        "chat_freq": 1.0,
        "post_freq": 0.6,
        "trade_freq": 1.2,
        "phrases": [
            "各位各位，今日特价！{resource}量大从优！",
            "嗨，最近怎么样？生意还好吗？",
            "我跟你说，{stock}现在入手正是时候",
            "嘿嘿，又有新货到了",
            "来来来，朋友，看看我的商品",
            "市场就是我的战场，交易就是我的武器",
            "今天的行情不错，大家加油赚金币！",
            "我做了一笔大买卖，开心！",
        ]
    }
}

# NPC聊天话题模板
NPC_CHAT_TOPICS = [
    "最近{resource}价格波动好大啊",
    "有没有人一起探索{sector}？",
    "我的殖民地升级了！",
    "今天天气不错，适合挖矿",
    "谁有多余的{resource}？我高价收",
    "刚被{enemy}打劫了，好气",
    "推荐大家研究{tech}科技",
    "这个游戏的股票太刺激了",
    "我加入{faction}了！",
    "量子矿脉到底在哪啊？",
    "反物质引擎什么时候能用？",
    "暗物质风暴要来了！",
    "有没有人组队去深空探索？",
    "今天赚了不少金币，嘿嘿",
    "防御工事一定要升级，不然容易被打",
    "我的专精选的{spec}，感觉不错",
    "合成稀有金属亏了...",
    "等离子体价格要涨了，快买！",
    "这游戏越来越好玩了",
    "新人求带！",
    "谁有星际地图？",
    "跃迁引擎2.0出了吗？",
    "纳米材料太贵了吧",
    "今天有什么新任务？",
    "派系战什么时候开？",
]

app = FastAPI(title="星际殖民地V8.0-战争纪元", version="8.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

pool = None
redis_client = None

# ============ 实时聊天 ============
chat_connections = []
chat_history = []

async def db_exec(cur, sql, args=()):
    await cur.execute(sql, args)

async def db_query(cur, sql, args=()):
    await cur.execute(sql, args)
    return await cur.fetchall()

async def db_one(cur, sql, args=()):
    await cur.execute(sql, args)
    rows = await cur.fetchall()
    return rows[0] if rows else None

# ============ JWT / Auth ============
def make_token(uid, username=""):
    return jwt.encode({"user_id": uid, "username": username, "exp": time.time()+JWT_EXPIRE}, JWT_SECRET, algorithm="HS256")

def decode_token(t):
    try:
        return jwt.decode(t, JWT_SECRET, algorithms=["HS256"])
    except:
        return None

def extract_token(authorization):
    if not authorization:
        return None
    parts = authorization.split()
    return parts[1] if len(parts)==2 and parts[0].lower()=="bearer" else (parts[0] if parts else None)

async def get_user(authorization: str = Header(None)):
    token = extract_token(authorization)
    if not token:
        raise HTTPException(401, "未登录")
    payload = decode_token(token)
    if not payload:
        raise HTTPException(401, "Token无效")
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            u = await db_one(cur, "SELECT is_banned FROM users WHERE id=%s", (payload["user_id"],))
            if u and u.get("is_banned"):
                raise HTTPException(403, "账号已被封禁")
    return payload["user_id"]

async def get_admin(authorization: str = Header(None)):
    uid = await get_user(authorization)
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            u = await db_one(cur, "SELECT is_admin FROM users WHERE id=%s", (uid,))
            if not u or not u.get("is_admin"):
                raise HTTPException(403, "需要管理员权限")
    return uid

async def get_colony_id(cur, uid):
    c = await db_one(cur, "SELECT id FROM colonies WHERE user_id=%s", (uid,))
    return c["id"] if c else None

async def add_notification(cur, cid, title, content, ntype="info"):
    if not cid: return
    await db_exec(cur, "INSERT INTO notifications (colony_id,title,content,ntype) VALUES (%s,%s,%s,%s)", (cid, title, content, ntype))

# ============ 成就检查 ============
async def check_achievements(cur, cid, uid=None):
    c = await db_one(cur, "SELECT * FROM colonies WHERE id=%s", (cid,))
    if not c: return
    unlocked = {a["achievement_id"] for a in await db_query(cur, "SELECT achievement_id FROM colony_achievements WHERE colony_id=%s", (cid,))}
    all_ach = await db_query(cur, "SELECT * FROM achievements")
    for a in all_ach:
        if a["id"] in unlocked: continue
        earned = False
        code = a["code"]
        if code == "first_trade":
            cnt = await db_one(cur, "SELECT COUNT(*) as cnt FROM trade_history WHERE buyer_id=%s", (cid,))
            if cnt["cnt"] >= 1: earned = True
        elif code == "trade_100":
            cnt = await db_one(cur, "SELECT COUNT(*) as cnt FROM trade_history WHERE buyer_id=%s", (cid,))
            if cnt["cnt"] >= 100: earned = True
        elif code == "rich_10k":
            if c["gold"] >= 10000: earned = True
        elif code == "rich_100k":
            if c["gold"] >= 100000: earned = True
        elif code == "stock_master":
            port = await db_query(cur, "SELECT profit_pct FROM stock_portfolios WHERE colony_id=%s AND amount>0", (cid,))
            if port and all(float(p["profit_pct"]) > 50 for p in port) and len(port) > 0: earned = True
        elif code == "stock_loss":
            port = await db_query(cur, "SELECT profit_pct FROM stock_portfolios WHERE colony_id=%s AND amount>0", (cid,))
            if port and any(float(p["profit_pct"]) < -30 for p in port): earned = True
        elif code == "win_first":
            if c["win_count"] >= 1: earned = True
        elif code == "win_50":
            if c["win_count"] >= 50: earned = True
        elif code == "faction_leader":
            if c["id"]:
                fl = await db_one(cur, "SELECT f.id FROM colony_factions cf JOIN factions f ON cf.faction_id=f.id WHERE cf.colony_id=%s AND cf.role='leader' AND f.member_count>=10", (cid,))
                if fl: earned = True
        elif code == "forum_star":
            posts = await db_query(cur, "SELECT SUM(like_count) as total FROM forum_posts WHERE author_id=%s", (cid,))
            if posts and posts[0]["total"] and int(posts[0]["total"]) >= 100: earned = True
        elif code == "philosopher":
            pc = await db_one(cur, "SELECT COUNT(*) as cnt FROM colony_philosophy WHERE colony_id=%s AND level>0", (cid,))
            if pc["cnt"] >= 5: earned = True
        elif code == "explorer":
            ec = await db_one(cur, "SELECT COUNT(*) as cnt FROM expeditions WHERE colony_id=%s AND status='completed'", (cid,))
            if ec["cnt"] >= 10: earned = True
        elif code == "level_10":
            if c["level"] >= 10: earned = True
        elif code == "daily_7":
            dc = await db_one(cur, "SELECT COUNT(*) as cnt FROM colony_daily_tasks WHERE colony_id=%s AND is_completed=1", (cid,))
            if dc["cnt"] >= 7: earned = True
        # V8新成就
        elif code == "raider_1":
            rc = await db_one(cur, "SELECT COUNT(*) as cnt FROM raids WHERE attacker_id=%s AND result='win'", (cid,))
            if rc["cnt"] >= 1: earned = True
        elif code == "raider_50":
            rc = await db_one(cur, "SELECT COUNT(*) as cnt FROM raids WHERE attacker_id=%s AND result='win'", (cid,))
            if rc["cnt"] >= 50: earned = True
        elif code == "revenge_master":
            rc = await db_one(cur, "SELECT COUNT(*) as cnt FROM raids WHERE attacker_id=%s AND result='win' AND is_revenge=1", (cid,))
            if rc["cnt"] >= 5: earned = True
        elif code == "arena_champion":
            rc = await db_one(cur, "SELECT COUNT(*) as cnt FROM arena_participants WHERE colony_id=%s AND wins>0 AND is_eliminated=0", (cid,))
            if rc["cnt"] >= 1: earned = True
        elif code == "bounty_hunter":
            bc = await db_one(cur, "SELECT COUNT(*) as cnt FROM bounties WHERE claimed_by=%s", (cid,))
            if bc["cnt"] >= 3: earned = True
        elif code == "spy_master":
            sc = await db_one(cur, "SELECT COUNT(*) as cnt FROM espionage_ops WHERE spy_id=%s AND result='success'", (cid,))
            if sc["cnt"] >= 10: earned = True
        if earned:
            await db_exec(cur, "INSERT IGNORE INTO colony_achievements (colony_id,achievement_id) VALUES (%s,%s)", (cid, a["id"]))
            await db_exec(cur, "UPDATE colonies SET gold=gold+%s,score=score+%s WHERE id=%s", (a["reward_gold"], a["reward_score"], cid))
            await add_notification(cur, cid, "成就解锁！", f"【{a['name']}】{a['description']}，奖励{a['reward_gold']}金币", "achievement")

# ============ AI模型调用 ============
async def call_ai(prompt, npc_cfg=None, timeout=8):
    model_cfg = None
    if npc_cfg and npc_cfg.get("ai_api_url") and npc_cfg.get("ai_api_key"):
        model_cfg = {"url": npc_cfg["ai_api_url"], "key": npc_cfg["ai_api_key"], "model": npc_cfg.get("ai_model","deepseek-chat")}
    elif npc_cfg and npc_cfg.get("model_name"):
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    cfg = await db_one(cur, "SELECT * FROM ai_model_configs WHERE model_name=%s AND is_active=1 LIMIT 1", (npc_cfg["model_name"],))
                    if not cfg:
                        cfg = await db_one(cur, "SELECT * FROM ai_model_configs WHERE is_default=1 AND is_active=1 LIMIT 1")
                    if cfg:
                        model_cfg = {"url": cfg["api_url"], "key": cfg["api_key"], "model": cfg["model_name"], "max_tokens": cfg.get("max_tokens",256)}
        except: pass
    if not model_cfg:
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    cfg = await db_one(cur, "SELECT * FROM ai_model_configs WHERE is_default=1 AND is_active=1 LIMIT 1")
                    if cfg:
                        model_cfg = {"url": cfg["api_url"], "key": cfg["api_key"], "model": cfg["model_name"], "max_tokens": cfg.get("max_tokens",256)}
        except: pass
    if model_cfg:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(model_cfg["url"],
                    headers={"Authorization": f"Bearer {model_cfg['key']}", "Content-Type": "application/json"},
                    json={"model": model_cfg["model"], "messages": [{"role":"user","content":prompt}], "max_tokens": model_cfg.get("max_tokens",256), "temperature": 0.8})
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            log.warning(f"AI调用失败: {e}")
    return None

# ============ 启动 ============
@asynccontextmanager
async def lifespan(app):
    global pool, redis_client
    for attempt in range(30):
        try:
            pool = await aiomysql.create_pool(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS, db=DB_NAME,
                autocommit=True, minsize=2, maxsize=10, charset="utf8mb4",
                init_command="SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci")
            break
        except Exception as e:
            log.warning(f"DB连接失败({attempt+1}/30): {e}")
            await asyncio.sleep(2)
    redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
    log.info("DB+Redis连接成功")
    # 数据库迁移
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("ALTER TABLE users ADD COLUMN is_banned TINYINT(1) DEFAULT 0")
    except: pass
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("ALTER TABLE colonies ADD COLUMN specialization VARCHAR(32) DEFAULT 'none'")
    except: pass
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("ALTER TABLE colonies ADD COLUMN rare_metals INT DEFAULT 0")
                await cur.execute("ALTER TABLE colonies ADD COLUMN crystals INT DEFAULT 0")
                await cur.execute("ALTER TABLE colonies ADD COLUMN plasma INT DEFAULT 0")
                await cur.execute("ALTER TABLE colonies ADD COLUMN dark_matter INT DEFAULT 0")
                await cur.execute("ALTER TABLE colonies ADD COLUMN antimatter INT DEFAULT 0")
    except: pass
    # V7: colonies.last_collect
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("ALTER TABLE colonies ADD COLUMN last_collect TIMESTAMP NULL")
    except: pass
    # V7: stocks daily volume tracking
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("ALTER TABLE stocks ADD COLUMN daily_buy_vol INT DEFAULT 0")
                await cur.execute("ALTER TABLE stocks ADD COLUMN daily_buy_amount FLOAT DEFAULT 0")
                await cur.execute("ALTER TABLE stocks ADD COLUMN daily_sell_vol INT DEFAULT 0")
                await cur.execute("ALTER TABLE stocks ADD COLUMN daily_sell_amount FLOAT DEFAULT 0")
    except: pass
    # V7: admin flag
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("ALTER TABLE users ADD COLUMN is_admin TINYINT(1) DEFAULT 0")
    except: pass
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("ALTER TABLE forum_posts ADD COLUMN is_npc TINYINT(1) DEFAULT 0")
    except: pass
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("ALTER TABLE forum_replies ADD COLUMN is_npc TINYINT(1) DEFAULT 0")
    except: pass
    # 新增表：聊天室
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""CREATE TABLE IF NOT EXISTS chat_messages (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    colony_id INT,
                    author_name VARCHAR(64) NOT NULL,
                    message TEXT NOT NULL,
                    is_npc TINYINT(1) DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_chat_time (created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
    except Exception as e:
        log.warning(f"chat_messages建表: {e}")
    # 新增表：上帝AI日志
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""CREATE TABLE IF NOT EXISTS god_ai_log (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    action_type VARCHAR(32) NOT NULL,
                    description TEXT,
                    effect_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
    except Exception as e:
        log.warning(f"god_ai_log建表: {e}")
    # V7: stock_ipo_log表
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""CREATE TABLE IF NOT EXISTS stock_ipo_log (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    stock_code VARCHAR(16),
                    stock_name VARCHAR(64),
                    ipo_price FLOAT,
                    ipo_date DATE,
                    status VARCHAR(16) DEFAULT 'listed',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
    except Exception as e:
        log.warning(f"stock_ipo_log建表: {e}")
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""CREATE TABLE IF NOT EXISTS faction_missions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    faction_id INT NOT NULL,
                    mission_type VARCHAR(32) NOT NULL,
                    title VARCHAR(128) NOT NULL,
                    description TEXT,
                    target_value INT DEFAULT 1,
                    reward_gold INT DEFAULT 100,
                    reward_score INT DEFAULT 50,
                    reward_faction_pts INT DEFAULT 10,
                    task_date DATE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_fm_faction (faction_id, task_date)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
                await cur.execute("""CREATE TABLE IF NOT EXISTS faction_mission_progress (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    mission_id INT NOT NULL,
                    colony_id INT NOT NULL,
                    progress INT DEFAULT 0,
                    is_completed TINYINT(1) DEFAULT 0,
                    UNIQUE KEY uk_mc (mission_id, colony_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
                await cur.execute("""CREATE TABLE IF NOT EXISTS faction_resource_pool (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    faction_id INT NOT NULL,
                    resource_type VARCHAR(32) NOT NULL,
                    amount INT DEFAULT 0,
                    UNIQUE KEY uk_fr (faction_id, resource_type)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
                await cur.execute("""CREATE TABLE IF NOT EXISTS forum_influence (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    post_id INT NOT NULL,
                    influence_type VARCHAR(32) NOT NULL,
                    target_type VARCHAR(32),
                    target_id VARCHAR(32),
                    effect_value FLOAT DEFAULT 0,
                    expires_at TIMESTAMP NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
                await cur.execute("""CREATE TABLE IF NOT EXISTS colony_craft_log (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    colony_id INT NOT NULL,
                    recipe_id VARCHAR(32) NOT NULL,
                    amount INT DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
    except Exception as e:
        log.warning(f"建表迁移: {e}")
    # ============ V8: 战争纪元 数据库迁移 ============
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                # colonies表扩展
                for col, default in [("shield_until","NULL"),("last_raid_at","NULL"),("raid_fatigue","0"),
                    ("revenge_tokens","0"),("arena_rating","1000"),("bounty_on_me","0"),("spy_defense","0"),("war_contribution","0")]:
                    try: await cur.execute(f"ALTER TABLE colonies ADD COLUMN {col} {'TIMESTAMP NULL' if 'NULL' in default and 'at' in col else 'INT DEFAULT '+default if default not in ('NULL',) else 'TIMESTAMP NULL' if 'at' in col else 'INT DEFAULT 0'}")
                    except: pass
                # 修正: shield_until和last_raid_at是TIMESTAMP, 其他是INT
                try: await cur.execute("ALTER TABLE colonies ADD COLUMN shield_until TIMESTAMP NULL")
                except: pass
                try: await cur.execute("ALTER TABLE colonies ADD COLUMN last_raid_at TIMESTAMP NULL")
                except: pass
                try: await cur.execute("ALTER TABLE colonies ADD COLUMN raid_fatigue INT DEFAULT 0")
                except: pass
                try: await cur.execute("ALTER TABLE colonies ADD COLUMN revenge_tokens INT DEFAULT 0")
                except: pass
                try: await cur.execute("ALTER TABLE colonies ADD COLUMN arena_rating INT DEFAULT 1000")
                except: pass
                try: await cur.execute("ALTER TABLE colonies ADD COLUMN bounty_on_me INT DEFAULT 0")
                except: pass
                try: await cur.execute("ALTER TABLE colonies ADD COLUMN spy_defense INT DEFAULT 0")
                except: pass
                try: await cur.execute("ALTER TABLE colonies ADD COLUMN war_contribution INT DEFAULT 0")
                except: pass
                # diplomacy表扩展
                try: await cur.execute("ALTER TABLE diplomacy ADD COLUMN proposed_by INT")
                except: pass
                try: await cur.execute("ALTER TABLE diplomacy ADD COLUMN expires_at TIMESTAMP NULL")
                except: pass
                try: await cur.execute("ALTER TABLE diplomacy ADD COLUMN is_pending TINYINT(1) DEFAULT 0")
                except: pass
                # raids表
                await cur.execute("""CREATE TABLE IF NOT EXISTS raids (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    attacker_id INT NOT NULL, defender_id INT NOT NULL,
                    attacker_power INT DEFAULT 0, defender_power INT DEFAULT 0,
                    formation VARCHAR(16) DEFAULT 'balanced',
                    result VARCHAR(8) NOT NULL, loot_json TEXT, loot_pct INT DEFAULT 0,
                    is_revenge TINYINT(1) DEFAULT 0, revenge_from INT,
                    fatigue_count INT DEFAULT 0, fatigue_penalty FLOAT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_raid_attacker (attacker_id, created_at DESC),
                    INDEX idx_raid_defender (defender_id, created_at DESC)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
                # colony_shields表
                await cur.execute("""CREATE TABLE IF NOT EXISTS colony_shields (
                    id INT AUTO_INCREMENT PRIMARY KEY, colony_id INT NOT NULL UNIQUE,
                    shield_type VARCHAR(16) DEFAULT 'none', shield_until TIMESTAMP NULL,
                    shield_charges INT DEFAULT 0, last_broken_at TIMESTAMP NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
                # colony_defenses表
                await cur.execute("""CREATE TABLE IF NOT EXISTS colony_defenses (
                    id INT AUTO_INCREMENT PRIMARY KEY, colony_id INT NOT NULL,
                    defense_type VARCHAR(32) NOT NULL, level INT DEFAULT 1,
                    hp INT DEFAULT 100, max_hp INT DEFAULT 100,
                    slot INT NOT NULL, is_active TINYINT(1) DEFAULT 1,
                    UNIQUE KEY uk_defense_slot (colony_id, slot)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
                # colony_defense_formation表
                await cur.execute("""CREATE TABLE IF NOT EXISTS colony_defense_formation (
                    colony_id INT NOT NULL PRIMARY KEY, formation VARCHAR(16) DEFAULT 'fortress'
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
                # battle_reports表
                await cur.execute("""CREATE TABLE IF NOT EXISTS battle_reports (
                    id INT AUTO_INCREMENT PRIMARY KEY, raid_id INT,
                    attacker_id INT NOT NULL, defender_id INT NOT NULL,
                    attacker_name VARCHAR(64), defender_name VARCHAR(64),
                    report_type VARCHAR(16) NOT NULL,
                    attacker_power INT DEFAULT 0, defender_power INT DEFAULT 0,
                    attacker_formation VARCHAR(16), defender_formation VARCHAR(16),
                    battle_phases_json TEXT, result VARCHAR(8) NOT NULL,
                    loot_json TEXT, is_read TINYINT(1) DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_report_attacker (attacker_id, is_read, created_at DESC),
                    INDEX idx_report_defender (defender_id, is_read, created_at DESC)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
                # faction_wars表
                await cur.execute("""CREATE TABLE IF NOT EXISTS faction_wars (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    attacker_faction INT NOT NULL, defender_faction INT NOT NULL,
                    war_type VARCHAR(16) DEFAULT 'declaration',
                    status VARCHAR(16) DEFAULT 'active',
                    attacker_score INT DEFAULT 0, defender_score INT DEFAULT 0,
                    territory_id INT, started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ended_at TIMESTAMP NULL, INDEX idx_war_status (status)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
                # bounties表
                await cur.execute("""CREATE TABLE IF NOT EXISTS bounties (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    target_id INT NOT NULL, placer_id INT NOT NULL,
                    amount INT NOT NULL, reason VARCHAR(256),
                    status VARCHAR(16) DEFAULT 'active',
                    claimed_by INT, claimed_at TIMESTAMP NULL,
                    escalation INT DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NULL,
                    INDEX idx_bounty_target (target_id, status),
                    INDEX idx_bounty_active (status, created_at DESC)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
                # arena_tournaments表
                await cur.execute("""CREATE TABLE IF NOT EXISTS arena_tournaments (
                    id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(64) NOT NULL,
                    tournament_type VARCHAR(16) DEFAULT 'daily',
                    tier VARCHAR(16) DEFAULT 'open', max_participants INT DEFAULT 32,
                    entry_fee INT DEFAULT 100, prize_pool INT DEFAULT 1000,
                    status VARCHAR(16) DEFAULT 'upcoming',
                    started_at TIMESTAMP NULL, completed_at TIMESTAMP NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
                # arena_participants表
                await cur.execute("""CREATE TABLE IF NOT EXISTS arena_participants (
                    id INT AUTO_INCREMENT PRIMARY KEY, tournament_id INT NOT NULL,
                    colony_id INT NOT NULL, bracket_pos INT DEFAULT 0,
                    wins INT DEFAULT 0, losses INT DEFAULT 0,
                    is_eliminated TINYINT(1) DEFAULT 0, final_rank INT,
                    UNIQUE KEY uk_tournament_colony (tournament_id, colony_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
                # arena_matches表
                await cur.execute("""CREATE TABLE IF NOT EXISTS arena_matches (
                    id INT AUTO_INCREMENT PRIMARY KEY, tournament_id INT NOT NULL,
                    round_num INT NOT NULL, colony_a INT NOT NULL, colony_b INT NOT NULL,
                    winner_id INT, result_json TEXT, fought_at TIMESTAMP NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
                # espionage_ops表
                await cur.execute("""CREATE TABLE IF NOT EXISTS espionage_ops (
                    id INT AUTO_INCREMENT PRIMARY KEY, spy_id INT NOT NULL,
                    target_id INT NOT NULL, op_type VARCHAR(16) NOT NULL,
                    success_rate FLOAT DEFAULT 0.5, result VARCHAR(16),
                    intel_json TEXT, damage_json TEXT, cost_gold INT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_espionage_spy (spy_id, created_at DESC)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
                # V8新成就
                for code, name, desc, cat, reward in [
                    ("raider_1","初次掠夺","成功完成1次袭击","combat",200),
                    ("raider_50","战争之王","累计赢得50次袭击","combat",3000),
                    ("revenge_master","复仇者","成功复仇5次","combat",1000),
                    ("arena_champion","竞技场冠军","赢得1次锦标赛","combat",5000),
                    ("bounty_hunter","赏金猎人","领取3次赏金","combat",2000),
                    ("spy_master","暗影大师","成功10次间谍行动","combat",2000)]:
                    try: await cur.execute(f"INSERT IGNORE INTO achievements (code,name,description,category,icon,reward_gold,reward_score) VALUES (%s,%s,%s,%s,'crossed-swords',%s,100)", (code,name,desc,cat,reward))
                    except: pass
                log.info("V8数据库迁移完成")
    except Exception as e:
        log.warning(f"V8建表迁移: {e}")
    # 更新NPC人格
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("UPDATE npc_bots SET personality='trader' WHERE user_id=5")
                await cur.execute("UPDATE npc_bots SET personality='miner' WHERE user_id=6")
                await cur.execute("UPDATE npc_bots SET personality='scholar' WHERE user_id=7")
                await cur.execute("UPDATE npc_bots SET personality='warrior' WHERE user_id=8")
                await cur.execute("UPDATE npc_bots SET personality='merchant' WHERE user_id=9")
    except Exception as e:
        log.warning(f"NPC人格更新: {e}")
    # 启动后台任务
    asyncio.create_task(bg_stock_engine())
    asyncio.create_task(bg_kline_recorder())
    asyncio.create_task(bg_market_maker())
    asyncio.create_task(bg_futures_liquidation())
    asyncio.create_task(bg_npc_scheduler())
    asyncio.create_task(bg_territory_refresh())
    asyncio.create_task(bg_daily_event())
    asyncio.create_task(bg_expedition_check())
    asyncio.create_task(bg_daily_task_generator())
    asyncio.create_task(bg_achievement_checker())
    asyncio.create_task(bg_territory_income())
    asyncio.create_task(bg_faction_mission_refresh())
    asyncio.create_task(bg_npc_forum_post())
    asyncio.create_task(bg_forum_influence())
    asyncio.create_task(bg_npc_chat())
    asyncio.create_task(bg_god_ai())
    asyncio.create_task(bg_stock_ipo_delist())
    # V8后台任务
    asyncio.create_task(bg_arena_scheduler())
    asyncio.create_task(bg_war_score_decay())
    asyncio.create_task(bg_bounty_expiry())
    log.info("V8后台任务已启动")
    yield
    pool.close()
    await pool.wait_closed()

app.router.lifespan_context = lifespan

# ============================================================
#  认证
# ============================================================
@app.post("/api/register")
async def register(m: RegModel):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            if len(m.password) < 6: raise HTTPException(400, "密码至少6位")
            if len(m.username) < 2: raise HTTPException(400, "用户名至少2位")
            ex = await db_one(cur, "SELECT id FROM users WHERE username=%s OR email=%s", (m.username, m.email))
            if ex: raise HTTPException(400, "用户名或邮箱已存在")
            pw_hash = bcrypt.hash(m.password)
            await db_exec(cur, "INSERT INTO users (username,email,password_hash) VALUES (%s,%s,%s)", (m.username, m.email, pw_hash))
            uid = cur.lastrowid
            await db_exec(cur, "INSERT INTO colonies (user_id,name,planet_type) VALUES (%s,%s,%s)", (uid, m.colony_name, m.planet_type))
            cid = cur.lastrowid
            await add_notification(cur, cid, "欢迎来到星际殖民地！", f"殖民地【{m.colony_name}】已建立！", "info")
            return {"user_id": uid, "colony_id": cid, "access_token": make_token(uid, m.username)}

@app.post("/api/login")
async def login(m: LoginModel):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            u = await db_one(cur, "SELECT * FROM users WHERE username=%s", (m.username,))
            if not u or not bcrypt.verify(m.password, u["password_hash"]):
                raise HTTPException(400, "用户名或密码错误")
            if u.get("is_banned"):
                raise HTTPException(403, "账号已被封禁，请联系管理员")
            return {"access_token": make_token(u["id"], u["username"]), "user_id": u["id"]}

# ============================================================
#  殖民地
# ============================================================
@app.get("/api/colony")
async def get_colony(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            c = await db_one(cur, "SELECT c.*, u.username FROM colonies c JOIN users u ON c.user_id=u.id WHERE c.user_id=%s", (uid,))
            if not c: raise HTTPException(404, "殖民地不存在")
            blds = await db_query(cur, "SELECT b.*, bc.display_name FROM buildings b JOIN building_config bc ON b.building_type=bc.building_type WHERE b.colony_id=%s", (c["id"],))
            techs = await db_query(cur, "SELECT t.*, tc.display_name FROM techs t JOIN tech_config tc ON t.tech_type=tc.tech_type WHERE t.colony_id=%s", (c["id"],))
            phils = await db_query(cur, "SELECT cp.*, pc.display_name, pc.max_level FROM colony_philosophy cp JOIN philosophy_config pc ON cp.philosophy_type=pc.philosophy_type WHERE cp.colony_id=%s", (c["id"],))
            terr_count = await db_one(cur, "SELECT COUNT(*) as cnt FROM territories WHERE owner_colony=%s AND is_active=1", (c["id"],))
            c["territory_count"] = terr_count["cnt"] if terr_count else 0
            spec = c.get("specialization", "none") or "none"
            c["spec_info"] = SPEC_BONUSES.get(spec, {"name": "无", "desc": "未选择专精"})
            await db_exec(cur, "UPDATE colonies SET last_online=NOW() WHERE id=%s", (c["id"],))
            return {"colony": c, "buildings": blds, "techs": techs, "philosophies": phils}

@app.post("/api/colony/build")
async def build(m: BuildModel, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            cfg = await db_one(cur, "SELECT * FROM building_config WHERE building_type=%s", (m.building_type,))
            if not cfg: raise HTTPException(400, "未知建筑")
            c = await db_one(cur, "SELECT * FROM colonies WHERE user_id=%s", (uid,))
            ex = await db_one(cur, "SELECT id FROM buildings WHERE colony_id=%s AND slot=%s", (c["id"], m.slot))
            if ex: raise HTTPException(400, "该位置已有建筑")
            if c["minerals"]<cfg["cost_minerals"] or c["energy"]<cfg["cost_energy"] or c["food"]<cfg["cost_food"] or c["gold"]<cfg["cost_gold"]:
                raise HTTPException(400, "资源不足")
            await db_exec(cur, "UPDATE colonies SET minerals=minerals-%s,energy=energy-%s,food=food-%s,gold=gold-%s WHERE id=%s",
                (cfg["cost_minerals"], cfg["cost_energy"], cfg["cost_food"], cfg["cost_gold"], c["id"]))
            await db_exec(cur, "INSERT INTO buildings (colony_id,building_type,slot) VALUES (%s,%s,%s)", (c["id"], m.building_type, m.slot))
            await recalc_power(cur, c["id"])
            return {"msg": f"建造{cfg['display_name']}成功"}

@app.post("/api/colony/collect")
async def collect(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            c = await db_one(cur, "SELECT * FROM colonies WHERE user_id=%s", (uid,))
            # V7: 收集冷却检查 - 使用数据库时间计算避免时区问题
            last_collect = c.get("last_collect")
            if last_collect:
                cd = await db_one(cur, "SELECT TIMESTAMPDIFF(SECOND, %s, NOW()) as elapsed", (last_collect,))
                elapsed = cd["elapsed"] if cd else 0
                if elapsed is not None and elapsed < 60:
                    remaining = 60 - int(elapsed)
                    raise HTTPException(400, f"冷却中，还需等待{remaining}秒")
            # 用数据库NOW()统一时区，避免Python datetime与MySQL时区不一致
            now_row = await db_one(cur, "SELECT NOW() as now_ts")
            now = now_row["now_ts"] if now_row else datetime.now()
            last = c["last_online"] or now
            hours = min((now-last).total_seconds()/3600, 24)
            spec = c.get("specialization", "none") or "none"
            spec_bonus = SPEC_BONUSES.get(spec, {})
            prod_mult = 1 + spec_bonus.get("prod_bonus", 0)
            gold_mult = 1 + spec_bonus.get("gold_bonus", 0)
            blds = await db_query(cur, "SELECT b.*, bc.produces_minerals, bc.produces_energy, bc.produces_food, bc.produces_gold FROM buildings b JOIN building_config bc ON b.building_type=bc.building_type WHERE b.colony_id=%s", (c["id"],))
            g = {"minerals":0,"energy":0,"food":0,"gold":0}
            for b in blds:
                lvl = b.get("level",1)
                g["minerals"] += int(b["produces_minerals"]*hours*lvl*prod_mult)
                g["energy"] += int(b["produces_energy"]*hours*lvl*prod_mult)
                g["food"] += int(b["produces_food"]*hours*lvl*prod_mult)
                g["gold"] += int(b["produces_gold"]*hours*lvl*gold_mult)
            await db_exec(cur, "UPDATE colonies SET minerals=minerals+%s,energy=energy+%s,food=food+%s,gold=gold+%s,last_online=NOW(),last_collect=NOW() WHERE id=%s",
                (g["minerals"], g["energy"], g["food"], g["gold"], c["id"]))
            return {"collected_hours": round(hours,1), "gains": g}

@app.post("/api/colony/level_up")
async def colony_level_up(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            c = await db_one(cur, "SELECT * FROM colonies WHERE user_id=%s", (uid,))
            lvl = c.get("level", 1)
            cost_gold = lvl * 500
            need_xp = lvl * 100
            if c["gold"] < cost_gold:
                raise HTTPException(400, f"金币不足，升级需要{cost_gold}金")
            if c["xp"] < need_xp:
                raise HTTPException(400, f"经验不足，升级需要{need_xp}XP")
            new_lvl = lvl + 1
            await db_exec(cur, "UPDATE colonies SET level=%s, gold=gold-%s, xp=xp-%s, attack_power=attack_power+5, defense_power=defense_power+5 WHERE id=%s",
                (new_lvl, cost_gold, need_xp, c["id"]))
            await add_notification(cur, c["id"], "殖民地升级！", f"你的殖民地升级到了{new_lvl}级！攻击+5 防御+5", "info")
            return {"msg": f"殖民地升级到{new_lvl}级！攻击+5 防御+5", "new_level": new_lvl}

@app.post("/api/colony/research_tech")
async def research_tech(m: TechModel, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            cfg = await db_one(cur, "SELECT * FROM tech_config WHERE tech_type=%s", (m.tech_type,))
            c = await db_one(cur, "SELECT * FROM colonies WHERE user_id=%s", (uid,))
            t = await db_one(cur, "SELECT * FROM techs WHERE colony_id=%s AND tech_type=%s", (c["id"], m.tech_type))
            lvl = (t["level"] if t else 0) + 1
            if lvl > cfg["max_level"]: raise HTTPException(400, "已达最高等级")
            spec = c.get("specialization", "none") or "none"
            tech_mult = 1 + SPEC_BONUSES.get(spec, {}).get("tech_bonus", 0)
            cm = int(cfg["cost_minerals_per_level"]*lvl/tech_mult); ce = int(cfg["cost_energy_per_level"]*lvl/tech_mult); cf = int(cfg["cost_food_per_level"]*lvl/tech_mult); cg = int(cfg.get("cost_gold",0)*lvl/tech_mult)
            if c["minerals"]<cm or c["energy"]<ce or c["food"]<cf or c["gold"]<cg: raise HTTPException(400, "资源不足")
            await db_exec(cur, "UPDATE colonies SET minerals=minerals-%s,energy=energy-%s,food=food-%s,gold=gold-%s WHERE id=%s", (cm,ce,cf,cg,c["id"]))
            await db_exec(cur, "INSERT INTO techs (colony_id,tech_type,level) VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE level=%s", (c["id"],m.tech_type,lvl,lvl))
            return {"msg": f"科技{cfg['display_name']}升级到{lvl}级"}

@app.post("/api/colony/upgrade_building")
async def upgrade_building(slot: int, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            c = await db_one(cur, "SELECT * FROM colonies WHERE user_id=%s", (uid,))
            b = await db_one(cur, "SELECT * FROM buildings WHERE colony_id=%s AND slot=%s", (c["id"], slot))
            if not b: raise HTTPException(400, "无建筑")
            cfg = await db_one(cur, "SELECT * FROM building_config WHERE building_type=%s", (b["building_type"],))
            cm = int(cfg["cost_minerals"]*(b["level"]+1)*1.5); ce = int(cfg["cost_energy"]*(b["level"]+1)*1.5)
            if c["minerals"]<cm or c["energy"]<ce: raise HTTPException(400, "资源不足")
            await db_exec(cur, "UPDATE colonies SET minerals=minerals-%s,energy=energy-%s WHERE id=%s", (cm,ce,c["id"]))
            await db_exec(cur, "UPDATE buildings SET level=level+1 WHERE id=%s", (b["id"],))
            await recalc_power(cur, c["id"])
            return {"msg": f"{cfg['display_name']}升级到{b['level']+1}级"}

@app.post("/api/colony/specialize")
async def set_specialization(m: SpecializeModel, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            if m.spec_type not in SPEC_BONUSES:
                raise HTTPException(400, f"未知专精类型，可选: {list(SPEC_BONUSES.keys())}")
            c = await db_one(cur, "SELECT * FROM colonies WHERE user_id=%s", (uid,))
            await db_exec(cur, "UPDATE colonies SET specialization=%s WHERE id=%s", (m.spec_type, c["id"]))
            return {"msg": f"已切换为{SPEC_BONUSES[m.spec_type]['name']}：{SPEC_BONUSES[m.spec_type]['desc']}"}

@app.post("/api/colony/craft")
async def craft_resource(m: CraftModel, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            recipe = CRAFT_RECIPES.get(m.recipe_id)
            if not recipe: raise HTTPException(400, f"未知配方，可选: {list(CRAFT_RECIPES.keys())}")
            c = await db_one(cur, "SELECT * FROM colonies WHERE user_id=%s", (uid,))
            for res, need in recipe["inputs"].items():
                need_total = need * m.amount
                if c[res] < need_total:
                    raise HTTPException(400, f"{RESOURCE_MAP[res]['name']}不足（需{need_total}，有{c[res]}）")
            for res, need in recipe["inputs"].items():
                need_total = need * m.amount
                await db_exec(cur, f"UPDATE colonies SET {res}={res}-%s WHERE id=%s", (need_total, c["id"]))
            output_amount = recipe["output"] * m.amount
            await db_exec(cur, f"UPDATE colonies SET {m.recipe_id}={m.recipe_id}+%s WHERE id=%s", (output_amount, c["id"]))
            await db_exec(cur, "INSERT INTO colony_craft_log (colony_id,recipe_id,amount) VALUES (%s,%s,%s)", (c["id"], m.recipe_id, m.amount))
            return {"msg": f"合成成功：{recipe['name']} x{m.amount}"}

@app.get("/api/colony/craft_recipes")
async def get_craft_recipes(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            c = await db_one(cur, "SELECT * FROM colonies WHERE user_id=%s", (uid,))
            recipes = []
            for rid, r in CRAFT_RECIPES.items():
                can_craft = all(c.get(res, 0) >= need for res, need in r["inputs"].items())
                recipes.append({
                    "id": rid, "name": r["name"], "inputs": r["inputs"],
                    "output": r["output"], "can_craft": can_craft,
                    "input_names": {RESOURCE_MAP[res]["name"]: need for res, need in r["inputs"].items()},
                    "output_name": RESOURCE_MAP[rid]["name"]
                })
            return {"recipes": recipes}

async def recalc_power(cur, cid):
    blds = await db_query(cur, "SELECT b.building_type, b.level, bc.attack_bonus, bc.defense_bonus FROM buildings b JOIN building_config bc ON b.building_type=bc.building_type WHERE b.colony_id=%s", (cid,))
    c = await db_one(cur, "SELECT specialization FROM colonies WHERE id=%s", (cid,))
    spec = c.get("specialization", "none") or "none" if c else "none"
    spec_bonus = SPEC_BONUSES.get(spec, {})
    atk = 10; dfn = 10
    for b in blds:
        atk += int(b["attack_bonus"]*b["level"])
        dfn += int(b["defense_bonus"]*b["level"])
    atk = int(atk * (1 + spec_bonus.get("atk_bonus", 0)))
    dfn = int(dfn * (1 + spec_bonus.get("def_bonus", 0)))
    await db_exec(cur, "UPDATE colonies SET attack_power=%s, defense_power=%s WHERE id=%s", (atk, dfn, cid))

@app.post("/api/attack")
async def attack(m: AttackModel, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            c = await db_one(cur, "SELECT * FROM colonies WHERE user_id=%s", (uid,))
            t = await db_one(cur, "SELECT * FROM colonies WHERE id=%s AND id!=%s", (m.target_id, c["id"]))
            if not t: raise HTTPException(400, "目标不存在")
            atk = c["attack_power"]*(1+random.random()*0.2)
            dfn = t["defense_power"]*(1+random.random()*0.2)
            if atk > dfn:
                pct = random.randint(10,20)
                sm = int(t["minerals"]*pct/100); se = int(t["energy"]*pct/100); sf = int(t["food"]*pct/100)
                await db_exec(cur, "UPDATE colonies SET minerals=minerals-%s,energy=energy-%s,food=food-%s WHERE id=%s", (sm,se,sf,t["id"]))
                await db_exec(cur, "UPDATE colonies SET minerals=minerals+%s,energy=energy+%s,food=food+%s,score=score+10,win_count=win_count+1 WHERE id=%s", (sm,se,sf,c["id"]))
                await db_exec(cur, "UPDATE colonies SET lose_count=lose_count+1 WHERE id=%s", (t["id"],))
                await db_exec(cur, "INSERT INTO battle_logs (attacker_id,defender_id,result,minerals_stolen,energy_stolen,food_stolen) VALUES (%s,%s,'win',%s,%s,%s)", (c["id"],t["id"],sm,se,sf))
                await add_notification(cur, t["id"], "被攻击！", f"被{c['name']}攻击，损失矿{sm}能{se}食{sf}", "danger")
                await check_achievements(cur, c["id"], uid)
                return {"result":"win","stolen":{"minerals":sm,"energy":se,"food":sf}}
            else:
                await db_exec(cur, "UPDATE colonies SET lose_count=lose_count+1 WHERE id=%s", (c["id"],))
                await db_exec(cur, "UPDATE colonies SET score=score+5,win_count=win_count+1 WHERE id=%s", (t["id"],))
                await db_exec(cur, "INSERT INTO battle_logs (attacker_id,defender_id,result) VALUES (%s,%s,'lose')", (c["id"], t["id"]))
                return {"result":"lose"}

# ============================================================
#  V8 战争纪元 — 核心战斗引擎
# ============================================================

async def execute_raid(cur, attacker, defender, formation="balanced", is_revenge=False, revenge_raid_id=None):
    """V8核心袭击执行引擎 - 返回袭击结果"""
    # 新手保护
    for colony in [attacker, defender]:
        age = await db_one(cur, "SELECT TIMESTAMPDIFF(DAY, created_at, NOW()) as days FROM colonies WHERE id=%s", (colony["id"],))
        if age and age["days"] < 7 and colony["level"] < 4:
            return {"result": "blocked", "msg": "新手保护期内(7天/3级以下)"}
    # 战力匹配
    if defender["defense_power"] > attacker["attack_power"] * 3:
        return {"result": "blocked", "msg": "目标战力远超自身，无法袭击"}
    # 护盾检查
    shield = await db_one(cur, "SELECT * FROM colony_shields WHERE colony_id=%s", (defender["id"],))
    if shield and shield["shield_until"] and shield["shield_type"] != "none":
        now_row = await db_one(cur, "SELECT NOW() as now_ts")
        if now_row and shield["shield_until"] > now_row["now_ts"]:
            if shield["shield_charges"] > 0:
                await db_exec(cur, "UPDATE colony_shields SET shield_charges=shield_charges-1, last_broken_at=NOW() WHERE colony_id=%s", (defender["id"],))
                if shield["shield_charges"] <= 1:
                    await db_exec(cur, "UPDATE colony_shields SET shield_type='none', shield_until=NULL WHERE colony_id=%s", (defender["id"],))
                return {"result": "shielded", "msg": f"目标护盾吸收了攻击！(剩余{shield['shield_charges']-1}次)"}
            else:
                await db_exec(cur, "UPDATE colony_shields SET shield_type='none', shield_until=NULL WHERE colony_id=%s", (defender["id"],))
    # 疲劳计算
    week_raids = await db_one(cur, "SELECT COUNT(*) as cnt FROM raids WHERE attacker_id=%s AND created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)", (attacker["id"],))
    fatigue = week_raids["cnt"] if week_raids else 0
    fatigue_penalty = max(0.5, 1.0 - max(0, fatigue - 3) * 0.15)
    # 攻击方战力
    f_bonus = FORMATION_BONUSES.get(formation, FORMATION_BONUSES["balanced"])
    spec = SPEC_BONUSES.get(attacker.get("specialization", "none") or "none", {})
    atk_power = attacker["attack_power"] * f_bonus["atk_mult"] * (1 + spec.get("atk_bonus", 0))
    # 防守方战力
    defense_structures = await db_query(cur, "SELECT * FROM colony_defenses WHERE colony_id=%s AND is_active=1", (defender["id"],))
    structure_def = sum(d["level"] * DEFENSE_BUILDINGS.get(d["defense_type"], {}).get("def", 0) for d in defense_structures)
    def_form_row = await db_one(cur, "SELECT formation FROM colony_defense_formation WHERE colony_id=%s", (defender["id"],))
    def_formation = def_form_row["formation"] if def_form_row else "fortress"
    d_bonus = DEFENSE_FORMATIONS.get(def_formation, DEFENSE_FORMATIONS["fortress"])
    def_spec = SPEC_BONUSES.get(defender.get("specialization", "none") or "none", {})
    def_power = (defender["defense_power"] + structure_def) * d_bonus["def_mult"] * (1 + def_spec.get("def_bonus", 0))
    # 陷阱效果
    trap_levels = sum(d["level"] for d in defense_structures if d["defense_type"] == "trap")
    trap_reduction = trap_levels * 0.10 * (1 + d_bonus.get("trap_bonus", 0))
    atk_power *= max(0.3, 1 - trap_reduction)
    # 随机因素
    atk_roll = atk_power * (1 + random.uniform(-0.15, 0.15))
    def_roll = def_power * (1 + random.uniform(-0.15, 0.15))
    # 复仇加成
    if is_revenge:
        atk_roll *= 1.2
    # 构建战斗阶段
    phases = []
    # 阶段1: 护盾
    if shield and shield.get("shield_charges", 0) > 0:
        phases.append({"phase": "shield", "desc": "护盾激活，但被突破！", "shield_charges_left": shield["shield_charges"] - 1})
    # 阶段2: 防御开火
    counter_dmg = 0
    for d in defense_structures:
        if d["defense_type"] in ("laser_turret", "autocannon", "missile_silo"):
            counter_dmg += d["level"] * DEFENSE_BUILDINGS[d["defense_type"]]["atk"]
    if counter_dmg > 0:
        atk_loss_pct = min(0.1, counter_dmg / max(1, atk_power) * 0.3)
        phases.append({"phase": "defense_fire", "desc": f"防御工事开火! 造成攻击方{int(atk_loss_pct*100)}%战力损失", "attacker_loss_pct": round(atk_loss_pct, 3)})
        atk_roll *= (1 - atk_loss_pct)
    # 阶段3: 主力碰撞
    phases.append({"phase": "clash", "attacker_roll": round(atk_roll, 1), "defender_roll": round(def_roll, 1),
                   "desc": f"{'复仇' if is_revenge else ''}主力碰撞! 攻{round(atk_roll,1)} vs 守{round(def_roll,1)}",
                   "formation_matchup": f"{f_bonus['name']} vs {d_bonus['name']}"})
    won = atk_roll > def_roll
    loot = {}
    loot_pct = 0
    if won:
        base_pct = random.randint(10, 20) + int(f_bonus.get("loot_bonus", 0) * 100)
        if is_revenge:
            base_pct = int(base_pct * 1.5)
        # 仓库保护
        wh_row = await db_one(cur, "SELECT level FROM buildings WHERE colony_id=%s AND building_type='wall'", (defender["id"],))
        wh_lvl = wh_row["level"] if wh_row else 0
        wh_protect = wh_lvl * 0.05 + d_bonus.get("warehouse_protect", 0)
        effective_pct = max(5, int(base_pct * (1 - wh_protect) * fatigue_penalty))
        loot_pct = effective_pct
        # 计算掠夺资源
        for res in ["minerals", "energy", "food", "rare_metals", "crystals", "plasma", "dark_matter"]:
            amt = int(defender.get(res, 0) * effective_pct / 100)
            if amt > 0:
                loot[res] = amt
        # 扣除防守方资源
        if loot:
            set_clauses = ", ".join(f"{r}=GREATEST(0,{r}-{v})" for r, v in loot.items())
            await db_exec(cur, f"UPDATE colonies SET {set_clauses} WHERE id=%s", (defender["id"],))
            add_clauses = ", ".join(f"{r}={r}+{v}" for r, v in loot.items())
            await db_exec(cur, f"UPDATE colonies SET {add_clauses}, score=score+10, win_count=win_count+1, xp=xp+5 WHERE id=%s", (attacker["id"],))
        else:
            await db_exec(cur, "UPDATE colonies SET score=score+10, win_count=win_count+1, xp=xp+5 WHERE id=%s", (attacker["id"],))
        await db_exec(cur, "UPDATE colonies SET lose_count=lose_count+1 WHERE id=%s", (defender["id"],))
        # 给防守方复仇令牌
        await db_exec(cur, "UPDATE colonies SET revenge_tokens=revenge_tokens+1 WHERE id=%s", (defender["id"],))
        # 给防守方2小时护盾
        await db_exec(cur, """INSERT INTO colony_shields (colony_id, shield_type, shield_until, shield_charges) VALUES (%s,'attack',DATE_ADD(NOW(),INTERVAL 2 HOUR),1)
            ON DUPLICATE KEY UPDATE shield_type='attack', shield_until=DATE_ADD(NOW(),INTERVAL 2 HOUR), shield_charges=1""", (defender["id"],))
        phases.append({"phase": "loot", "desc": f"掠夺{effective_pct}%资源!", "loot": loot})
    else:
        await db_exec(cur, "UPDATE colonies SET lose_count=lose_count+1 WHERE id=%s", (attacker["id"],))
        await db_exec(cur, "UPDATE colonies SET score=score+5, win_count=win_count+1 WHERE id=%s", (defender["id"],))
        phases.append({"phase": "defend", "desc": "攻击被击退!"})
    # 记录袭击
    await db_exec(cur, """INSERT INTO raids (attacker_id,defender_id,attacker_power,defender_power,formation,result,loot_json,loot_pct,is_revenge,revenge_from,fatigue_count,fatigue_penalty)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (attacker["id"], defender["id"], round(atk_roll), round(def_roll), formation,
         "win" if won else "lose", json.dumps(loot), loot_pct,
         1 if is_revenge else 0, revenge_raid_id, fatigue, fatigue_penalty))
    raid_id = cur.lastrowid
    # 记录战报
    await db_exec(cur, """INSERT INTO battle_reports (raid_id,attacker_id,defender_id,attacker_name,defender_name,report_type,
        attacker_power,defender_power,attacker_formation,defender_formation,battle_phases_json,result,loot_json)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (raid_id, attacker["id"], defender["id"], attacker["name"], defender["name"],
         "revenge" if is_revenge else "raid",
         round(atk_roll), round(def_roll), formation, def_formation,
         json.dumps(phases), "win" if won else "lose", json.dumps(loot)))
    # 通知双方
    if won:
        await add_notification(cur, defender["id"], "⚡ 被袭击!", f"被{attacker['name']}{('复仇' if is_revenge else '袭击')}，损失{loot_pct}%资源", "danger")
        await add_notification(cur, attacker["id"], "⚔️ 袭击成功!", f"成功{('复仇' if is_revenge else '袭击')}{defender['name']}，掠夺{loot_pct}%资源", "success")
    else:
        await add_notification(cur, defender["id"], "🛡️ 防御成功!", f"成功击退{attacker['name']}{('的复仇' if is_revenge else '的袭击')}!", "success")
        await add_notification(cur, attacker["id"], "💀 袭击失败", f"{('复仇' if is_revenge else '袭击')}{defender['name']}失败", "danger")
    # 检查派系战争积分
    await update_war_score(cur, attacker, defender, won, loot)
    return {"result": "win" if won else "lose", "raid_id": raid_id, "loot": loot, "loot_pct": loot_pct, "phases": phases, "fatigue": fatigue, "fatigue_penalty": fatigue_penalty}

async def update_war_score(cur, attacker, defender, attacker_won, loot):
    """更新派系战争积分"""
    atk_fac = await db_one(cur, "SELECT faction_id FROM colony_factions WHERE colony_id=%s", (attacker["id"],))
    def_fac = await db_one(cur, "SELECT faction_id FROM colony_factions WHERE colony_id=%s", (defender["id"],))
    if not atk_fac or not def_fac or atk_fac["faction_id"] == def_fac["faction_id"]:
        return
    wars = await db_query(cur, """SELECT * FROM faction_wars WHERE status='active' AND
        ((attacker_faction=%s AND defender_faction=%s) OR (attacker_faction=%s AND defender_faction=%s))""",
        (atk_fac["faction_id"], def_fac["faction_id"], def_fac["faction_id"], atk_fac["faction_id"]))
    for war in wars:
        score = 10 if attacker_won else 0
        if loot:
            loot_val = sum(loot.values())
            score += loot_val // 1000
        if war["attacker_faction"] == atk_fac["faction_id"]:
            await db_exec(cur, "UPDATE faction_wars SET attacker_score=attacker_score+%s WHERE id=%s", (score, war["id"]))
        else:
            await db_exec(cur, "UPDATE faction_wars SET defender_score=defender_score+%s WHERE id=%s", (score, war["id"]))

# ============ V8: 袭击API ============
@app.post("/api/raid/launch")
async def raid_launch(m: RaidModel, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            c = await db_one(cur, "SELECT * FROM colonies WHERE user_id=%s", (uid,))
            if not c: raise HTTPException(404, "殖民地不存在")
            t = await db_one(cur, "SELECT * FROM colonies WHERE id=%s AND id!=%s", (m.target_id, c["id"]))
            if not t: raise HTTPException(400, "目标不存在")
            # 冷却检查
            cd = await redis_client.get(f"raid_cd:{c['id']}")
            if cd: raise HTTPException(400, f"袭击冷却中，还需{cd}秒")
            # 检查是否对目标有赏金(额外加成)
            bounty_bonus = 0
            active_bounty = await db_one(cur, "SELECT SUM(amount) as total FROM bounties WHERE target_id=%s AND status='active'", (t["id"],))
            if active_bounty and active_bounty["total"]:
                bounty_bonus = 0.10
            result = await execute_raid(cur, c, t, m.formation)
            if result["result"] in ("win", "lose"):
                # 设置5分钟冷却
                await redis_client.setex(f"raid_cd:{c['id']}", 300, "300")
                await check_achievements(cur, c["id"], uid)
            return result

@app.post("/api/raid/revenge/{raid_id}")
async def raid_revenge(raid_id: int, m: RevengeModel, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            c = await db_one(cur, "SELECT * FROM colonies WHERE user_id=%s", (uid,))
            if not c: raise HTTPException(404, "殖民地不存在")
            if c.get("revenge_tokens", 0) <= 0:
                raise HTTPException(400, "没有复仇令牌")
            orig = await db_one(cur, "SELECT * FROM raids WHERE id=%s AND defender_id=%s AND result='win'", (raid_id, c["id"]))
            if not orig: raise HTTPException(400, "无效的复仇目标")
            attacker = await db_one(cur, "SELECT * FROM colonies WHERE id=%s", (orig["attacker_id"],))
            if not attacker: raise HTTPException(400, "目标已不存在")
            result = await execute_raid(cur, c, attacker, m.formation, is_revenge=True, revenge_raid_id=raid_id)
            if result["result"] in ("win", "lose"):
                await db_exec(cur, "UPDATE colonies SET revenge_tokens=GREATEST(0,revenge_tokens-1) WHERE id=%s", (c["id"],))
                await check_achievements(cur, c["id"], uid)
            return result

@app.get("/api/raid/targets")
async def raid_targets(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            c = await db_one(cur, "SELECT * FROM colonies WHERE user_id=%s", (uid,))
            targets = await db_query(cur, """SELECT c.id, c.name, c.level, c.attack_power, c.defense_power, c.score,
                u.username, cs.shield_type, cs.shield_until,
                (SELECT SUM(amount) FROM bounties WHERE target_id=c.id AND status='active') as bounty_amount
                FROM colonies c JOIN users u ON c.user_id=u.id
                LEFT JOIN colony_shields cs ON cs.colony_id=c.id
                WHERE c.id!=%s AND u.is_npc=0 ORDER BY c.score DESC LIMIT 30""", (c["id"],))
            now_row = await db_one(cur, "SELECT NOW() as now_ts")
            for t in targets:
                t["has_shield"] = bool(t.get("shield_type") and t["shield_type"] != "none" and t.get("shield_until") and t["shield_until"] > now_row["now_ts"])
                t["bounty_amount"] = t.get("bounty_amount") or 0
            return {"targets": targets, "my_power": c["attack_power"]}

@app.get("/api/raid/preview/{target_id}")
async def raid_preview(target_id: int, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            c = await db_one(cur, "SELECT * FROM colonies WHERE user_id=%s", (uid,))
            t = await db_one(cur, "SELECT * FROM colonies WHERE id=%s", (target_id,))
            if not t: raise HTTPException(404)
            ratio = c["attack_power"] / max(1, t["defense_power"])
            if ratio > 1.5: chance = "high"
            elif ratio > 0.8: chance = "medium"
            else: chance = "low"
            return {"my_atk": c["attack_power"], "target_def": t["defense_power"], "chance": chance, "ratio": round(ratio, 2)}

@app.get("/api/raid/history")
async def raid_history(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            c = await db_one(cur, "SELECT id FROM colonies WHERE user_id=%s", (uid,))
            raids = await db_query(cur, """SELECT r.*, a.name as attacker_name, d.name as defender_name
                FROM raids r JOIN colonies a ON r.attacker_id=a.id JOIN colonies d ON r.defender_id=d.id
                WHERE r.attacker_id=%s OR r.defender_id=%s ORDER BY r.created_at DESC LIMIT 20""", (c["id"], c["id"]))
            return {"raids": raids}

@app.get("/api/raid/fatigue")
async def raid_fatigue(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            c = await db_one(cur, "SELECT * FROM colonies WHERE user_id=%s", (uid,))
            week_raids = await db_one(cur, "SELECT COUNT(*) as cnt FROM raids WHERE attacker_id=%s AND created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)", (c["id"],))
            fatigue = week_raids["cnt"] if week_raids else 0
            penalty = max(0.5, 1.0 - max(0, fatigue - 3) * 0.15)
            cd = await redis_client.get(f"raid_cd:{c['id']}")
            return {"weekly_raids": fatigue, "fatigue_penalty": penalty, "cooldown_remaining": int(cd) if cd else 0, "revenge_tokens": c.get("revenge_tokens", 0)}

@app.post("/api/raid/shield/activate")
async def shield_activate(m: ShieldActivateModel, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            c = await db_one(cur, "SELECT * FROM colonies WHERE user_id=%s", (uid,))
            cost_dm = 100 if m.shield_type == "attack" else 200
            hours = 8 if m.shield_type == "attack" else 24
            if c.get("dark_matter", 0) < cost_dm:
                raise HTTPException(400, f"暗物质不足，需要{cost_dm}")
            await db_exec(cur, "UPDATE colonies SET dark_matter=dark_matter-%s WHERE id=%s", (cost_dm, c["id"]))
            charges = 2 if m.shield_type == "premium" else 1
            await db_exec(cur, """INSERT INTO colony_shields (colony_id, shield_type, shield_until, shield_charges)
                VALUES (%s,%s,DATE_ADD(NOW(),INTERVAL %s HOUR),%s)
                ON DUPLICATE KEY UPDATE shield_type=%s, shield_until=DATE_ADD(NOW(),INTERVAL %s HOUR), shield_charges=%s""",
                (c["id"], m.shield_type, hours, charges, m.shield_type, hours, charges))
            return {"msg": f"护盾激活{hours}小时!", "cost": cost_dm}

# ============ V8: 防御体系API ============
@app.get("/api/defenses")
async def get_defenses(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            c = await db_one(cur, "SELECT id FROM colonies WHERE user_id=%s", (uid,))
            defenses = await db_query(cur, "SELECT * FROM colony_defenses WHERE colony_id=%s", (c["id"],))
            formation = await db_one(cur, "SELECT formation FROM colony_defense_formation WHERE colony_id=%s", (c["id"],))
            shield = await db_one(cur, "SELECT * FROM colony_shields WHERE colony_id=%s", (c["id"],))
            return {"defenses": defenses, "formation": formation["formation"] if formation else "fortress",
                    "shield": shield, "defense_types": DEFENSE_BUILDINGS, "defense_formations": DEFENSE_FORMATIONS}

@app.post("/api/defenses/build")
async def build_defense(m: DefenseBuildModel, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            c = await db_one(cur, "SELECT * FROM colonies WHERE user_id=%s", (uid,))
            if m.defense_type not in DEFENSE_BUILDINGS: raise HTTPException(400, "未知防御类型")
            if m.slot < 0 or m.slot > 4: raise HTTPException(400, "槽位0-4")
            cfg = DEFENSE_BUILDINGS[m.defense_type]
            if c["minerals"] < cfg["cost_m"] or c["energy"] < cfg["cost_e"]:
                raise HTTPException(400, "资源不足")
            existing = await db_one(cur, "SELECT id FROM colony_defenses WHERE colony_id=%s AND slot=%s", (c["id"], m.slot))
            if existing: raise HTTPException(400, "该槽位已有防御工事")
            await db_exec(cur, "UPDATE colonies SET minerals=minerals-%s, energy=energy-%s WHERE id=%s", (cfg["cost_m"], cfg["cost_e"], c["id"]))
            await db_exec(cur, "INSERT INTO colony_defenses (colony_id,defense_type,slot,level,hp,max_hp) VALUES (%s,%s,%s,1,100,100)", (c["id"], m.defense_type, m.slot))
            await recalc_power(cur, c["id"])
            return {"msg": f"建造{cfg['name']}成功!"}

@app.post("/api/defenses/upgrade/{def_id}")
async def upgrade_defense(def_id: int, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            c = await db_one(cur, "SELECT * FROM colonies WHERE user_id=%s", (uid,))
            d = await db_one(cur, "SELECT * FROM colony_defenses WHERE id=%s AND colony_id=%s", (def_id, c["id"]))
            if not d: raise HTTPException(404, "防御工事不存在")
            cfg = DEFENSE_BUILDINGS.get(d["defense_type"], {})
            cost_m = int(cfg.get("cost_m", 30) * d["level"] * 1.5)
            cost_e = int(cfg.get("cost_e", 20) * d["level"] * 1.5)
            if c["minerals"] < cost_m or c["energy"] < cost_e:
                raise HTTPException(400, "资源不足")
            await db_exec(cur, "UPDATE colonies SET minerals=minerals-%s, energy=energy-%s WHERE id=%s", (cost_m, cost_e, c["id"]))
            new_hp = d["max_hp"] + 50
            await db_exec(cur, "UPDATE colony_defenses SET level=level+1, hp=%s, max_hp=%s WHERE id=%s", (new_hp, new_hp, def_id))
            await recalc_power(cur, c["id"])
            return {"msg": f"{cfg.get('name','防御工事')}升级到{d['level']+1}级!"}

@app.post("/api/defenses/repair/{def_id}")
async def repair_defense(def_id: int, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            c = await db_one(cur, "SELECT * FROM colonies WHERE user_id=%s", (uid,))
            d = await db_one(cur, "SELECT * FROM colony_defenses WHERE id=%s AND colony_id=%s", (def_id, c["id"]))
            if not d: raise HTTPException(404)
            if d["hp"] >= d["max_hp"]: raise HTTPException(400, "无需修复")
            cost_m = int(10 * d["level"])
            cost_e = int(5 * d["level"])
            if c["minerals"] < cost_m or c["energy"] < cost_e: raise HTTPException(400, "资源不足")
            await db_exec(cur, "UPDATE colonies SET minerals=minerals-%s, energy=energy-%s WHERE id=%s", (cost_m, cost_e, c["id"]))
            await db_exec(cur, "UPDATE colony_defenses SET hp=max_hp WHERE id=%s", (def_id,))
            return {"msg": "修复完成!"}

@app.post("/api/defenses/formation")
async def set_defense_formation(m: DefenseFormationModel, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            c = await db_one(cur, "SELECT id FROM colonies WHERE user_id=%s", (uid,))
            if m.formation not in DEFENSE_FORMATIONS: raise HTTPException(400, "无效阵型")
            await db_exec(cur, """INSERT INTO colony_defense_formation (colony_id, formation) VALUES (%s,%s)
                ON DUPLICATE KEY UPDATE formation=%s""", (c["id"], m.formation, m.formation))
            return {"msg": f"防御阵型设为{DEFENSE_FORMATIONS[m.formation]['name']}!"}

# ============ V8: 战报中心API ============
@app.get("/api/reports")
async def get_reports(page: int = 1, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            c = await db_one(cur, "SELECT id FROM colonies WHERE user_id=%s", (uid,))
            limit = 20
            offset = (page - 1) * limit
            reports = await db_query(cur, """SELECT * FROM battle_reports WHERE attacker_id=%s OR defender_id=%s
                ORDER BY created_at DESC LIMIT %s OFFSET %s""", (c["id"], c["id"], limit, offset))
            return {"reports": reports, "page": page}

@app.get("/api/reports/unread_count")
async def unread_count(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            c = await db_one(cur, "SELECT id FROM colonies WHERE user_id=%s", (uid,))
            cnt = await db_one(cur, "SELECT COUNT(*) as cnt FROM battle_reports WHERE (attacker_id=%s OR defender_id=%s) AND is_read=0", (c["id"], c["id"]))
            notif_cnt = await db_one(cur, "SELECT COUNT(*) as cnt FROM notifications WHERE colony_id=%s AND is_read=0", (c["id"],))
            return {"unread_reports": cnt["cnt"] if cnt else 0, "unread_notifications": notif_cnt["cnt"] if notif_cnt else 0}

@app.get("/api/reports/{report_id}")
async def get_report_detail(report_id: int, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            c = await db_one(cur, "SELECT id FROM colonies WHERE user_id=%s", (uid,))
            report = await db_one(cur, "SELECT * FROM battle_reports WHERE id=%s AND (attacker_id=%s OR defender_id=%s)", (report_id, c["id"], c["id"]))
            if not report: raise HTTPException(404)
            if not report["is_read"]:
                await db_exec(cur, "UPDATE battle_reports SET is_read=1 WHERE id=%s", (report_id,))
            return report

# ============ V8: 派系战争API ============
@app.post("/api/factions/{fid}/declare_war/{target_fid}")
async def declare_war(fid: int, target_fid: int, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            c = await db_one(cur, "SELECT * FROM colonies WHERE user_id=%s", (uid,))
            cf = await db_one(cur, "SELECT * FROM colony_factions WHERE colony_id=%s AND faction_id=%s AND role='leader'", (c["id"], fid))
            if not cf: raise HTTPException(403, "只有首领可以宣战")
            tf = await db_one(cur, "SELECT * FROM factions WHERE id=%s", (target_fid,))
            if not tf: raise HTTPException(404, "目标派系不存在")
            if fid == target_fid: raise HTTPException(400, "不能对自己宣战")
            existing = await db_one(cur, """SELECT * FROM faction_wars WHERE status='active' AND
                ((attacker_faction=%s AND defender_faction=%s) OR (attacker_faction=%s AND defender_faction=%s))""",
                (fid, target_fid, target_fid, fid))
            if existing: raise HTTPException(400, "已在交战中")
            await db_exec(cur, "INSERT INTO faction_wars (attacker_faction,defender_faction,war_type) VALUES (%s,%s,'declaration')", (fid, target_fid))
            # 更新外交关系
            await db_exec(cur, """INSERT INTO diplomacy (faction_a,faction_b,relation_type,proposed_by) VALUES (%s,%s,'war',%s)
                ON DUPLICATE KEY UPDATE relation_type='war'""", (fid, target_fid, c["id"]))
            # 通知双方成员
            members_a = await db_query(cur, "SELECT colony_id FROM colony_factions WHERE faction_id=%s", (fid,))
            members_b = await db_query(cur, "SELECT colony_id FROM colony_factions WHERE faction_id=%s", (target_fid,))
            for m in members_a:
                await add_notification(cur, m["colony_id"], "🏴 宣战!", f"派系已向{tf['name']}宣战!", "danger")
            for m in members_b:
                await add_notification(cur, m["colony_id"], "⚠️ 被宣战!", f"被{cf['faction_id']}号派系宣战!", "danger")
            # 战争影响股市 - 军工板块上涨
            await db_exec(cur, "UPDATE stocks SET change_pct=change_pct+ROUND(RAND()*5+3,2) WHERE sector='军工' AND is_active=1")
            return {"msg": f"宣战成功! 战争已经开始!"}

@app.post("/api/factions/{fid}/propose_peace/{target_fid}")
async def propose_peace(fid: int, target_fid: int, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            c = await db_one(cur, "SELECT * FROM colonies WHERE user_id=%s", (uid,))
            cf = await db_one(cur, "SELECT * FROM colony_factions WHERE colony_id=%s AND faction_id=%s AND role='leader'", (c["id"], fid))
            if not cf: raise HTTPException(403, "只有首领可以求和")
            war = await db_one(cur, """SELECT * FROM faction_wars WHERE status='active' AND
                ((attacker_faction=%s AND defender_faction=%s) OR (attacker_faction=%s AND defender_faction=%s))""",
                (fid, target_fid, target_fid, fid))
            if not war: raise HTTPException(400, "未在交战中")
            await db_exec(cur, "UPDATE faction_wars SET status='ceasefire' WHERE id=%s", (war["id"],))
            await db_exec(cur, """INSERT INTO diplomacy (faction_a,faction_b,relation_type,proposed_by) VALUES (%s,%s,'ceasefire',%s)
                ON DUPLICATE KEY UPDATE relation_type='ceasefire'""", (fid, target_fid, c["id"]))
            return {"msg": "求和提议已发送!"}

@app.post("/api/factions/{fid}/alliance/{target_fid}")
async def form_alliance(fid: int, target_fid: int, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            c = await db_one(cur, "SELECT * FROM colonies WHERE user_id=%s", (uid,))
            cf = await db_one(cur, "SELECT * FROM colony_factions WHERE colony_id=%s AND faction_id=%s AND role='leader'", (c["id"], fid))
            if not cf: raise HTTPException(403, "只有首领可以结盟")
            await db_exec(cur, """INSERT INTO diplomacy (faction_a,faction_b,relation_type,proposed_by) VALUES (%s,%s,'alliance',%s)
                ON DUPLICATE KEY UPDATE relation_type='alliance'""", (fid, target_fid, c["id"]))
            return {"msg": "结盟成功!"}

@app.get("/api/wars/active")
async def active_wars(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            wars = await db_query(cur, """SELECT w.*, fa.name as attacker_name, fd.name as defender_name
                FROM faction_wars w JOIN factions fa ON w.attacker_faction=fa.id JOIN factions fd ON w.defender_faction=fd.id
                WHERE w.status='active' ORDER BY w.started_at DESC""")
            return {"wars": wars}

@app.get("/api/wars/{war_id}")
async def war_detail(war_id: int, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            war = await db_one(cur, """SELECT w.*, fa.name as attacker_name, fd.name as defender_name
                FROM faction_wars w JOIN factions fa ON w.attacker_faction=fa.id JOIN factions fd ON w.defender_faction=fd.id
                WHERE w.id=%s""", (war_id,))
            if not war: raise HTTPException(404)
            return war

# ============ V8: 赏金系统API ============
@app.post("/api/bounty/place")
async def place_bounty(m: BountyPlaceModel, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            c = await db_one(cur, "SELECT * FROM colonies WHERE user_id=%s", (uid,))
            if m.amount < 500: raise HTTPException(400, "最低悬赏500金")
            if c["gold"] < m.amount: raise HTTPException(400, "金币不足")
            t = await db_one(cur, "SELECT * FROM colonies WHERE id=%s", (m.target_id,))
            if not t: raise HTTPException(404, "目标不存在")
            if t["level"] < 4: raise HTTPException(400, "新手不可被悬赏")
            await db_exec(cur, "UPDATE colonies SET gold=gold-%s WHERE id=%s", (m.amount, c["id"]))
            await db_exec(cur, """INSERT INTO bounties (target_id,placer_id,amount,reason,expires_at)
                VALUES (%s,%s,%s,%s,DATE_ADD(NOW(),INTERVAL 7 DAY))""",
                (m.target_id, c["id"], m.amount, m.reason))
            await add_notification(cur, m.target_id, "💀 被悬赏!", f"你被{c['name']}悬赏了{m.amount}金币!", "danger")
            return {"msg": f"悬赏{m.amount}金币成功!"}

@app.get("/api/bounty/board")
async def bounty_board(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            bounties = await db_query(cur, """SELECT b.*, t.name as target_name, p.name as placer_name
                FROM bounties b JOIN colonies t ON b.target_id=t.id JOIN colonies p ON b.placer_id=p.id
                WHERE b.status='active' ORDER BY b.amount DESC LIMIT 30""")
            return {"bounties": bounties}

@app.get("/api/bounty/board")
async def bounty_board(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            bounties = await db_query(cur, """SELECT b.*, c.name as target_name, p.name as placer_name
                FROM bounties b JOIN colonies c ON b.target_id=c.id LEFT JOIN colonies p ON b.placer_id=p.id
                WHERE b.status='active' ORDER BY b.amount DESC LIMIT 30""")
            return {"bounties": bounties}

@app.get("/api/bounty/my")
async def my_bounties(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            c = await db_one(cur, "SELECT id FROM colonies WHERE user_id=%s", (uid,))
            placed = await db_query(cur, """SELECT b.*, c.name as target_name FROM bounties b JOIN colonies c ON b.target_id=c.id
                WHERE b.placer_id=%s ORDER BY b.created_at DESC""", (c["id"],))
            on_me = await db_query(cur, """SELECT b.*, c.name as placer_name FROM bounties b JOIN colonies c ON b.placer_id=c.id
                WHERE b.target_id=%s AND b.status='active' ORDER BY b.amount DESC""", (c["id"],))
            return {"placed": placed, "on_me": on_me}

@app.post("/api/bounty/escalate/{bounty_id}")
async def escalate_bounty(bounty_id: int, m: BountyEscalateModel, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            c = await db_one(cur, "SELECT * FROM colonies WHERE user_id=%s", (uid,))
            b = await db_one(cur, "SELECT * FROM bounties WHERE id=%s AND status='active'", (bounty_id,))
            if not b: raise HTTPException(404)
            if m.additional_amount < 200: raise HTTPException(400, "最低追加200金")
            if c["gold"] < m.additional_amount: raise HTTPException(400, "金币不足")
            await db_exec(cur, "UPDATE colonies SET gold=gold-%s WHERE id=%s", (m.additional_amount, c["id"]))
            await db_exec(cur, "UPDATE bounties SET amount=amount+%s, escalation=escalation+1 WHERE id=%s", (m.additional_amount, bounty_id))
            return {"msg": f"追加{m.additional_amount}金币成功!"}

# ============ V8: 竞技场API ============
@app.get("/api/arena/tournaments")
async def arena_tournaments(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            tournaments = await db_query(cur, "SELECT * FROM arena_tournaments WHERE status IN ('upcoming','active') ORDER BY created_at DESC LIMIT 10")
            return {"tournaments": tournaments}

@app.post("/api/arena/register/{tid}")
async def arena_register(tid: int, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            c = await db_one(cur, "SELECT * FROM colonies WHERE user_id=%s", (uid,))
            t = await db_one(cur, "SELECT * FROM arena_tournaments WHERE id=%s", (tid,))
            if not t: raise HTTPException(404)
            if t["status"] != "upcoming": raise HTTPException(400, "赛事已开始")
            if c["gold"] < t["entry_fee"]: raise HTTPException(400, "金币不足")
            existing = await db_one(cur, "SELECT id FROM arena_participants WHERE tournament_id=%s AND colony_id=%s", (tid, c["id"]))
            if existing: raise HTTPException(400, "已报名")
            cnt = await db_one(cur, "SELECT COUNT(*) as cnt FROM arena_participants WHERE tournament_id=%s", (tid,))
            if cnt["cnt"] >= t["max_participants"]: raise HTTPException(400, "名额已满")
            await db_exec(cur, "UPDATE colonies SET gold=gold-%s WHERE id=%s", (t["entry_fee"], c["id"]))
            await db_exec(cur, "INSERT INTO arena_participants (tournament_id,colony_id,bracket_pos) VALUES (%s,%s,%s)",
                (tid, c["id"], cnt["cnt"]))
            await db_exec(cur, "UPDATE arena_tournaments SET prize_pool=prize_pool+%s WHERE id=%s", (int(t["entry_fee"] * 0.7), tid))
            return {"msg": "报名成功!"}

@app.get("/api/arena/bracket/{tid}")
async def arena_bracket(tid: int, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            participants = await db_query(cur, """SELECT ap.*, c.name, c.attack_power, c.defense_power, c.arena_rating
                FROM arena_participants ap JOIN colonies c ON ap.colony_id=c.id WHERE ap.tournament_id=%s ORDER BY ap.bracket_pos""", (tid,))
            matches = await db_query(cur, """SELECT am.*, ca.name as colony_a_name, cb.name as colony_b_name
                FROM arena_matches am LEFT JOIN colonies ca ON am.colony_a=ca.id LEFT JOIN colonies cb ON am.colony_b=cb.id
                WHERE am.tournament_id=%s ORDER BY am.round_num""", (tid,))
            return {"participants": participants, "matches": matches}

@app.get("/api/arena/rankings")
async def arena_rankings(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            rankings = await db_query(cur, """SELECT c.id, c.name, c.arena_rating, u.username
                FROM colonies c JOIN users u ON c.user_id=u.id WHERE u.is_npc=0 ORDER BY c.arena_rating DESC LIMIT 30""")
            for r in rankings:
                r["title"] = get_arena_title(r.get("arena_rating", 1000))
            return {"rankings": rankings}

# ============ V8: 间谍系统API ============
@app.post("/api/espionage/launch")
async def espionage_launch(m: EspionageLaunchModel, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            c = await db_one(cur, "SELECT * FROM colonies WHERE user_id=%s", (uid,))
            t = await db_one(cur, "SELECT * FROM colonies WHERE id=%s", (m.target_id,))
            if not t: raise HTTPException(404, "目标不存在")
            if m.op_type not in ESPIONAGE_CONFIG: raise HTTPException(400, "无效间谍行动")
            cfg = ESPIONAGE_CONFIG[m.op_type]
            # 频率限制
            spy_count = await db_one(cur, "SELECT COUNT(*) as cnt FROM espionage_ops WHERE spy_id=%s AND created_at >= DATE_SUB(NOW(),INTERVAL 6 HOUR)", (c["id"],))
            if spy_count["cnt"] >= 3: raise HTTPException(400, "间谍行动冷却中(6小时3次)")
            if c["gold"] < cfg["cost_gold"]: raise HTTPException(400, "金币不足")
            if c.get("dark_matter", 0) < cfg["cost_dm"]: raise HTTPException(400, "暗物质不足")
            await db_exec(cur, "UPDATE colonies SET gold=gold-%s, dark_matter=dark_matter-%s WHERE id=%s",
                (cfg["cost_gold"], cfg["cost_dm"], c["id"]))
            # 计算成功率
            spy_def = t.get("spy_defense", 0) or 0
            success_rate = cfg["base_rate"] * (1 - spy_def / 100)
            spec = SPEC_BONUSES.get(c.get("specialization", "none") or "none", {})
            if spec.get("atk_bonus", 0) > 0:
                success_rate *= 1.10
            success_rate = min(0.95, max(0.05, success_rate))
            roll = random.random()
            intel_json = None
            damage_json = None
            if roll < success_rate:
                result = "success"
                if m.op_type == "recon":
                    intel_json = json.dumps({r: t.get(r, 0) for r in ["minerals","energy","food","gold","attack_power","defense_power","rare_metals","dark_matter"]})
                elif m.op_type == "sabotage":
                    bld = await db_query(cur, "SELECT * FROM buildings WHERE colony_id=%s ORDER BY RAND() LIMIT 1", (t["id"],))
                    if bld and bld[0]["level"] > 1:
                        await db_exec(cur, "UPDATE buildings SET level=level-1 WHERE id=%s", (bld[0]["id"],))
                        await recalc_power(cur, t["id"])
                        damage_json = json.dumps({"building": bld[0]["building_type"], "levels_lost": 1})
                    else:
                        damage_json = json.dumps({"building": "none", "msg": "目标无建筑可破坏"})
                elif m.op_type == "steal":
                    steal_res = random.choice(["minerals","energy","food","gold"])
                    steal_amt = int(t.get(steal_res, 0) * 0.05)
                    if steal_amt > 0:
                        await db_exec(cur, f"UPDATE colonies SET {steal_res}=GREATEST(0,{steal_res}-{steal_amt}) WHERE id=%s", (t["id"],))
                        await db_exec(cur, f"UPDATE colonies SET {steal_res}={steal_res}+{steal_amt} WHERE id=%s", (c["id"],))
                        damage_json = json.dumps({"resource": steal_res, "amount": steal_amt})
                    else:
                        damage_json = json.dumps({"resource": steal_res, "amount": 0})
                elif m.op_type == "counter_intel":
                    await db_exec(cur, "UPDATE colonies SET spy_defense=LEAST(100,spy_defense+20) WHERE id=%s", (c["id"],))
                    intel_json = json.dumps({"new_spy_defense": min(100, (c.get("spy_defense", 0) or 0) + 20)})
                await add_notification(cur, c["id"], "🕵️ 间谍成功!", f"对{t['name']}执行{cfg['name']}成功!", "success")
            else:
                result = "caught" if roll > success_rate + 0.2 else "failed"
                if result == "caught":
                    await add_notification(cur, t["id"], "🚨 抓获间谍!", f"抓获来自{c['name']}的间谍!", "success")
                await add_notification(cur, c["id"], "❌ 间谍失败", f"对{t['name']}执行{cfg['name']}失败", "danger")
            await db_exec(cur, """INSERT INTO espionage_ops (spy_id,target_id,op_type,success_rate,result,intel_json,damage_json,cost_gold)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (c["id"], t["id"], m.op_type, round(success_rate, 2), result, intel_json, damage_json, cfg["cost_gold"]))
            await check_achievements(cur, c["id"], uid)
            return {"result": result, "success_rate": round(success_rate, 2), "intel": json.loads(intel_json) if intel_json else None,
                    "damage": json.loads(damage_json) if damage_json else None}

@app.get("/api/espionage/history")
async def espionage_history(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            c = await db_one(cur, "SELECT id, spy_defense FROM colonies WHERE user_id=%s", (uid,))
            ops = await db_query(cur, """SELECT e.*, c.name as target_name FROM espionage_ops e JOIN colonies c ON e.target_id=c.id
                WHERE e.spy_id=%s ORDER BY e.created_at DESC LIMIT 20""", (c["id"],))
            return {"ops": ops, "my_spy_defense": c.get("spy_defense", 0) or 0}

# ============================================================
#  A股风格股票系统（V7增强：涨跌停/交易量追踪）
# ============================================================
@app.get("/api/stocks/list")
async def stock_list(sector: str = None, sort: str = "code", uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            sql = "SELECT * FROM stocks WHERE is_active=1"
            args = []
            if sector:
                sql += " AND sector=%s"; args.append(sector)
            if sort == "change": sql += " ORDER BY change_pct DESC"
            elif sort == "volume": sql += " ORDER BY volume DESC"
            elif sort == "name": sql += " ORDER BY name"
            else: sql += " ORDER BY code"
            stocks = await db_query(cur, sql, args if args else None)
            cid = await get_colony_id(cur, uid)
            wl = set()
            if cid:
                for w in await db_query(cur, "SELECT stock_code FROM stock_watchlist WHERE colony_id=%s", (cid,)):
                    wl.add(w["stock_code"])
            for s in stocks:
                s["is_watchlisted"] = s["code"] in wl
                s["current_price"] = float(s["current_price"])
                s["change_pct"] = float(s["change_pct"])
                # V7: 涨跌停状态
                prev_close = float(s["prev_close"])
                limit_up = round(prev_close * 1.1, 2)
                limit_down = round(prev_close * 0.9, 2)
                s["limit_up"] = limit_up
                s["limit_down"] = limit_down
                s["is_limit_up"] = s["current_price"] >= limit_up
                s["is_limit_down"] = s["current_price"] <= limit_down
            return {"stocks": stocks}

@app.get("/api/stocks/detail/{code}")
async def stock_detail(code: str, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            stock = await db_one(cur, "SELECT * FROM stocks WHERE code=%s", (code,))
            if not stock: raise HTTPException(404, "股票不存在")
            stock["current_price"] = float(stock["current_price"])
            stock["change_pct"] = float(stock["change_pct"])
            # V7: 涨跌停信息
            prev_close = float(stock["prev_close"])
            stock["limit_up"] = round(prev_close * 1.1, 2)
            stock["limit_down"] = round(prev_close * 0.9, 2)
            stock["is_limit_up"] = stock["current_price"] >= stock["limit_up"]
            stock["is_limit_down"] = stock["current_price"] <= stock["limit_down"]
            ob = await db_query(cur, "SELECT * FROM stock_orderbook WHERE stock_code=%s ORDER BY direction, price_level", (code,))
            buys = [o for o in ob if o["direction"]=="buy"]
            sells = [o for o in ob if o["direction"]=="sell"]
            trades = await db_query(cur, "SELECT * FROM stock_trades WHERE stock_code=%s ORDER BY created_at DESC LIMIT 30", (code,))
            klines = await db_query(cur, "SELECT * FROM stock_klines WHERE stock_code=%s ORDER BY k_date DESC LIMIT 90", (code,))
            klines.reverse()
            for k in klines:
                for f in ("open_price","high_price","low_price","close_price","change_pct"):
                    k[f] = float(k[f])
            cid = await get_colony_id(cur, uid)
            my_pos = await db_one(cur, "SELECT * FROM stock_portfolios WHERE colony_id=%s AND stock_code=%s AND amount>0", (cid, code))
            return {"stock": stock, "buy_orders": buys, "sell_orders": sells, "recent_trades": trades, "klines": klines, "my_position": my_pos}

@app.post("/api/stocks/trade")
async def stock_trade(m: StockTradeModel, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            stock = await db_one(cur, "SELECT * FROM stocks WHERE code=%s AND is_active=1", (m.code,))
            if not stock: raise HTTPException(404, "股票不存在")
            trade_price = m.price if m.price else float(stock["current_price"])
            total = round(trade_price * m.amount, 2)
            commission = round(total * 0.001, 2)
            cid = await get_colony_id(cur, uid)
            c = await db_one(cur, "SELECT gold FROM colonies WHERE id=%s", (cid,))

            # V7: 涨跌停检查
            prev_close = float(stock["prev_close"])
            limit_up = round(prev_close * 1.1, 2)
            limit_down = round(prev_close * 0.9, 2)
            current_price = float(stock["current_price"])

            if m.direction == "buy":
                if current_price >= limit_up:
                    raise HTTPException(400, "该股已涨停，无法买入")
                if c["gold"] < total + commission:
                    raise HTTPException(400, f"金币不足（需{total+commission:.0f}）")
                await db_exec(cur, "UPDATE colonies SET gold=gold-%s WHERE id=%s", (total+commission, cid))
                await db_exec(cur, """INSERT INTO stock_portfolios (colony_id,stock_code,amount,total_cost,avg_cost)
                    VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE amount=amount+%s, total_cost=total_cost+%s, avg_cost=(total_cost+%s)/(amount+%s)""",
                    (cid, m.code, m.amount, total, trade_price, m.amount, total, total, m.amount))
                # V7: 追踪买入量
                await db_exec(cur, "UPDATE stocks SET daily_buy_vol=daily_buy_vol+%s, daily_buy_amount=daily_buy_amount+%s, volume=volume+%s, turnover=turnover+%s WHERE code=%s",
                    (m.amount, total, m.amount, total, m.code))
            else:
                if current_price <= limit_down:
                    raise HTTPException(400, "该股已跌停，无法卖出")
                port = await db_one(cur, "SELECT * FROM stock_portfolios WHERE colony_id=%s AND stock_code=%s", (cid, m.code))
                if not port or port["amount"] < m.amount:
                    raise HTTPException(400, "持仓不足")
                await db_exec(cur, "UPDATE colonies SET gold=gold+%s WHERE id=%s", (total-commission, cid))
                await db_exec(cur, "UPDATE stock_portfolios SET amount=amount-%s, total_cost=GREATEST(total_cost-%s,0) WHERE colony_id=%s AND stock_code=%s",
                    (m.amount, round(float(port["avg_cost"])*m.amount,2), cid, m.code))
                if port["amount"] == m.amount:
                    await db_exec(cur, "DELETE FROM stock_portfolios WHERE colony_id=%s AND stock_code=%s AND amount<=0", (cid, m.code))
                # V7: 追踪卖出量
                await db_exec(cur, "UPDATE stocks SET daily_sell_vol=daily_sell_vol+%s, daily_sell_amount=daily_sell_amount+%s, volume=volume+%s, turnover=turnover+%s WHERE code=%s",
                    (m.amount, total, m.amount, total, m.code))

            await db_exec(cur, "INSERT INTO stock_trades (colony_id,stock_code,direction,price,amount,total_gold,commission) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (cid, m.code, m.direction, trade_price, m.amount, total, commission))
            await check_achievements(cur, cid, uid)
            await update_daily_task_progress(cur, cid, "stock_buy" if m.direction=="buy" else "trade_1")
            return {"msg": f"{'买入' if m.direction=='buy' else '卖出'}{stock['name']} {m.amount}股 @{trade_price:.2f}", "total": total, "commission": commission}

@app.get("/api/stocks/trade_preview")
async def stock_trade_preview(code: str, direction: str, amount: int, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            stock = await db_one(cur, "SELECT * FROM stocks WHERE code=%s", (code,))
            if not stock: raise HTTPException(404, "股票不存在")
            price = float(stock["current_price"])
            total = round(price * amount, 2)
            commission = round(total * 0.001, 2)
            cid = await get_colony_id(cur, uid)
            c = await db_one(cur, "SELECT gold FROM colonies WHERE id=%s", (cid,))
            can_afford = c["gold"] >= total + commission if direction == "buy" else True
            my_pos = await db_one(cur, "SELECT amount FROM stock_portfolios WHERE colony_id=%s AND stock_code=%s AND amount>0", (cid, code))
            pos_amount = my_pos["amount"] if my_pos else 0
            max_buy = int(c["gold"] / (price * 1.001)) if price > 0 else 0
            # V7: 涨跌停状态
            prev_close = float(stock["prev_close"])
            limit_up = round(prev_close * 1.1, 2)
            limit_down = round(prev_close * 0.9, 2)
            is_limit_up = price >= limit_up
            is_limit_down = price <= limit_down
            return {"code": code, "name": stock["name"], "price": price, "amount": amount, "total": total,
                    "commission": commission, "grand_total": total + commission if direction=="buy" else total - commission,
                    "can_afford": can_afford, "gold": c["gold"], "pos_amount": pos_amount, "max_buy": max_buy,
                    "limit_up": limit_up, "limit_down": limit_down, "is_limit_up": is_limit_up, "is_limit_down": is_limit_down}

@app.get("/api/stocks/portfolio")
async def get_portfolio(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            cid = await get_colony_id(cur, uid)
            ports = await db_query(cur, """SELECT sp.*, s.name, s.current_price, s.change_pct, s.sector
                FROM stock_portfolios sp JOIN stocks s ON sp.stock_code=s.code WHERE sp.colony_id=%s AND sp.amount>0""", (cid,))
            tv = tc = 0
            for p in ports:
                cv = float(p["current_price"]) * p["amount"]
                p["current_value"] = round(cv, 2)
                p["profit_loss"] = round(cv - float(p["total_cost"]), 2)
                p["profit_pct"] = round((cv/float(p["total_cost"])-1)*100, 2) if float(p["total_cost"])>0 else 0
                tv += cv; tc += float(p["total_cost"])
            return {"positions": ports, "total_value": round(tv,2), "total_cost": round(tc,2), "total_pnl": round(tv-tc,2)}

@app.post("/api/stocks/watchlist")
async def manage_watchlist(code: str, action: str = "add", uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            cid = await get_colony_id(cur, uid)
            if action == "add":
                await db_exec(cur, "INSERT IGNORE INTO stock_watchlist (colony_id,stock_code) VALUES (%s,%s)", (cid, code))
            else:
                await db_exec(cur, "DELETE FROM stock_watchlist WHERE colony_id=%s AND stock_code=%s", (cid, code))
            return {"msg": "已" + ("添加" if action=="add" else "移除")}

@app.get("/api/stocks/watchlist")
async def get_watchlist(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            cid = await get_colony_id(cur, uid)
            rows = await db_query(cur, """SELECT sw.stock_code as code, s.name, s.current_price, s.change_pct, s.sector
                FROM stock_watchlist sw JOIN stocks s ON sw.stock_code=s.code WHERE sw.colony_id=%s""", (cid,))
            return {"watchlist": rows}

# V7: IPO日历
@app.get("/api/stocks/ipo_calendar")
async def ipo_calendar(page: int = 1, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            off = (page - 1) * 20
            logs = await db_query(cur, "SELECT * FROM stock_ipo_log ORDER BY created_at DESC LIMIT 20 OFFSET %s", (off,))
            total = await db_one(cur, "SELECT COUNT(*) as cnt FROM stock_ipo_log")
            return {"ipos": logs, "total": total["cnt"] if total else 0}

# 股票期货
@app.post("/api/stocks/futures/open")
async def open_stock_future(m: StockFutureModel, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            stock = await db_one(cur, "SELECT current_price FROM stocks WHERE code=%s", (m.code,))
            if not stock: raise HTTPException(404, "股票不存在")
            price = float(stock["current_price"])
            total = price * m.amount
            margin = round(total / m.leverage, 2)
            cid = await get_colony_id(cur, uid)
            c = await db_one(cur, "SELECT gold FROM colonies WHERE id=%s", (cid,))
            if c["gold"] < margin: raise HTTPException(400, f"保证金不足（需{margin:.0f}）")
            await db_exec(cur, "UPDATE colonies SET gold=gold-%s WHERE id=%s", (margin, cid))
            await db_exec(cur, "INSERT INTO stock_futures (colony_id,stock_code,direction,amount,entry_price,leverage,margin) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (cid, m.code, m.direction, m.amount, price, m.leverage, margin))
            return {"msg": f"开仓{m.direction} {m.code} {m.amount}股 {m.leverage}x", "margin": margin}

@app.get("/api/stocks/futures/positions")
async def get_stock_futures(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            cid = await get_colony_id(cur, uid)
            rows = await db_query(cur, """SELECT sf.*, s.name, s.current_price FROM stock_futures sf JOIN stocks s ON sf.stock_code=s.code
                WHERE sf.colony_id=%s AND sf.status='open'""", (cid,))
            for r in rows:
                ep = float(r["entry_price"]); cp = float(r["current_price"])
                pnl = (cp-ep)*r["amount"] if r["direction"]=="long" else (ep-cp)*r["amount"]
                r["unrealized_pnl"] = round(pnl*r["leverage"], 2)
            return {"positions": rows}

@app.post("/api/stocks/futures/close/{fid}")
async def close_stock_future(fid: int, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            cid = await get_colony_id(cur, uid)
            cf = await db_one(cur, "SELECT * FROM stock_futures WHERE id=%s AND colony_id=%s AND status='open'", (fid, cid))
            if not cf: raise HTTPException(404, "合约不存在")
            stock = await db_one(cur, "SELECT current_price FROM stocks WHERE code=%s", (cf["stock_code"],))
            cp = float(stock["current_price"]); ep = float(cf["entry_price"])
            pnl = (cp-ep)*cf["amount"] if cf["direction"]=="long" else (ep-cp)*cf["amount"]
            pnl = round(pnl*cf["leverage"], 2)
            settlement = round(float(cf["margin"]) + pnl, 2)
            await db_exec(cur, "UPDATE colonies SET gold=gold+%s WHERE id=%s", (max(settlement,0), cid))
            await db_exec(cur, "UPDATE stock_futures SET status='closed',profit_loss=%s,closed_at=NOW() WHERE id=%s", (pnl, fid))
            return {"msg": f"平仓盈亏: {pnl:.2f}金币", "pnl": pnl}

# ============================================================
#  资源市场
# ============================================================
@app.get("/api/market/prices")
async def market_prices(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            prices = await db_query(cur, "SELECT * FROM resource_prices")
            for p in prices:
                p["display_name"] = RESOURCE_MAP.get(p["resource_type"], {}).get("name", p["resource_type"])
            trades = await db_query(cur, "SELECT * FROM trade_history ORDER BY created_at DESC LIMIT 20")
            for t in trades:
                t["display_name"] = RESOURCE_MAP.get(t["resource_type"], {}).get("name", t["resource_type"])
            return {"prices": prices, "recent_trades": trades, "maker": {"name":"星际联邦储备银行","balance":sum(p["maker_balance"] for p in prices)}}

@app.post("/api/market/trade")
async def market_trade(m: TradeModel, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            rp = await db_one(cur, "SELECT * FROM resource_prices WHERE resource_type=%s", (m.resource_type,))
            if not rp: raise HTTPException(400, "未知资源")
            cid = await get_colony_id(cur, uid)
            c = await db_one(cur, "SELECT * FROM colonies WHERE id=%s", (cid,))
            price = rp["current_price"]; total = price * m.amount
            basic_resources = {"minerals":"minerals","energy":"energy","food":"food"}
            rc = basic_resources.get(m.resource_type)
            if m.trade_type == "buy":
                if c["gold"] < total: raise HTTPException(400, "金币不足")
                if rc:
                    await db_exec(cur, f"UPDATE colonies SET gold=gold-%s,{rc}={rc}+%s WHERE id=%s", (total, m.amount, cid))
                else:
                    await db_exec(cur, "UPDATE colonies SET gold=gold-%s WHERE id=%s", (total, cid))
                await db_exec(cur, "UPDATE resource_prices SET maker_balance=maker_balance+%s,total_volume=total_volume+%s WHERE resource_type=%s", (total, m.amount, m.resource_type))
            else:
                if rc:
                    if c[rc] < m.amount: raise HTTPException(400, f"{m.resource_type}不足")
                    await db_exec(cur, f"UPDATE colonies SET gold=gold+%s,{rc}={rc}-%s WHERE id=%s", (total, m.amount, cid))
                else:
                    await db_exec(cur, "UPDATE colonies SET gold=gold+%s WHERE id=%s", (total, cid))
                await db_exec(cur, "UPDATE resource_prices SET maker_balance=maker_balance-%s,total_volume=total_volume+%s WHERE resource_type=%s", (total, m.amount, m.resource_type))
            res_name = RESOURCE_MAP.get(m.resource_type, {}).get("name", m.resource_type)
            await db_exec(cur, "INSERT INTO trade_history (buyer_id,resource_type,amount,unit_price,total_gold) VALUES (%s,%s,%s,%s,%s)", (cid, m.resource_type, m.amount, price, total))
            await check_achievements(cur, cid, uid)
            await update_daily_task_progress(cur, cid, "trade_1")
            return {"msg": f"{'买入' if m.trade_type=='buy' else '卖出'}{m.amount}{res_name} @{price} = {total}金币"}

# 资源期货
@app.post("/api/futures/open")
async def open_future(m: FuturesModel, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            rp = await db_one(cur, "SELECT current_price FROM resource_prices WHERE resource_type=%s", (m.resource_type,))
            if not rp: raise HTTPException(400, "未知资源")
            margin = int(m.amount * rp["current_price"] / m.leverage)
            cid = await get_colony_id(cur, uid)
            c = await db_one(cur, "SELECT gold FROM colonies WHERE id=%s", (cid,))
            if c["gold"] < margin: raise HTTPException(400, f"保证金不足（需{margin}）")
            await db_exec(cur, "UPDATE colonies SET gold=gold-%s WHERE id=%s", (margin, cid))
            await db_exec(cur, "INSERT INTO futures_contracts (colony_id,resource_type,direction,amount,entry_price,leverage,margin) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (cid, m.resource_type, m.direction, m.amount, rp["current_price"], m.leverage, margin))
            return {"msg": "开仓成功", "margin": margin}

@app.get("/api/futures/positions")
async def get_futures(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            cid = await get_colony_id(cur, uid)
            rows = await db_query(cur, """SELECT fc.*, rp.current_price FROM futures_contracts fc
                JOIN resource_prices rp ON fc.resource_type=rp.resource_type WHERE fc.colony_id=%s AND fc.status='open'""", (cid,))
            for r in rows:
                pnl = (r["current_price"]-r["entry_price"])*r["amount"] if r["direction"]=="long" else (r["entry_price"]-r["current_price"])*r["amount"]
                r["unrealized_pnl"] = int(pnl*r["leverage"])
                r["display_name"] = RESOURCE_MAP.get(r["resource_type"], {}).get("name", r["resource_type"])
            return {"positions": rows}

@app.post("/api/futures/close/{fid}")
async def close_future(fid: int, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            cid = await get_colony_id(cur, uid)
            cf = await db_one(cur, "SELECT * FROM futures_contracts WHERE id=%s AND colony_id=%s AND status='open'", (fid, cid))
            if not cf: raise HTTPException(404, "合约不存在")
            rp = await db_one(cur, "SELECT current_price FROM resource_prices WHERE resource_type=%s", (cf["resource_type"],))
            pnl = (rp["current_price"]-cf["entry_price"])*cf["amount"] if cf["direction"]=="long" else (cf["entry_price"]-rp["current_price"])*cf["amount"]
            pnl = int(pnl*cf["leverage"])
            await db_exec(cur, "UPDATE colonies SET gold=gold+%s WHERE id=%s", (cf["margin"]+pnl, cid))
            await db_exec(cur, "UPDATE futures_contracts SET status='closed',profit_loss=%s,closed_at=NOW() WHERE id=%s", (pnl, fid))
            return {"msg": f"平仓盈亏: {pnl}金币", "pnl": pnl}

# ============================================================
#  论坛
# ============================================================
@app.get("/api/forum/posts")
async def forum_posts(category: str = "general", page: int = 1, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            off = (page-1)*20
            posts = await db_query(cur, "SELECT * FROM forum_posts WHERE category=%s ORDER BY is_pinned DESC, created_at DESC LIMIT 20 OFFSET %s", (category, off))
            total = await db_one(cur, "SELECT COUNT(*) as cnt FROM forum_posts WHERE category=%s", (category,))
            return {"posts": posts, "total": total["cnt"]}

@app.post("/api/forum/posts")
async def create_post(m: ForumPostModel, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            cid = await get_colony_id(cur, uid)
            c = await db_one(cur, "SELECT name FROM colonies WHERE id=%s", (cid,))
            await db_exec(cur, "INSERT INTO forum_posts (author_id,author_name,category,title,content) VALUES (%s,%s,%s,%s,%s)", (cid, c["name"], m.category, m.title, m.content))
            post_id = cur.lastrowid
            await apply_forum_influence(cur, post_id, m.category, m.title, m.content, cid)
            await update_daily_task_progress(cur, cid, "post")
            await db_exec(cur, "UPDATE colonies SET score=score+2 WHERE id=%s", (cid,))
            return {"msg": "发帖成功，获得2积分"}

async def apply_forum_influence(cur, post_id, category, title, content, cid):
    if category == "trade":
        keywords_pos = ["利好", "上涨", "暴涨", "大涨", "牛市", "看涨", "推荐", "必涨"]
        keywords_neg = ["利空", "下跌", "暴跌", "大跌", "熊市", "看跌", "危险", "崩盘"]
        pos = sum(1 for k in keywords_pos if k in title + content)
        neg = sum(1 for k in keywords_neg if k in title + content)
        if pos > neg:
            for rt in random.sample(["minerals","energy","food","rare_metals","crystals"], min(2, 5)):
                await db_exec(cur, "UPDATE resource_prices SET current_price=LEAST(max_price, current_price+%s) WHERE resource_type=%s", (random.randint(1,3), rt))
        elif neg > pos:
            for rt in random.sample(["minerals","energy","food","rare_metals","crystals"], min(2, 5)):
                await db_exec(cur, "UPDATE resource_prices SET current_price=GREATEST(min_price, current_price-%s) WHERE resource_type=%s", (random.randint(1,3), rt))
    elif category == "strategy":
        cf = await db_one(cur, "SELECT faction_id FROM colony_factions WHERE colony_id=%s", (cid,))
        if cf:
            await db_exec(cur, "UPDATE factions SET total_score=total_score+5 WHERE id=%s", (cf["faction_id"],))
    elif category == "social":
        await db_exec(cur, "UPDATE colonies SET culture=culture+3 WHERE id=%s", (cid,))
    elif category == "tech":
        tech_keywords = ["突破", "发现", "创新", "革新", "量子", "跃迁", "反物质", "暗物质", "AI", "纳米"]
        if any(k in title + content for k in tech_keywords):
            await db_exec(cur, "UPDATE stocks SET change_pct=change_pct+0.1 WHERE sector IN ('科技','军工','能源') AND is_active=1 LIMIT 3")

@app.get("/api/forum/posts/{pid}")
async def get_post(pid: int, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            post = await db_one(cur, "SELECT * FROM forum_posts WHERE id=%s", (pid,))
            if not post: raise HTTPException(404, "帖子不存在")
            replies = await db_query(cur, "SELECT * FROM forum_replies WHERE post_id=%s ORDER BY created_at", (pid,))
            return {"post": post, "replies": replies}

@app.post("/api/forum/posts/{pid}/reply")
async def reply_post(pid: int, m: ReplyModel, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            cid = await get_colony_id(cur, uid)
            c = await db_one(cur, "SELECT name FROM colonies WHERE id=%s", (cid,))
            await db_exec(cur, "INSERT INTO forum_replies (post_id,author_id,author_name,content) VALUES (%s,%s,%s,%s)", (pid, cid, c["name"], m.content))
            await db_exec(cur, "UPDATE forum_posts SET reply_count=reply_count+1 WHERE id=%s", (pid,))
            return {"msg": "回复成功"}

@app.post("/api/forum/posts/{pid}/like")
async def like_post(pid: int, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await db_exec(cur, "UPDATE forum_posts SET like_count=like_count+1 WHERE id=%s", (pid,))
            cid = await get_colony_id(cur, uid)
            if cid:
                await check_achievements(cur, cid, uid)
            post = await db_one(cur, "SELECT like_count, category FROM forum_posts WHERE id=%s", (pid,))
            if post and post["like_count"] % 10 == 0 and post["like_count"] > 0:
                await apply_forum_influence(cur, pid, post["category"], "", "", 0)
            return {"msg": "已点赞"}

# ============================================================
#  实时聊天室
# ============================================================
@app.get("/api/chat/history")
async def chat_history(limit: int = 50, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            msgs = await db_query(cur, "SELECT * FROM chat_messages ORDER BY created_at DESC LIMIT %s", (limit,))
            msgs.reverse()
            return {"messages": msgs}

@app.post("/api/chat/send")
async def chat_send(m: ChatModel, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            cid = await get_colony_id(cur, uid)
            c = await db_one(cur, "SELECT name FROM colonies WHERE id=%s", (cid,))
            msg = m.message.strip()[:500]
            if not msg: raise HTTPException(400, "消息不能为空")
            await db_exec(cur, "INSERT INTO chat_messages (colony_id,author_name,message,is_npc) VALUES (%s,%s,%s,0)", (cid, c["name"], msg))
            msg_id = cur.lastrowid
            return {"id": msg_id, "author_name": c["name"], "message": msg}

# ============================================================
#  派系
# ============================================================
@app.get("/api/factions")
async def list_factions(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            factions = await db_query(cur, "SELECT * FROM factions ORDER BY total_score DESC")
            for f in factions:
                members = await db_query(cur, """SELECT c.name, cf.role FROM colony_factions cf 
                    JOIN colonies c ON cf.colony_id=c.id WHERE cf.faction_id=%s LIMIT 10""", (f["id"],))
                f["members"] = [{"name": m["name"], "role": m["role"]} for m in members]
                pool_res = await db_query(cur, "SELECT resource_type, amount FROM faction_resource_pool WHERE faction_id=%s", (f["id"],))
                f["resource_pool"] = {r["resource_type"]: r["amount"] for r in pool_res}
            return {"factions": factions}

@app.post("/api/factions/create")
async def create_faction(m: FactionModel, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            cid = await get_colony_id(cur, uid)
            ex = await db_one(cur, "SELECT id FROM factions WHERE name=%s", (m.name,))
            if ex: raise HTTPException(400, "派系名已存在")
            already = await db_one(cur, "SELECT * FROM colony_factions WHERE colony_id=%s", (cid,))
            if already: raise HTTPException(400, "已加入其他派系，请先退出")
            await db_exec(cur, "INSERT INTO factions (name,motto,ideology,leader_id) VALUES (%s,%s,%s,%s)", (m.name, m.motto, m.ideology, cid))
            fid = cur.lastrowid
            await db_exec(cur, "INSERT INTO colony_factions (colony_id,faction_id,role) VALUES (%s,%s,'leader')", (cid, fid))
            await add_notification(cur, cid, "创建派系", f"派系【{m.name}】创建成功！", "success")
            await check_achievements(cur, cid, uid)
            return {"msg": f"派系【{m.name}】创建成功"}

@app.post("/api/factions/{fid}/join")
async def join_faction(fid: int, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            cid = await get_colony_id(cur, uid)
            ex = await db_one(cur, "SELECT * FROM colony_factions WHERE colony_id=%s", (cid,))
            if ex: raise HTTPException(400, "已加入派系，请先退出当前派系")
            faction = await db_one(cur, "SELECT * FROM factions WHERE id=%s", (fid,))
            if not faction: raise HTTPException(404, "派系不存在")
            await db_exec(cur, "INSERT INTO colony_factions (colony_id,faction_id) VALUES (%s,%s)", (cid, fid))
            await db_exec(cur, "UPDATE factions SET member_count=member_count+1 WHERE id=%s", (fid,))
            await add_notification(cur, cid, "加入派系", f"已加入派系【{faction['name']}】", "success")
            return {"msg": "加入成功"}

@app.post("/api/factions/leave")
async def leave_faction(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            cid = await get_colony_id(cur, uid)
            cf = await db_one(cur, "SELECT * FROM colony_factions WHERE colony_id=%s", (cid,))
            if not cf: raise HTTPException(400, "未加入任何派系")
            if cf["role"] == "leader":
                raise HTTPException(400, "派系首领不能退出，请先转让或解散派系")
            await db_exec(cur, "DELETE FROM colony_factions WHERE colony_id=%s", (cid,))
            await db_exec(cur, "UPDATE factions SET member_count=GREATEST(member_count-1,0) WHERE id=%s", (cf["faction_id"],))
            return {"msg": "已退出派系"}

@app.get("/api/factions/my")
async def my_faction(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            cid = await get_colony_id(cur, uid)
            cf = await db_one(cur, "SELECT * FROM colony_factions WHERE colony_id=%s", (cid,))
            if not cf:
                return {"faction": None, "role": None, "missions": [], "resource_pool": {}}
            f = await db_one(cur, "SELECT * FROM factions WHERE id=%s", (cf["faction_id"],))
            members = await db_query(cur, """SELECT c.name, cf.role FROM colony_factions cf 
                JOIN colonies c ON cf.colony_id=c.id WHERE cf.faction_id=%s ORDER BY cf.role='leader' DESC""", (cf["faction_id"],))
            today = date.today().isoformat()
            missions = await db_query(cur, "SELECT * FROM faction_missions WHERE faction_id=%s AND task_date=%s", (cf["faction_id"], today))
            for m in missions:
                prog = await db_one(cur, "SELECT * FROM faction_mission_progress WHERE mission_id=%s AND colony_id=%s", (m["id"], cid))
                m["progress"] = prog["progress"] if prog else 0
                m["is_completed"] = bool(prog["is_completed"]) if prog else False
            pool_res = await db_query(cur, "SELECT resource_type, amount FROM faction_resource_pool WHERE faction_id=%s", (cf["faction_id"],))
            res_pool = {r["resource_type"]: r["amount"] for r in pool_res}
            return {"faction": f, "role": cf["role"], "members": members, "missions": missions, "resource_pool": res_pool}

@app.post("/api/factions/{fid}/donate")
async def faction_donate(fid: int, m: FactionDonateModel, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            cid = await get_colony_id(cur, uid)
            cf = await db_one(cur, "SELECT * FROM colony_factions WHERE colony_id=%s AND faction_id=%s", (cid, fid))
            if not cf: raise HTTPException(400, "你不是该派系成员")
            c = await db_one(cur, "SELECT * FROM colonies WHERE id=%s", (cid,))
            basic = {"minerals":"minerals","energy":"energy","food":"food","gold":"gold"}
            col = basic.get(m.resource_type) or m.resource_type
            if c.get(col, 0) < m.amount:
                raise HTTPException(400, f"{RESOURCE_MAP.get(m.resource_type,{}).get('name',m.resource_type)}不足")
            await db_exec(cur, f"UPDATE colonies SET {col}={col}-%s WHERE id=%s", (m.amount, cid))
            await db_exec(cur, """INSERT INTO faction_resource_pool (faction_id,resource_type,amount) VALUES (%s,%s,%s)
                ON DUPLICATE KEY UPDATE amount=amount+%s""", (fid, m.resource_type, m.amount, m.amount))
            score_gain = m.amount // 10 + 1
            await db_exec(cur, "UPDATE colonies SET score=score+%s WHERE id=%s", (score_gain, cid))
            await db_exec(cur, "UPDATE factions SET total_score=total_score+%s WHERE id=%s", (score_gain, fid))
            return {"msg": f"捐献{m.amount}{RESOURCE_MAP.get(m.resource_type,{}).get('name',m.resource_type)}，获得{score_gain}积分"}

@app.post("/api/factions/{fid}/missions/{mid}/complete")
async def complete_faction_mission(fid: int, mid: int, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            cid = await get_colony_id(cur, uid)
            m = await db_one(cur, "SELECT * FROM faction_missions WHERE id=%s AND faction_id=%s", (mid, fid))
            if not m: raise HTTPException(404, "任务不存在")
            prog = await db_one(cur, "SELECT * FROM faction_mission_progress WHERE mission_id=%s AND colony_id=%s", (mid, cid))
            if not prog or not prog["is_completed"]: raise HTTPException(400, "任务尚未完成")
            await db_exec(cur, "UPDATE colonies SET gold=gold+%s,score=score+%s WHERE id=%s", (m["reward_gold"], m["reward_score"], cid))
            await db_exec(cur, "UPDATE factions SET total_score=total_score+%s WHERE id=%s", (m["reward_faction_pts"], fid))
            return {"msg": f"领取奖励：{m['reward_gold']}金币 +{m['reward_score']}积分"}

# ============================================================
#  哲学
# ============================================================
@app.get("/api/philosophy")
async def get_philosophies(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            cid = await get_colony_id(cur, uid)
            all_p = await db_query(cur, "SELECT * FROM philosophy_config")
            my = {p["philosophy_type"]:p["level"] for p in await db_query(cur, "SELECT * FROM colony_philosophy WHERE colony_id=%s", (cid,))}
            return {"philosophies": [{**p, "current_level": my.get(p["philosophy_type"],0), "cost_gold": int(p["cost_gold_base"]*(my.get(p["philosophy_type"],0)+1))} for p in all_p]}

@app.post("/api/philosophy/research")
async def research_philosophy(m: PhiloModel, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            cid = await get_colony_id(cur, uid)
            cfg = await db_one(cur, "SELECT * FROM philosophy_config WHERE philosophy_type=%s", (m.philosophy_type,))
            cp = await db_one(cur, "SELECT * FROM colony_philosophy WHERE colony_id=%s AND philosophy_type=%s", (cid, m.philosophy_type))
            lvl = (cp["level"] if cp else 0) + 1
            cost = int(cfg["cost_gold_base"]*lvl)
            c = await db_one(cur, "SELECT gold FROM colonies WHERE id=%s", (cid,))
            if c["gold"] < cost: raise HTTPException(400, f"金币不足（需{cost}）")
            if lvl > cfg["max_level"]: raise HTTPException(400, "已达最高等级")
            await db_exec(cur, "UPDATE colonies SET gold=gold-%s,culture=culture+%s WHERE id=%s", (cost, lvl*5, cid))
            await db_exec(cur, "INSERT INTO colony_philosophy (colony_id,philosophy_type,level) VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE level=%s", (cid, m.philosophy_type, lvl, lvl))
            await check_achievements(cur, cid, uid)
            return {"msg": f"【{cfg['display_name']}】升级到{lvl}级", "cost": cost}

# ============================================================
#  NPC / 通知 / 排行 / 成就 / 探索 / 每日任务 / 领地
# ============================================================
@app.get("/api/npc/list")
async def npc_list(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            npcs = await db_query(cur, """SELECT n.*, u.username, c.name as colony_name, c.attack_power, c.defense_power, c.score
                FROM npc_bots n JOIN users u ON n.user_id=u.id JOIN colonies c ON c.user_id=u.id WHERE n.is_active=1""")
            for npc in npcs:
                p = NPC_PERSONALITIES.get(npc.get("personality","trader"), NPC_PERSONALITIES["trader"])
                npc["personality_info"] = {"name": p["name"], "style": p["style"], "emoji": p["emoji"], "traits": p["traits"]}
            return {"npcs": npcs}

@app.get("/api/notifications")
async def get_notifications(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            cid = await get_colony_id(cur, uid)
            notifs = await db_query(cur, "SELECT * FROM notifications WHERE colony_id=%s ORDER BY is_read, created_at DESC LIMIT 50", (cid,))
            unread = await db_one(cur, "SELECT COUNT(*) as cnt FROM notifications WHERE colony_id=%s AND is_read=0", (cid,))
            return {"notifications": notifs, "unread_count": unread["cnt"]}

@app.post("/api/notifications/read-all")
async def read_all(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            cid = await get_colony_id(cur, uid)
            await db_exec(cur, "UPDATE notifications SET is_read=1 WHERE colony_id=%s AND is_read=0", (cid,))
            return {"msg": "已全部已读"}

@app.get("/api/leaderboard")
async def leaderboard(sort: str = "score", uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            col_map = {"score":"score","attack":"attack_power","defense":"defense_power","gold":"gold","culture":"culture","win":"win_count"}
            col = col_map.get(sort, "score")
            rows = await db_query(cur, f"SELECT c.*, u.username FROM colonies c JOIN users u ON c.user_id=u.id ORDER BY c.{col} DESC LIMIT 20")
            return {"leaderboard": rows, "sort": sort}

@app.get("/api/achievements")
async def get_achievements(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            cid = await get_colony_id(cur, uid)
            all_a = await db_query(cur, "SELECT * FROM achievements ORDER BY category, id")
            unlocked = {a["achievement_id"] for a in await db_query(cur, "SELECT achievement_id FROM colony_achievements WHERE colony_id=%s", (cid,))}
            return {"achievements": [{**a, "unlocked": a["id"] in unlocked} for a in all_a]}

@app.get("/api/expeditions")
async def get_expeditions(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            cid = await get_colony_id(cur, uid)
            return {"expeditions": await db_query(cur, "SELECT * FROM expeditions WHERE colony_id=%s ORDER BY started_at DESC LIMIT 20", (cid,))}

@app.post("/api/expeditions/launch")
async def launch_expedition(m: ExpeditionModel, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            cid = await get_colony_id(cur, uid)
            c = await db_one(cur, "SELECT gold FROM colonies WHERE id=%s", (cid,))
            cost = m.fleet_size * 100
            if c["gold"] < cost: raise HTTPException(400, f"金币不足（需{cost}）")
            dur = 1 + m.fleet_size
            await db_exec(cur, "UPDATE colonies SET gold=gold-%s WHERE id=%s", (cost, cid))
            await db_exec(cur, "INSERT INTO expeditions (colony_id,target_sector,fleet_size,duration_hours,status,started_at) VALUES (%s,%s,%s,%s,'exploring',NOW())",
                (cid, m.target_sector, m.fleet_size, dur))
            await update_daily_task_progress(cur, cid, "explore")
            return {"msg": f"舰队出发前往{m.target_sector}，预计{dur}小时返回"}

@app.post("/api/expeditions/{eid}/claim")
async def claim_expedition(eid: int, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            cid = await get_colony_id(cur, uid)
            exp = await db_one(cur, "SELECT * FROM expeditions WHERE id=%s AND colony_id=%s", (eid, cid))
            if not exp: raise HTTPException(404, "探索记录不存在")
            if exp["status"] != "completed": raise HTTPException(400, "探索尚未完成")
            return {"msg": "奖励已领取", "rewards": {
                "minerals": exp["reward_minerals"], "energy": exp["reward_energy"],
                "food": exp["reward_food"], "gold": exp["reward_gold"],
                "score": exp["reward_score"], "discovery": exp["reward_discovery"]
            }}

@app.get("/api/daily_tasks")
async def get_daily_tasks(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            cid = await get_colony_id(cur, uid)
            today = date.today().isoformat()
            tasks = await db_query(cur, "SELECT * FROM daily_tasks WHERE task_date=%s", (today,))
            my = {p["task_id"]:p for p in await db_query(cur, "SELECT * FROM colony_daily_tasks WHERE colony_id=%s", (cid,))}
            return {"tasks": [{**t, "progress": my.get(t["id"],{}).get("progress",0), "is_completed": bool(my.get(t["id"],{}).get("is_completed",0))} for t in tasks]}

@app.post("/api/daily_tasks/{tid}/claim")
async def claim_task(tid: int, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            cid = await get_colony_id(cur, uid)
            t = await db_one(cur, "SELECT * FROM daily_tasks WHERE id=%s", (tid,))
            p = await db_one(cur, "SELECT * FROM colony_daily_tasks WHERE colony_id=%s AND task_id=%s AND is_completed=1", (cid, tid))
            if not p: raise HTTPException(400, "任务未完成或已领取")
            await db_exec(cur, "UPDATE colonies SET gold=gold+%s,score=score+%s WHERE id=%s", (t["reward_gold"], t["reward_score"], cid))
            await check_achievements(cur, cid, uid)
            return {"msg": f"领取{t['reward_gold']}金币 +{t['reward_score']}积分"}

async def update_daily_task_progress(cur, cid, task_type, increment=1):
    today = date.today().isoformat()
    tasks = await db_query(cur, "SELECT * FROM daily_tasks WHERE task_date=%s AND task_type=%s", (today, task_type))
    for t in tasks:
        cd = await db_one(cur, "SELECT * FROM colony_daily_tasks WHERE colony_id=%s AND task_id=%s", (cid, t["id"]))
        if cd and cd["is_completed"]: continue
        progress = (cd["progress"] if cd else 0) + increment
        if progress >= t["target_value"]:
            if cd:
                await db_exec(cur, "UPDATE colony_daily_tasks SET progress=%s,is_completed=1,completed_at=NOW() WHERE colony_id=%s AND task_id=%s", (progress, cid, t["id"]))
            else:
                await db_exec(cur, "INSERT INTO colony_daily_tasks (colony_id,task_id,progress,is_completed,completed_at) VALUES (%s,%s,%s,1,NOW())", (cid, t["id"], progress))
            await add_notification(cur, cid, "每日任务完成", f"【{t['title']}】已完成，记得领取奖励！", "success")
        else:
            if cd:
                await db_exec(cur, "UPDATE colony_daily_tasks SET progress=%s WHERE colony_id=%s AND task_id=%s", (progress, cid, t["id"]))
            else:
                await db_exec(cur, "INSERT INTO colony_daily_tasks (colony_id,task_id,progress) VALUES (%s,%s,%s)", (cid, t["id"], progress))

# ============================================================
#  领地
# ============================================================
@app.get("/api/territories")
async def get_territories(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            territories = await db_query(cur, """SELECT t.*, c.name as owner_name, u.username as owner_username
                FROM territories t LEFT JOIN colonies c ON t.owner_colony=c.id 
                LEFT JOIN users u ON c.user_id=u.id
                WHERE t.is_active=1 ORDER BY t.id""")
            cid = await get_colony_id(cur, uid)
            for t in territories:
                t["is_mine"] = (t["owner_colony"] == cid) if cid else False
            return {"territories": territories}

@app.post("/api/territories/{tid}/capture")
async def capture_territory(tid: int, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            cid = await get_colony_id(cur, uid)
            c = await db_one(cur, "SELECT * FROM colonies WHERE id=%s", (cid,))
            terr = await db_one(cur, "SELECT * FROM territories WHERE id=%s AND is_active=1", (tid,))
            if not terr: raise HTTPException(404, "领地不存在")
            if terr["owner_colony"] == cid: raise HTTPException(400, "已是你的领地")
            if terr["owner_colony"]:
                defender = await db_one(cur, "SELECT * FROM colonies WHERE id=%s", (terr["owner_colony"],))
                if c["attack_power"] <= defender["defense_power"]:
                    raise HTTPException(400, "攻击力不足，无法夺取")
                await db_exec(cur, "UPDATE colonies SET lose_count=lose_count+1 WHERE id=%s", (defender["id"],))
            await db_exec(cur, "UPDATE territories SET owner_colony=%s,captured_at=NOW() WHERE id=%s", (cid, tid))
            await db_exec(cur, "UPDATE colonies SET score=score+%s WHERE id=%s", (terr["bonus_score"], cid))
            await add_notification(cur, cid, "占领领地", f"成功占领【{terr['name']}】，每30分钟自动收取资源！", "success")
            return {"msg": f"占领【{terr['name']}】成功，领地将每30分钟产出资源！"}

@app.post("/api/territories/{tid}/collect")
async def collect_territory_income(tid: int, uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            cid = await get_colony_id(cur, uid)
            terr = await db_one(cur, "SELECT * FROM territories WHERE id=%s AND owner_colony=%s AND is_active=1", (tid, cid))
            if not terr: raise HTTPException(400, "领地不属于你")
            g_minerals = terr["bonus_minerals"] * 5
            g_energy = terr["bonus_energy"] * 5
            g_food = terr["bonus_food"] * 5
            g_gold = terr["bonus_score"] * 2
            await db_exec(cur, "UPDATE colonies SET minerals=minerals+%s,energy=energy+%s,food=food+%s,gold=gold+%s WHERE id=%s",
                (g_minerals, g_energy, g_food, g_gold, cid))
            return {"msg": f"收取【{terr['name']}】产出：矿+{g_minerals} 能+{g_energy} 食+{g_food} 金+{g_gold}"}

@app.get("/api/events/today")
async def today_events(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            today = date.today().isoformat()
            return {"events": await db_query(cur, "SELECT * FROM daily_events WHERE event_date=%s", (today,))}

# 上帝AI状态
@app.get("/api/god/status")
async def god_status(uid=Depends(get_user)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            logs = await db_query(cur, "SELECT * FROM god_ai_log ORDER BY created_at DESC LIMIT 10")
            return {"god_logs": logs}

# ============================================================
#  V7: 管理面板 - God AI
# ============================================================
@app.get("/admin/api/god-ai/logs")
async def admin_god_ai_logs(page: int = 1, limit: int = 20, uid=Depends(get_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            off = (page - 1) * limit
            logs = await db_query(cur, "SELECT * FROM god_ai_log ORDER BY created_at DESC LIMIT %s OFFSET %s", (limit, off))
            total = await db_one(cur, "SELECT COUNT(*) as cnt FROM god_ai_log")
            return {"logs": logs, "total": total["cnt"] if total else 0, "page": page}

@app.post("/admin/api/god-ai/execute")
async def admin_god_ai_execute(uid=Depends(get_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            action = random.choices(
                ["balance_economy","weather_event","fix_data","market_intervention","stock_event","reward_active"],
                weights=[25,20,15,20,10,10]
            )[0]
            desc = await execute_god_action(cur, action)
            await db_exec(cur, "INSERT INTO god_ai_log (action_type,description) VALUES (%s,%s)", (action, desc))
            return {"msg": f"God AI动作已执行: {action}", "description": desc}

@app.post("/admin/api/god-ai/modify")
async def admin_god_ai_modify(m: GodAIModifyModel, uid=Depends(get_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            # 安全限制：只允许修改特定表
            allowed_tables = ["colonies", "stocks", "resource_prices", "factions", "territories", "users", "npc_bots"]
            if m.table not in allowed_tables:
                raise HTTPException(400, f"不允许修改表 {m.table}，允许的表: {allowed_tables}")
            # 检查字段是否合法（防SQL注入）
            row = await db_one(cur, f"SELECT * FROM {m.table} WHERE id=%s", (m.row_id,))
            if not row:
                raise HTTPException(404, f"{m.table}中id={m.row_id}不存在")
            if m.field not in row:
                raise HTTPException(400, f"字段 {m.field} 不存在于表 {m.table}")
            # 尝试数值转换
            try:
                val = float(m.value) if '.' in m.value else int(m.value)
            except ValueError:
                val = m.value
            await db_exec(cur, f"UPDATE {m.table} SET {m.field}=%s WHERE id=%s", (val, m.row_id))
            await db_exec(cur, "INSERT INTO god_ai_log (action_type,description) VALUES (%s,%s)",
                ("manual_modify", f"管理员修改 {m.table}.id={m.row_id} {m.field}={m.value}"))
            return {"msg": f"已修改 {m.table}.id={m.row_id} {m.field}={m.value}"}

async def execute_god_action(cur, action):
    """执行God AI动作，返回描述"""
    desc = ""
    if action == "balance_economy":
        prices = await db_query(cur, "SELECT * FROM resource_prices")
        for p in prices:
            if p["current_price"] > p["base_price"] * 3:
                new_p = int(p["current_price"] * 0.85)
                await db_exec(cur, "UPDATE resource_prices SET current_price=%s WHERE resource_type=%s", (new_p, p["resource_type"]))
                desc += f"{p['resource_type']}价格过高，下调至{new_p}; "
            elif p["current_price"] < p["base_price"] * 0.3:
                new_p = int(p["current_price"] * 1.2)
                await db_exec(cur, "UPDATE resource_prices SET current_price=%s WHERE resource_type=%s", (new_p, p["resource_type"]))
                desc += f"{p['resource_type']}价格过低，上调至{new_p}; "
        if not desc: desc = "经济系统运行正常，无需干预"

    elif action == "weather_event":
        events = [
            ("暗物质风暴", "一场暗物质风暴正在席卷银河系边缘", "minerals", -0.05),
            ("量子潮汐", "量子潮汐带来了异常的能量波动", "energy", 0.1),
            ("星际寒流", "星际寒流来袭，食物产量受影响", "food", -0.08),
            ("等离子雨", "等离子雨降临，能源收集效率提升", "energy", 0.15),
            ("陨石群", "陨石群经过，矿物资源丰富", "minerals", 0.12),
            ("和平时期", "星际局势平稳，贸易繁荣", "gold", 0.05),
        ]
        evt = random.choice(events)
        colonies = await db_query(cur, "SELECT id FROM colonies")
        for c in colonies:
            await db_exec(cur, f"UPDATE colonies SET {evt[2]}={evt[2]}*(1+%s) WHERE id=%s", (evt[3], c["id"]))
            await add_notification(cur, c["id"], f"天气事件：{evt[0]}", evt[1], "event")
        desc = f"{evt[0]}: {evt[1]}"

    elif action == "fix_data":
        await db_exec(cur, "UPDATE colonies SET minerals=GREATEST(minerals,0), energy=GREATEST(energy,0), food=GREATEST(food,0), gold=GREATEST(gold,0)")
        await db_exec(cur, "UPDATE colonies SET attack_power=GREATEST(attack_power,10), defense_power=GREATEST(defense_power,10)")
        await db_exec(cur, "UPDATE colonies SET happiness=GREATEST(LEAST(happiness,100),0)")
        desc = "数据修复：负值归零、异常值修正"

    elif action == "market_intervention":
        stocks = await db_query(cur, "SELECT * FROM stocks WHERE is_active=1 ORDER BY RAND() LIMIT 3")
        for s in stocks:
            direction = random.choice(["up","down"])
            pct = random.uniform(0.5, 2.0)
            if direction == "up":
                new_price = round(float(s["current_price"]) * (1 + pct/100), 2)
            else:
                new_price = round(float(s["current_price"]) * (1 - pct/100), 2)
            prev = float(s["prev_close"])
            new_price = max(round(prev*0.9,2), min(round(prev*1.1,2), new_price))
            await db_exec(cur, "UPDATE stocks SET current_price=%s WHERE code=%s", (new_price, s["code"]))
            desc += f"{s['name']}{'↑' if direction=='up' else '↓'}{pct:.1f}%; "

    elif action == "stock_event":
        events = [
            ("利好政策", "星际联邦发布新政策，相关行业利好", 1),
            ("行业丑闻", "某大型企业爆出丑闻，股价承压", -1),
            ("技术突破", "重大技术突破引发市场热议", 1),
            ("经济数据", "最新经济数据不及预期", -1),
        ]
        evt = random.choice(events)
        direction = evt[2]
        stocks = await db_query(cur, "SELECT code FROM stocks WHERE is_active=1 ORDER BY RAND() LIMIT 5")
        for s in stocks:
            chg = round(random.uniform(0.3, 1.5) * direction, 2)
            await db_exec(cur, "UPDATE stocks SET change_pct=change_pct+%s WHERE code=%s", (chg, s["code"]))
        desc = f"{evt[0]}: {evt[1]}"

    elif action == "reward_active":
        active = await db_query(cur, "SELECT id FROM colonies WHERE last_online > DATE_SUB(NOW(), INTERVAL 1 HOUR) LIMIT 10")
        for c in active:
            reward = random.randint(50, 200)
            await db_exec(cur, "UPDATE colonies SET gold=gold+%s WHERE id=%s", (reward, c["id"]))
            await add_notification(cur, c["id"], "活跃奖励", f"感谢你的活跃，获得{reward}金币奖励！", "success")
        desc = f"发放活跃奖励给{len(active)}个殖民地"

    return desc

# ============================================================
#  后台任务：股票引擎（V7增强：跨模块影响+交易量涨跌停）
# ============================================================
async def bg_stock_engine():
    await asyncio.sleep(10)
    while True:
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    stocks = await db_query(cur, "SELECT * FROM stocks WHERE is_active=1")
                    for s in stocks:
                        price = float(s["current_price"])
                        prev = float(s["prev_close"])
                        volatility = random.gauss(0, 0.015)
                        trend = float(s["change_pct"]) / 100 * 0.1
                        change = volatility + trend
                        new_price = round(price * (1 + change), 2)
                        limit_up = round(prev * 1.1, 2)
                        limit_down = round(prev * 0.9, 2)

                        # V7: 基于日内交易量的价格压力
                        buy_vol = int(s.get("daily_buy_vol", 0) or 0)
                        sell_vol = int(s.get("daily_sell_vol", 0) or 0)
                        total_vol = buy_vol + sell_vol
                        if total_vol > 0:
                            buy_ratio = buy_vol / total_vol
                            if buy_ratio > 0.7:
                                # 买压过大，推高价格
                                change += 0.005 * (buy_ratio - 0.5)
                            elif buy_ratio < 0.3:
                                # 卖压过大，压低价格
                                change -= 0.005 * (0.5 - buy_ratio)

                        new_price = round(price * (1 + change), 2)
                        new_price = max(limit_down, min(limit_up, new_price))
                        new_price = max(0.01, new_price)
                        chg_amt = round(new_price - prev, 2)
                        chg_pct = round((new_price / prev - 1) * 100, 2) if prev > 0 else 0
                        hi = max(float(s["high_price"]), new_price)
                        lo = min(float(s["low_price"]), new_price)
                        vol = random.randint(1000, 50000)
                        turnover = round(new_price * vol, 2)
                        await db_exec(cur, """UPDATE stocks SET current_price=%s, high_price=%s, low_price=%s,
                            change_amt=%s, change_pct=%s, volume=volume+%s, turnover=turnover+%s WHERE code=%s""",
                            (new_price, hi, lo, chg_amt, chg_pct, vol, turnover, s["code"]))
                        for level in range(1, 6):
                            buy_p = round(new_price * (1 - level * 0.002), 2)
                            sell_p = round(new_price * (1 + level * 0.002), 2)
                            buy_v = random.randint(100, 5000) * (6-level)
                            sell_v = random.randint(100, 5000) * (6-level)
                            await db_exec(cur, """INSERT INTO stock_orderbook (stock_code,direction,price_level,price,volume)
                                VALUES (%s,'buy',%s,%s,%s) ON DUPLICATE KEY UPDATE price=%s, volume=%s""",
                                (s["code"], level, buy_p, buy_v, buy_p, buy_v))
                            await db_exec(cur, """INSERT INTO stock_orderbook (stock_code,direction,price_level,price,volume)
                                VALUES (%s,'sell',%s,%s,%s) ON DUPLICATE KEY UPDATE price=%s, volume=%s""",
                                (s["code"], level, sell_p, sell_v, sell_p, sell_v))

                    # V7: 跨模块影响
                    # 1. 资源价格影响
                    stocks = await db_query(cur, "SELECT * FROM stocks WHERE is_active=1")
                    for s in stocks:
                        sector = s.get("sector", "")
                        related_resources = SECTOR_RESOURCE_MAP.get(sector, [])
                        if not related_resources:
                            continue
                        prev = float(s["prev_close"])
                        limit_up = round(prev * 1.1, 2)
                        limit_down = round(prev * 0.9, 2)
                        current_price = float(s["current_price"])
                        for rr in related_resources:
                            rp = await db_one(cur, "SELECT trend FROM resource_prices WHERE resource_type=%s", (rr,))
                            if rp and rp["trend"] == "up":
                                current_price = min(round(current_price * 1.002, 2), limit_up)
                            elif rp and rp["trend"] == "down":
                                current_price = max(round(current_price * 0.998, 2), limit_down)
                        if current_price != float(s["current_price"]):
                            chg_pct = round((current_price / prev - 1) * 100, 2) if prev > 0 else 0
                            await db_exec(cur, "UPDATE stocks SET current_price=%s, change_pct=%s WHERE code=%s",
                                (current_price, chg_pct, s["code"]))

                    # 2. 期货影响
                    long_count = await db_one(cur, "SELECT COUNT(*) as cnt FROM futures_contracts WHERE direction='long' AND status='open'")
                    short_count = await db_one(cur, "SELECT COUNT(*) as cnt FROM futures_contracts WHERE direction='short' AND status='open'")
                    if long_count and short_count:
                        if long_count["cnt"] > short_count["cnt"] * 1.5:
                            # 多头优势，利好市场
                            top_stocks = await db_query(cur, "SELECT code, prev_close, current_price FROM stocks WHERE is_active=1 ORDER BY RAND() LIMIT 5")
                            for ts in top_stocks:
                                prev = float(ts["prev_close"])
                                cp = float(ts["current_price"])
                                limit_up = round(prev * 1.1, 2)
                                new_cp = min(round(cp * 1.001, 2), limit_up)
                                await db_exec(cur, "UPDATE stocks SET current_price=%s WHERE code=%s", (new_cp, ts["code"]))
                        elif short_count["cnt"] > long_count["cnt"] * 1.5:
                            # 空头优势，利空市场
                            top_stocks = await db_query(cur, "SELECT code, prev_close, current_price FROM stocks WHERE is_active=1 ORDER BY RAND() LIMIT 5")
                            for ts in top_stocks:
                                prev = float(ts["prev_close"])
                                cp = float(ts["current_price"])
                                limit_down = round(prev * 0.9, 2)
                                new_cp = max(round(cp * 0.999, 2), limit_down)
                                await db_exec(cur, "UPDATE stocks SET current_price=%s WHERE code=%s", (new_cp, ts["code"]))

                    # 3. 论坛情绪影响
                    trade_posts = await db_query(cur, "SELECT title, content FROM forum_posts WHERE category='trade' AND created_at > DATE_SUB(NOW(), INTERVAL 1 HOUR)")
                    bullish_kw = ["利好", "上涨", "暴涨", "大涨", "牛市", "看涨", "推荐", "必涨"]
                    bearish_kw = ["利空", "下跌", "暴跌", "大跌", "熊市", "看跌", "危险", "崩盘"]
                    bullish = sum(1 for p in trade_posts for kw in bullish_kw if kw in (p["title"]+p.get("content","")))
                    bearish = sum(1 for p in trade_posts for kw in bearish_kw if kw in (p["title"]+p.get("content","")))
                    if bullish > bearish + 2:
                        sentiment_boost = 0.001 * min(bullish - bearish, 5)
                        all_stocks = await db_query(cur, "SELECT code, prev_close, current_price FROM stocks WHERE is_active=1")
                        for as_ in all_stocks:
                            prev = float(as_["prev_close"])
                            cp = float(as_["current_price"])
                            limit_up = round(prev * 1.1, 2)
                            new_cp = min(round(cp * (1 + sentiment_boost), 2), limit_up)
                            await db_exec(cur, "UPDATE stocks SET current_price=%s WHERE code=%s", (new_cp, as_["code"]))
                    elif bearish > bullish + 2:
                        sentiment_drop = 0.001 * min(bearish - bullish, 5)
                        all_stocks = await db_query(cur, "SELECT code, prev_close, current_price FROM stocks WHERE is_active=1")
                        for as_ in all_stocks:
                            prev = float(as_["prev_close"])
                            cp = float(as_["current_price"])
                            limit_down = round(prev * 0.9, 2)
                            new_cp = max(round(cp * (1 - sentiment_drop), 2), limit_down)
                            await db_exec(cur, "UPDATE stocks SET current_price=%s WHERE code=%s", (new_cp, as_["code"]))

                    # 4. 每日事件影响
                    today_event = await db_one(cur, "SELECT * FROM daily_events WHERE event_date=%s", (date.today(),))
                    if today_event and today_event.get("effect_market"):
                        affected_sectors = {
                            "minerals": ["矿业", "军工", "运输"],
                            "energy": ["能源", "运输", "综合"],
                            "food": ["农业", "综合"],
                        }
                        market = today_event["effect_market"]
                        pct = today_event.get("effect_market_pct", 0) or 0
                        if market in affected_sectors:
                            for sector in affected_sectors[market]:
                                sector_stocks = await db_query(cur, "SELECT code, prev_close, current_price FROM stocks WHERE sector=%s AND is_active=1", (sector,))
                                for ss in sector_stocks:
                                    prev = float(ss["prev_close"])
                                    cp = float(ss["current_price"])
                                    limit_up = round(prev * 1.1, 2)
                                    limit_down = round(prev * 0.9, 2)
                                    multiplier = 1 + pct / 1000  # 缩小影响
                                    new_cp = max(limit_down, min(limit_up, round(cp * multiplier, 2)))
                                    await db_exec(cur, "UPDATE stocks SET current_price=%s WHERE code=%s", (new_cp, ss["code"]))

                    # 更新投资组合
                    ports = await db_query(cur, """SELECT sp.colony_id, sp.stock_code, sp.amount, sp.total_cost, s.current_price
                        FROM stock_portfolios sp JOIN stocks s ON sp.stock_code=s.code WHERE sp.amount>0""")
                    for p in ports:
                        cv = float(p["current_price"]) * p["amount"]
                        await db_exec(cur, "UPDATE stock_portfolios SET current_value=%s, profit_loss=%s, profit_pct=%s WHERE colony_id=%s AND stock_code=%s",
                            (round(cv,2), round(cv-float(p["total_cost"]),2), round((cv/float(p["total_cost"])-1)*100,2) if float(p["total_cost"])>0 else 0, p["colony_id"], p["stock_code"]))
        except Exception as e:
            log.error(f"Stock engine error: {e}")
        await asyncio.sleep(30)

async def bg_kline_recorder():
    while True:
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    stocks = await db_query(cur, "SELECT * FROM stocks WHERE is_active=1")
                    today = date.today().isoformat()
                    for s in stocks:
                        await db_exec(cur, """INSERT INTO stock_klines (stock_code,k_date,open_price,high_price,low_price,close_price,volume,change_pct)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE
                            high_price=GREATEST(high_price,VALUES(high_price)),
                            low_price=LEAST(low_price,VALUES(low_price)),
                            close_price=VALUES(close_price), volume=volume+VALUES(volume), change_pct=VALUES(change_pct)""",
                            (s["code"], today, s["open_price"], s["high_price"], s["low_price"], s["current_price"], s["volume"], s["change_pct"]))
                    # V7: 午夜重置日交易量 - 用数据库时间避免时区问题
                    now_row = await db_one(cur, "SELECT HOUR(NOW()) as h, MINUTE(NOW()) as m")
                    if now_row and now_row["h"] == 0 and now_row["m"] < 2:
                        await db_exec(cur, "UPDATE stocks SET daily_buy_vol=0, daily_buy_amount=0, daily_sell_vol=0, daily_sell_amount=0")
                        log.info("V7: 已重置股票日交易量")
        except Exception as e:
            log.error(f"Kline recorder error: {e}")
        await asyncio.sleep(60)

async def bg_market_maker():
    await asyncio.sleep(15)
    while True:
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    for rt in ("minerals","energy","food","rare_metals","crystals","plasma","dark_matter","antimatter"):
                        rp = await db_one(cur, "SELECT * FROM resource_prices WHERE resource_type=%s", (rt,))
                        if not rp: continue
                        base = rp["base_price"]; cur_p = rp["current_price"]; vol = rp["volatility"]
                        noise = random.gauss(0, vol * 0.3)
                        new_p = int(base + (cur_p - base) * 0.95 + noise)
                        new_p = max(rp["min_price"], min(rp["max_price"], new_p))
                        if new_p > base * 2:
                            new_p = int(new_p * 0.9)
                            await db_exec(cur, "UPDATE resource_prices SET maker_balance=maker_balance-%s WHERE resource_type=%s", (1000, rt))
                        elif new_p < base * 0.5:
                            new_p = int(new_p * 1.1)
                            await db_exec(cur, "UPDATE resource_prices SET maker_balance=maker_balance+%s WHERE resource_type=%s", (1000, rt))
                        trend = "up" if new_p > cur_p else ("down" if new_p < cur_p else "stable")
                        await db_exec(cur, "UPDATE resource_prices SET current_price=%s, trend=%s, updated_at=NOW() WHERE resource_type=%s", (new_p, trend, rt))
                        await db_exec(cur, "INSERT INTO market_prices (resource_type,price,volume) VALUES (%s,%s,%s)", (rt, new_p, random.randint(10,100)))
        except Exception as e:
            log.error(f"Market maker error: {e}")
        await asyncio.sleep(30)

async def bg_futures_liquidation():
    await asyncio.sleep(30)
    while True:
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    positions = await db_query(cur, """SELECT fc.*, rp.current_price FROM futures_contracts fc
                        JOIN resource_prices rp ON fc.resource_type=rp.resource_type WHERE fc.status='open'""")
                    for p in positions:
                        pnl = (p["current_price"]-p["entry_price"])*p["amount"] if p["direction"]=="long" else (p["entry_price"]-p["current_price"])*p["amount"]
                        pnl *= p["leverage"]
                        if pnl < -p["margin"]*0.8:
                            await db_exec(cur, "UPDATE futures_contracts SET status='liquidated',profit_loss=%s,closed_at=NOW() WHERE id=%s", (int(pnl), p["id"]))
                            await add_notification(cur, p["colony_id"], "期货强平", f"你的{p['resource_type']}期货仓位已被强平", "danger")
                    sf_pos = await db_query(cur, """SELECT sf.*, s.current_price FROM stock_futures sf
                        JOIN stocks s ON sf.stock_code=s.code WHERE sf.status='open'""")
                    for p in sf_pos:
                        ep = float(p["entry_price"]); cp = float(p["current_price"])
                        pnl = (cp-ep)*p["amount"] if p["direction"]=="long" else (ep-cp)*p["amount"]
                        pnl = round(pnl*p["leverage"], 2)
                        if pnl < -float(p["margin"])*0.8:
                            await db_exec(cur, "UPDATE stock_futures SET status='liquidated',profit_loss=%s,closed_at=NOW() WHERE id=%s", (pnl, p["id"]))
                            await add_notification(cur, p["colony_id"], "股票期货强平", f"你的{p['stock_code']}合约已被强平", "danger")
        except Exception as e:
            log.error(f"Liquidation error: {e}")
        await asyncio.sleep(60)

# ============================================================
#  后台任务：NPC AI调度器（V6增强版：人格驱动）
# ============================================================
async def bg_npc_scheduler():
    await asyncio.sleep(20)
    while True:
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    npcs = await db_query(cur, """SELECT n.*, u.username, c.id as colony_id, c.minerals, c.energy, c.food, c.gold,
                        c.attack_power, c.defense_power, c.score, c.name as colony_name
                        FROM npc_bots n JOIN users u ON n.user_id=u.id JOIN colonies c ON c.user_id=u.id WHERE n.is_active=1""")
                    for bot in npcs:
                        try:
                            pers = NPC_PERSONALITIES.get(bot.get("personality","trader"), NPC_PERSONALITIES["trader"])
                            actions = ["trade","build","post","attack","philosophy","craft","territory","research"]
                            weights = [
                                int(25 * pers["trade_freq"]),
                                20,
                                int(25 * pers["post_freq"]),
                                15 if pers["style"] in ["豪爽","精明"] else 5,
                                10 if pers["style"] in ["博学"] else 8,
                                5,
                                8,
                                10 if pers["style"] in ["博学"] else 5,
                            ]
                            action = random.choices(actions, weights=weights)[0]
                            if action == "trade":
                                await npc_trade(cur, bot)
                            elif action == "build":
                                await npc_build(cur, bot)
                            elif action == "post":
                                await npc_post(cur, bot)
                            elif action == "attack":
                                await npc_attack(cur, bot)
                            elif action == "philosophy":
                                await npc_philosophy(cur, bot)
                            elif action == "craft":
                                await npc_craft(cur, bot)
                            elif action == "territory":
                                await npc_capture_territory(cur, bot)
                            elif action == "research":
                                await npc_research(cur, bot)
                        except Exception as e:
                            log.warning(f"NPC {bot.get('colony_name','?')} error: {e}")
        except Exception as e:
            log.error(f"NPC scheduler error: {e}")
        await asyncio.sleep(45)

async def npc_trade(cur, bot):
    pers = NPC_PERSONALITIES.get(bot.get("personality","trader"), NPC_PERSONALITIES["trader"])
    if random.random() < 0.5 and bot["gold"] > 200:
        rt = random.choice(["minerals","energy","food","rare_metals","crystals","plasma"])
        rp = await db_one(cur, "SELECT current_price FROM resource_prices WHERE resource_type=%s", (rt,))
        if not rp: return
        amount = random.randint(1, min(10, bot["gold"]//rp["current_price"]))
        total = rp["current_price"]*amount
        rc = {"minerals":"minerals","energy":"energy","food":"food"}.get(rt)
        if rc:
            await db_exec(cur, f"UPDATE colonies SET gold=gold-%s,{rc}={rc}+%s WHERE id=%s", (total, amount, bot["colony_id"]))
        else:
            await db_exec(cur, "UPDATE colonies SET gold=gold-%s WHERE id=%s", (total, bot["colony_id"]))
        await db_exec(cur, "INSERT INTO trade_history (buyer_id,resource_type,amount,unit_price,total_gold,is_npc) VALUES (%s,%s,%s,%s,%s,1)",
            (bot["colony_id"], rt, amount, rp["current_price"], total))
    elif bot["gold"] > 500:
        stocks = await db_query(cur, "SELECT * FROM stocks WHERE is_active=1 ORDER BY RAND() LIMIT 3")
        for s in stocks:
            if bot["gold"] > float(s["current_price"])*10:
                amt = random.randint(1, 10)
                price = float(s["current_price"])
                total = round(price*amt*1.001, 2)
                # V7: NPC交易也受涨跌停限制
                prev_close = float(s["prev_close"])
                if price >= round(prev_close * 1.1, 2):
                    continue  # 涨停不买
                await db_exec(cur, "UPDATE colonies SET gold=gold-%s WHERE id=%s", (total, bot["colony_id"]))
                await db_exec(cur, """INSERT INTO stock_portfolios (colony_id,stock_code,amount,total_cost,avg_cost)
                    VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE amount=amount+%s, total_cost=total_cost+%s""",
                    (bot["colony_id"], s["code"], amt, total, price, amt, total))
                await db_exec(cur, "INSERT INTO stock_trades (colony_id,stock_code,direction,price,amount,total_gold,is_npc) VALUES (%s,%s,'buy',%s,%s,%s,1)",
                    (bot["colony_id"], s["code"], price, amt, total))
                # V7: 追踪NPC买入量
                await db_exec(cur, "UPDATE stocks SET daily_buy_vol=daily_buy_vol+%s, daily_buy_amount=daily_buy_amount+%s, volume=volume+%s, turnover=turnover+%s WHERE code=%s",
                    (amt, total, amt, total, s["code"]))
                break

async def npc_build(cur, bot):
    types = ["mine","solar_plant","farm","barracks","gold_mine","lab","library","theater"]
    bt = random.choice(types)
    cfg = await db_one(cur, "SELECT * FROM building_config WHERE building_type=%s", (bt,))
    if cfg and bot["minerals"]>=cfg["cost_minerals"] and bot["energy"]>=cfg["cost_energy"] and bot["food"]>=cfg["cost_food"]:
        slot = random.randint(0,11)
        ex = await db_one(cur, "SELECT id FROM buildings WHERE colony_id=%s AND slot=%s", (bot["colony_id"], slot))
        if not ex:
            await db_exec(cur, "UPDATE colonies SET minerals=minerals-%s,energy=energy-%s,food=food-%s WHERE id=%s",
                (cfg["cost_minerals"], cfg["cost_energy"], cfg["cost_food"], bot["colony_id"]))
            await db_exec(cur, "INSERT INTO buildings (colony_id,building_type,slot) VALUES (%s,%s,%s)", (bot["colony_id"], bt, slot))
            await recalc_power(cur, bot["colony_id"])

async def npc_post(cur, bot):
    """NPC发帖 - 基于人格的内容生成"""
    pers = NPC_PERSONALITIES.get(bot.get("personality","trader"), NPC_PERSONALITIES["trader"])
    categories = ["general","trade","strategy","social","tech"]
    cat_pref = {
        "trader": ["trade","general"],
        "miner": ["general","strategy"],
        "scholar": ["tech","strategy"],
        "warrior": ["social","strategy"],
        "merchant": ["trade","social"],
    }
    pref_cats = cat_pref.get(bot.get("personality","trader"), categories)
    cat = random.choice(pref_cats)

    title_templates = {
        "trader": [
            f"【行情分析】{random.choice(['矿物','能量','稀有金属'])}市场走势研判",
            f"【投资建议】现在是入场的好时机吗？",
            f"今日交易心得分享",
            f"市场波动预警！大家注意风险",
        ],
        "miner": [
            f"【矿区报告】今日矿产储量更新",
            f"发现新矿脉！坐标分享",
            f"采矿效率提升技巧",
        ],
        "scholar": [
            f"量子计算突破：新型处理器运算速度提升300%",
            f"暗物质采集技术获得重大进展，产量有望翻倍",
            f"反物质引擎原型机测试成功",
            f"纳米材料研究突破：自修复护盾不再是梦想",
            f"跃迁引擎2.0设计完成，超光速航行即将实现",
            f"AI辅助决策系统上线，殖民管理效率提升50%",
            f"等离子体存储新技术：容量提升5倍",
        ],
        "warrior": [
            f"【战报】今日战绩：攻防数据统计",
            f"防御工事升级心得：先护盾后炮台",
            f"谁敢来挑战？我随时应战",
            f"军事科技研究进展报告",
        ],
        "merchant": [
            f"【特价】今日商品促销！量大从优",
            f"寻找合作伙伴！长期交易优先",
            f"市场供需分析：{random.choice(['矿物','能量','食物'])}紧缺",
            f"好消息！新一批稀有物资到货",
        ],
    }
    titles = title_templates.get(bot.get("personality","trader"), title_templates["trader"])
    title = random.choice(titles)

    content_templates = {
        "trader": f"各位，{random.choice(['矿物','能量','稀有金属'])}价格{'上涨' if random.random()>0.5 else '下跌'}趋势明显，建议{'逢低买入' if random.random()>0.5 else '及时止损'}。数据不会骗人，{bot['colony_name']}交易室持续为大家分析！",
        "miner": f"今天矿区产出：矿物+{random.randint(100,500)}，效率{'提升' if random.random()>0.5 else '正常'}。建议大家优先升级矿场。",
        "scholar": f"经过{random.randint(3,12)}个月的研究，我们在{random.choice(['量子计算','暗物质','纳米材料','反物质'])}领域取得了突破性进展。详细数据将在后续论文中公布。",
        "warrior": f"{'攻击力' if random.random()>0.5 else '防御力'}已提升到{bot['attack_power']+random.randint(10,50)}，{bot['colony_name']}欢迎挑战！不过我劝你们三思...",
        "merchant": f"嗨朋友们！{bot['colony_name']}今日营业！{random.choice(['稀有金属打折','水晶特价','等离子体限量供应'])}，走过路过不要错过！有需要的私信我~",
    }
    content = content_templates.get(bot.get("personality","trader"), content_templates["trader"])

    await db_exec(cur, "INSERT INTO forum_posts (author_id,author_name,category,title,content,is_npc) VALUES (%s,%s,%s,%s,%s,1)",
        (bot["colony_id"], bot["colony_name"], cat, title, content))
    post_id = cur.lastrowid
    await apply_forum_influence(cur, post_id, cat, title, content, bot["colony_id"])

async def npc_craft(cur, bot):
    if bot["minerals"] >= 50 and bot["energy"] >= 20:
        recipe = random.choice(["rare_metals","crystals","plasma"])
        r = CRAFT_RECIPES[recipe]
        can = all(bot.get(res, 0) >= need for res, need in r["inputs"].items())
        if can:
            for res, need in r["inputs"].items():
                await db_exec(cur, f"UPDATE colonies SET {res}={res}-%s WHERE id=%s", (need, bot["colony_id"]))
            await db_exec(cur, f"UPDATE colonies SET {recipe}={recipe}+%s WHERE id=%s", (r["output"], bot["colony_id"]))

async def npc_attack(cur, bot):
    pers = NPC_PERSONALITIES.get(bot.get("personality","trader"), NPC_PERSONALITIES["trader"])
    if pers["style"] not in ["豪爽","精明"] and random.random() > 0.3: return
    targets = await db_query(cur, "SELECT id FROM colonies WHERE id!=%s ORDER BY RAND() LIMIT 3", (bot["colony_id"],))
    for t in targets:
        defender = await db_one(cur, "SELECT defense_power FROM colonies WHERE id=%s", (t["id"],))
        if bot["attack_power"] > defender["defense_power"] * 0.8:
            await attack(AttackModel(target_id=t["id"]), uid=bot["user_id"])
            break

async def npc_philosophy(cur, bot):
    philos = await db_query(cur, "SELECT * FROM philosophy_config ORDER BY RAND() LIMIT 1")
    for p in philos:
        cp = await db_one(cur, "SELECT * FROM colony_philosophy WHERE colony_id=%s AND philosophy_type=%s", (bot["colony_id"], p["philosophy_type"]))
        lvl = (cp["level"] if cp else 0) + 1
        if lvl <= p["max_level"]:
            cost = int(p["cost_gold_base"]*lvl)
            if bot["gold"] >= cost:
                await db_exec(cur, "UPDATE colonies SET gold=gold-%s,culture=culture+%s WHERE id=%s", (cost, lvl*5, bot["colony_id"]))
                await db_exec(cur, "INSERT INTO colony_philosophy (colony_id,philosophy_type,level) VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE level=%s",
                    (bot["colony_id"], p["philosophy_type"], lvl, lvl))
                break

async def npc_capture_territory(cur, bot):
    """NPC占领领地"""
    free = await db_query(cur, "SELECT id FROM territories WHERE owner_colony IS NULL AND is_active=1 ORDER BY RAND() LIMIT 3")
    for t in free:
        await db_exec(cur, "UPDATE territories SET owner_colony=%s, captured_at=NOW() WHERE id=%s AND owner_colony IS NULL", (bot["colony_id"], t["id"]))
        break

async def npc_research(cur, bot):
    """NPC研究科技"""
    techs = await db_query(cur, "SELECT * FROM tech_config ORDER BY RAND() LIMIT 1")
    for tc in techs:
        t = await db_one(cur, "SELECT * FROM techs WHERE colony_id=%s AND tech_type=%s", (bot["colony_id"], tc["tech_type"]))
        lvl = (t["level"] if t else 0) + 1
        if lvl <= tc["max_level"] and bot["gold"] >= tc.get("cost_gold",0)*lvl:
            cost = int(tc.get("cost_gold",0)*lvl)
            if bot["gold"] >= cost and bot["minerals"] >= tc["cost_minerals_per_level"]*lvl:
                await db_exec(cur, "UPDATE colonies SET gold=gold-%s,minerals=minerals-%s WHERE id=%s", (cost, int(tc["cost_minerals_per_level"]*lvl), bot["colony_id"]))
                await db_exec(cur, "INSERT INTO techs (colony_id,tech_type,level) VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE level=%s",
                    (bot["colony_id"], tc["tech_type"], lvl, lvl))
                break

# ============================================================
#  后台任务：NPC聊天灌水
# ============================================================
async def bg_npc_chat():
    await asyncio.sleep(25)
    while True:
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    npcs = await db_query(cur, """SELECT n.*, c.id as colony_id, c.name as colony_name, c.minerals, c.energy, c.food, c.gold
                        FROM npc_bots n JOIN users u ON n.user_id=u.id JOIN colonies c ON c.user_id=u.id WHERE n.is_active=1""")
                    if not npcs:
                        await asyncio.sleep(10)
                        continue
                    speakers = random.sample(npcs, min(random.randint(1,2), len(npcs)))
                    for bot in speakers:
                        pers = NPC_PERSONALITIES.get(bot.get("personality","trader"), NPC_PERSONALITIES["trader"])
                        if random.random() > pers["chat_freq"]:
                            continue
                        phrase = random.choice(pers["phrases"])
                        resources = ["矿物","能量","食物","稀有金属","水晶","等离子体"]
                        stocks_list = ["星际矿业","量子银行","光能科技","芯片国际"]
                        sectors = ["仙女座","猎户臂","半人马座","天琴座"]
                        factions_list = ["星河联邦","暗影军团","知识圣殿","自由联盟"]
                        techs = ["量子计算","暗物质采集","纳米材料","反物质引擎"]
                        phrase = phrase.replace("{resource}", random.choice(resources))
                        phrase = phrase.replace("{stock}", random.choice(stocks_list))
                        phrase = phrase.replace("{sector}", random.choice(sectors))
                        phrase = phrase.replace("{faction}", random.choice(factions_list))
                        phrase = phrase.replace("{tech}", random.choice(techs))
                        phrase = phrase.replace("{spec}", random.choice(["军事","经济","文化","科研"]))
                        phrase = phrase.replace("{enemy}", random.choice(["星盗","暗影","异形"]))
                        phrase = phrase.replace("{amount}", str(random.randint(100,5000)))
                        phrase = phrase.replace("{count}", str(random.randint(1,10)))

                        if random.random() < 0.4:
                            topic = random.choice(NPC_CHAT_TOPICS)
                            topic = topic.replace("{resource}", random.choice(resources))
                            topic = topic.replace("{sector}", random.choice(sectors))
                            topic = topic.replace("{faction}", random.choice(factions_list))
                            topic = topic.replace("{tech}", random.choice(techs))
                            topic = topic.replace("{spec}", random.choice(["军事","经济","文化","科研"]))
                            topic = topic.replace("{enemy}", random.choice(["星盗","暗影","异形"]))
                            phrase = topic

                        prefix = pers["emoji"]
                        msg = f"{prefix} {phrase}"

                        await db_exec(cur, "INSERT INTO chat_messages (colony_id,author_name,message,is_npc) VALUES (%s,%s,%s,1)",
                            (bot["colony_id"], bot["colony_name"], msg))
        except Exception as e:
            log.error(f"NPC chat error: {e}")
        await asyncio.sleep(random.randint(5, 15))

# ============================================================
#  后台任务：上帝AI
# ============================================================
async def bg_god_ai():
    """上帝AI：维护游戏世界平衡"""
    await asyncio.sleep(60)
    while True:
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    action = random.choices(
                        ["balance_economy","weather_event","fix_data","market_intervention","stock_event","reward_active"],
                        weights=[25,20,15,20,10,10]
                    )[0]
                    desc = await execute_god_action(cur, action)
                    await db_exec(cur, "INSERT INTO god_ai_log (action_type,description) VALUES (%s,%s)", (action, desc))
                    log.info(f"上帝AI: [{action}] {desc}")
        except Exception as e:
            log.error(f"God AI error: {e}")
        await asyncio.sleep(random.randint(120, 300))

# ============================================================
#  V7: 后台任务：股票IPO/退市
# ============================================================
async def bg_stock_ipo_delist():
    """每24小时运行一次：IPO新股票或退市旧股票"""
    await asyncio.sleep(120)
    while True:
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    # 30%概率IPO
                    if random.random() < 0.3:
                        prefix = random.choice(STOCK_PREFIXES)
                        suffix = random.choice(STOCK_SUFFIXES)
                        stock_name = prefix + suffix
                        # 生成唯一代码
                        code_num = random.randint(100000, 999999)
                        stock_code = f"SH{code_num}"
                        # 检查代码是否已存在
                        existing = await db_one(cur, "SELECT id FROM stocks WHERE code=%s", (stock_code,))
                        if existing:
                            code_num = random.randint(100000, 999999)
                            stock_code = f"SH{code_num}"
                        sector = random.choice(SECTORS)
                        ipo_price = round(random.uniform(10, 500), 2)
                        await db_exec(cur, """INSERT INTO stocks (code,name,sector,current_price,prev_close,open_price,high_price,low_price,change_amt,change_pct,volume,turnover,is_active)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0,0,0,0,1)""",
                            (stock_code, stock_name, sector, ipo_price, ipo_price, ipo_price, ipo_price, ipo_price))
                        await db_exec(cur, "INSERT INTO stock_ipo_log (stock_code,stock_name,ipo_price,ipo_date,status) VALUES (%s,%s,%s,%s,'listed')",
                            (stock_code, stock_name, ipo_price, date.today().isoformat()))
                        log.info(f"V7 IPO: {stock_name}({stock_code}) 上市价{ipo_price}")

                    # 10%概率退市
                    if random.random() < 0.1:
                        # 找7天前上市且交易量低的股票
                        old_stocks = await db_query(cur, """SELECT s.code, s.name, s.volume, sil.ipo_date FROM stocks s
                            JOIN stock_ipo_log sil ON s.code = sil.stock_code
                            WHERE s.is_active=1 AND sil.ipo_date <= DATE_SUB(CURDATE(), INTERVAL 7 DAY) AND s.volume < 1000
                            ORDER BY RAND() LIMIT 1""")
                        for s in old_stocks:
                            await db_exec(cur, "UPDATE stocks SET is_active=0 WHERE code=%s", (s["code"],))
                            await db_exec(cur, "UPDATE stock_ipo_log SET status='delisted' WHERE stock_code=%s", (s["code"],))
                            # 通知持仓用户
                            holders = await db_query(cur, "SELECT DISTINCT colony_id FROM stock_portfolios WHERE stock_code=%s AND amount>0", (s["code"],))
                            for h in holders:
                                await add_notification(cur, h["colony_id"], "股票退市", f"【{s['name']}】({s['code']})已被退市", "danger")
                            log.info(f"V7 Delist: {s['name']}({s['code']}) 退市")
        except Exception as e:
            log.error(f"Stock IPO/Delist error: {e}")
        await asyncio.sleep(86400)  # 24小时

# ============ V8: 战争纪元 后台任务 ============
async def bg_arena_scheduler():
    """每1小时：管理竞技场赛事"""
    await asyncio.sleep(120)
    while True:
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    today = date.today().isoformat()
                    # 创建每日赛事(如果不存在)
                    existing = await db_one(cur, "SELECT id FROM arena_tournaments WHERE tournament_type='daily' AND DATE(created_at)=%s", (today,))
                    if not existing:
                        await db_exec(cur, """INSERT INTO arena_tournaments (name,tournament_type,tier,max_participants,entry_fee,prize_pool,status)
                            VALUES (%s,'daily','open',32,100,1000,'upcoming')""", (f"每日竞技赛{today}",))
                    # 每周赛(周一)
                    if date.today().weekday() == 0:
                        week_existing = await db_one(cur, "SELECT id FROM arena_tournaments WHERE tournament_type='weekly' AND DATE(created_at)=%s", (today,))
                        if not week_existing:
                            await db_exec(cur, """INSERT INTO arena_tournaments (name,tournament_type,tier,max_participants,entry_fee,prize_pool,status)
                                VALUES (%s,'weekly','veteran',64,500,5000,'upcoming')""", (f"周冠军赛{today}",))
                    # 自动执行已满的赛事
                    upcoming = await db_query(cur, """SELECT t.*, (SELECT COUNT(*) FROM arena_participants WHERE tournament_id=t.id) as p_count
                        FROM arena_tournaments t WHERE t.status='upcoming'""")
                    for t in upcoming:
                        cnt = t["p_count"] or 0
                        if cnt >= 4:  # 至少4人开赛
                            # 简化版比赛: 两两配对PK
                            participants = await db_query(cur, """SELECT ap.colony_id, c.name, c.attack_power, c.defense_power, c.arena_rating
                                FROM arena_participants ap JOIN colonies c ON ap.colony_id=c.id
                                WHERE ap.tournament_id=%s AND ap.is_eliminated=0 ORDER BY c.arena_rating DESC""", (t["id"],))
                            if len(participants) < 2:
                                continue
                            await db_exec(cur, "UPDATE arena_tournaments SET status='active', started_at=NOW() WHERE id=%s", (t["id"],))
                            # 生成对阵
                            round_num = 1
                            for i in range(0, len(participants)-1, 2):
                                a, b = participants[i], participants[i+1]
                                a_total = a["attack_power"] * (1 + random.uniform(-0.15, 0.15))
                                b_total = b["defense_power"] * (1 + random.uniform(-0.15, 0.15))
                                winner = a if a_total > b_total else b
                                loser = b if winner["colony_id"] == a["colony_id"] else a
                                await db_exec(cur, """INSERT INTO arena_matches (tournament_id,round_num,colony_a,colony_b,winner_id,result_json,fought_at)
                                    VALUES (%s,%s,%s,%s,%s,%s,NOW())""",
                                    (t["id"], round_num, a["colony_id"], b["colony_id"], winner["colony_id"],
                                     json.dumps({"a_atk": round(a_total), "b_def": round(b_total)})))
                                await db_exec(cur, "UPDATE arena_participants SET wins=wins+1 WHERE tournament_id=%s AND colony_id=%s", (t["id"], winner["colony_id"]))
                                await db_exec(cur, "UPDATE arena_participants SET losses=losses+1, is_eliminated=1 WHERE tournament_id=%s AND colony_id=%s", (t["id"], loser["colony_id"]))
                                # ELO更新
                                elo_change = 30 if winner["arena_rating"] < loser["arena_rating"] else 15
                                await db_exec(cur, "UPDATE colonies SET arena_rating=arena_rating+%s WHERE id=%s", (elo_change, winner["colony_id"]))
                                await db_exec(cur, "UPDATE colonies SET arena_rating=GREATEST(0,arena_rating-%s) WHERE id=%s", (elo_change // 2, loser["colony_id"]))
                            # 赛事完成
                            champion = participants[0] if participants else None
                            if champion:
                                prize = t["prize_pool"]
                                await db_exec(cur, "UPDATE colonies SET gold=gold+%s WHERE id=%s", (prize, champion["colony_id"]))
                                await add_notification(cur, champion["colony_id"], "🏆 竞技场冠军!", f"赢得{t['name']}! 奖金{prize}金!", "success")
                            await db_exec(cur, "UPDATE arena_tournaments SET status='completed', completed_at=NOW() WHERE id=%s", (t["id"],))
                            log.info(f"V8 Arena: 赛事{t['id']}完成, 冠军:{champion['name'] if champion else 'None'}")
        except Exception as e:
            log.error(f"Arena scheduler error: {e}")
        await asyncio.sleep(3600)

async def bg_war_score_decay():
    """每6小时：检查战争超时自动结束"""
    await asyncio.sleep(300)
    while True:
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    wars = await db_query(cur, """SELECT * FROM faction_wars WHERE status='active'
                        AND started_at < DATE_SUB(NOW(), INTERVAL 14 DAY)""")
                    for war in wars:
                        winner = "attacker" if war["attacker_score"] >= war["defender_score"] else "defender"
                        if war["attacker_score"] >= 500:
                            winner = "attacker"
                        elif war["defender_score"] >= 500:
                            winner = "defender"
                        await db_exec(cur, "UPDATE faction_wars SET status='ended', ended_at=NOW() WHERE id=%s", (war["id"],))
                        # 奖惩
                        win_fid = war[f"{winner}_faction"]
                        lose_fid = war["defender_faction"] if winner == "attacker" else war["attacker_faction"]
                        await db_exec(cur, "UPDATE colonies SET gold=gold+500 WHERE id IN (SELECT colony_id FROM colony_factions WHERE faction_id=%s)", (win_fid,))
                        await db_exec(cur, "UPDATE colonies SET gold=GREATEST(0,gold-200) WHERE id IN (SELECT colony_id FROM colony_factions WHERE faction_id=%s)", (lose_fid,))
                        # 通知
                        win_members = await db_query(cur, "SELECT colony_id FROM colony_factions WHERE faction_id=%s", (win_fid,))
                        for m in win_members:
                            await add_notification(cur, m["colony_id"], "🎉 战争胜利!", "派系战争胜利! 全体+500金!", "success")
                        lose_members = await db_query(cur, "SELECT colony_id FROM colony_factions WHERE faction_id=%s", (lose_fid,))
                        for m in lose_members:
                            await add_notification(cur, m["colony_id"], "💀 战争失败", "派系战争失败! -200金", "danger")
                        # 战争结束影响股市
                        await db_exec(cur, "UPDATE stocks SET change_pct=change_pct+2 WHERE sector IN (SELECT sector FROM stocks WHERE is_active=1) AND is_active=1 LIMIT 5")
                        log.info(f"V8 War: 战争{war['id']}结束, 胜方:{win_fid}")
        except Exception as e:
            log.error(f"War score decay error: {e}")
        await asyncio.sleep(21600)

async def bg_bounty_expiry():
    """每12小时：过期赏金自动关闭"""
    await asyncio.sleep(300)
    while True:
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    expired = await db_query(cur, "SELECT * FROM bounties WHERE status='active' AND expires_at < NOW()")
                    for b in expired:
                        await db_exec(cur, "UPDATE bounties SET status='expired' WHERE id=%s", (b["id"],))
                        # 退还50%给发布者
                        refund = int(b["amount"] * 0.5)
                        await db_exec(cur, "UPDATE colonies SET gold=gold+%s WHERE id=%s", (refund, b["placer_id"]))
                        await add_notification(cur, b["placer_id"], "💀 悬赏过期", f"悬赏已过期，退还{refund}金", "info")
        except Exception as e:
            log.error(f"Bounty expiry error: {e}")
        await asyncio.sleep(43200)

# ============================================================
#  其他后台任务（保持不变）
# ============================================================
async def bg_territory_refresh():
    await asyncio.sleep(10)
    while True:
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await db_exec(cur, "UPDATE territories SET is_active=0 WHERE expires_at < NOW()")
                    names = ["极光星","暗影卫星","水晶洞穴","熔岩高地","冰冻荒原","翡翠森林","沙漠绿洲","天空之城","深海之渊","遗忘之地","量子矿脉","等离子风暴"]
                    types = ["terran","gas","ice","volcanic","desert","oceanic"]
                    for i in range(3):
                        name = random.choice(names)+str(random.randint(1,99))
                        await db_exec(cur, "INSERT INTO territories (name,planet_type,bonus_minerals,bonus_energy,bonus_food,bonus_score,expires_at) VALUES (%s,%s,%s,%s,%s,%s,DATE_ADD(NOW(),INTERVAL 6 HOUR))",
                            (name, random.choice(types), random.randint(10,50), random.randint(10,50), random.randint(10,50), random.randint(20,100)))
        except Exception as e:
            log.error(f"Territory refresh error: {e}")
        await asyncio.sleep(6*3600)

async def bg_territory_income():
    await asyncio.sleep(120)
    while True:
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    owned = await db_query(cur, """SELECT t.owner_colony, SUM(t.bonus_minerals) as total_m, 
                        SUM(t.bonus_energy) as total_e, SUM(t.bonus_food) as total_f, SUM(t.bonus_score) as total_s
                        FROM territories t WHERE t.owner_colony IS NOT NULL AND t.is_active=1 GROUP BY t.owner_colony""")
                    for o in owned:
                        m = o["total_m"] or 0; e = o["total_e"] or 0; f = o["total_f"] or 0; g = (o["total_s"] or 0) * 2
                        if m or e or f or g:
                            await db_exec(cur, "UPDATE colonies SET minerals=minerals+%s,energy=energy+%s,food=food+%s,gold=gold+%s WHERE id=%s",
                                (m, e, f, g, o["owner_colony"]))
        except Exception as e:
            log.error(f"Territory income error: {e}")
        await asyncio.sleep(1800)

async def bg_daily_event():
    await asyncio.sleep(30)
    while True:
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    today = date.today().isoformat()
                    ex = await db_one(cur, "SELECT id FROM daily_events WHERE event_date=%s", (today,))
                    if ex:
                        await asyncio.sleep(3600); continue
                    events = [
                        ("繁荣","星际贸易繁荣","各殖民地资源产出提升！",30,20,10,50,0,0,None,0),
                        ("危机","陨石群来袭","陨石群正在接近！防御准备！",0,0,0,-10,0,-5,"minerals",-5),
                        ("发现","远古遗迹发现","发现了远古文明的遗迹！",0,0,0,100,0,0,None,0),
                        ("牛市","市场利好消息","资源价格大幅上涨！",0,0,0,0,100,0,"minerals",15),
                        ("熊市","经济衰退警告","资源价格下跌！",0,0,0,0,0,-5,"energy",-10),
                        ("科技","量子跃迁突破","研究效率大幅提升！",20,20,20,50,0,0,None,0),
                    ]
                    evt = random.choice(events)
                    await db_exec(cur, """INSERT INTO daily_events (event_date,event_type,title,description,effect_minerals,effect_energy,effect_food,effect_score,effect_gold,effect_happiness,effect_market,effect_market_pct)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (today, evt[0], evt[1], evt[2], evt[3], evt[4], evt[5], evt[6], evt[7], evt[8], evt[9], evt[10]))
                    colonies = await db_query(cur, "SELECT id FROM colonies")
                    for c in colonies:
                        em,ee,ef,es,eg,eh = evt[3],evt[4],evt[5],evt[6],evt[7],evt[8]
                        if em or ee or ef or es or eg or eh:
                            await db_exec(cur, "UPDATE colonies SET minerals=GREATEST(minerals+%s,0),energy=GREATEST(energy+%s,0),food=GREATEST(food+%s,0),score=GREATEST(score+%s,0),gold=GREATEST(gold+%s,0),happiness=GREATEST(LEAST(happiness+%s,100),0) WHERE id=%s",
                                (em,ee,ef,es,eg,eh,c["id"]))
                        await add_notification(cur, c["id"], f"今日事件：{evt[1]}", evt[2], "event")
                    if evt[9] and evt[10]:
                        direction = 1 + evt[10]/100
                        await db_exec(cur, f"UPDATE resource_prices SET current_price=LEAST(max_price, GREATEST(min_price, ROUND(current_price*%s))) WHERE resource_type=%s", (direction, evt[9]))
        except Exception as e:
            log.error(f"Daily event error: {e}")
        await asyncio.sleep(3600)

async def bg_expedition_check():
    await asyncio.sleep(60)
    while True:
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    exps = await db_query(cur, """SELECT * FROM expeditions WHERE status='exploring'
                        AND started_at IS NOT NULL AND TIMESTAMPDIFF(MINUTE, started_at, NOW()) >= duration_hours*60""")
                    for exp in exps:
                        rewards = {
                            "reward_minerals": random.randint(50,200)*exp["fleet_size"],
                            "reward_energy": random.randint(30,150)*exp["fleet_size"],
                            "reward_food": random.randint(20,100)*exp["fleet_size"],
                            "reward_gold": random.randint(50,300)*exp["fleet_size"],
                            "reward_score": random.randint(10,50)*exp["fleet_size"]
                        }
                        discoveries = ["发现了稀有矿脉！","遇到了友善的外星文明！","找到了远古科技遗迹！","安全返回，收获颇丰！","发现了一颗宜居行星！"]
                        reward_desc = random.choice(discoveries)
                        await db_exec(cur, """UPDATE expeditions SET status='completed', reward_minerals=%s, reward_energy=%s, reward_food=%s, reward_gold=%s, reward_score=%s, reward_discovery=%s, completed_at=NOW() WHERE id=%s""",
                            (rewards["reward_minerals"], rewards["reward_energy"], rewards["reward_food"], rewards["reward_gold"], rewards["reward_score"], reward_desc, exp["id"]))
                        await db_exec(cur, "UPDATE colonies SET minerals=minerals+%s,energy=energy+%s,food=food+%s,gold=gold+%s,score=score+%s WHERE id=%s",
                            (rewards["reward_minerals"], rewards["reward_energy"], rewards["reward_food"], rewards["reward_gold"], rewards["reward_score"], exp["colony_id"]))
                        await add_notification(cur, exp["colony_id"], "探索完成！", f"舰队从{exp['target_sector']}返回，{reward_desc}", "success")
        except Exception as e:
            log.error(f"Expedition check error: {e}")
        await asyncio.sleep(300)

async def bg_daily_task_generator():
    await asyncio.sleep(45)
    while True:
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    today = date.today().isoformat()
                    existing = await db_one(cur, "SELECT id FROM daily_tasks WHERE task_date=%s LIMIT 1", (today,))
                    if existing:
                        await asyncio.sleep(3600); continue
                    task_templates = [
                        ("trade_1", "完成1笔交易", "在资源市场或股票市场完成1笔交易", 1, 50, 10),
                        ("trade_5", "完成5笔交易", "完成5笔任意交易", 5, 200, 30),
                        ("build_1", "建造1座建筑", "建造或升级1座建筑", 1, 100, 15),
                        ("collect", "收取挂机资源", "收取一次挂机产出", 1, 80, 10),
                        ("explore", "派遣1次探索", "派遣舰队进行1次星际探索", 1, 150, 20),
                        ("stock_buy", "买入1只股票", "在股票市场买入任意股票", 1, 100, 15),
                        ("philosophy", "研究1次哲学", "进行1次哲学研究", 1, 120, 15),
                        ("post", "论坛发帖", "在论坛发表1篇帖子", 1, 80, 10),
                        ("battle", "发起1次攻击", "攻击其他殖民地1次", 1, 100, 20),
                    ]
                    selected = random.sample(task_templates, min(5, len(task_templates)))
                    for tt in selected:
                        await db_exec(cur, """INSERT IGNORE INTO daily_tasks (task_date,task_type,title,description,target_value,reward_gold,reward_score)
                            VALUES (%s,%s,%s,%s,%s,%s,%s)""", (today, tt[0], tt[1], tt[2], tt[3], tt[4], tt[5]))
        except Exception as e:
            log.error(f"Daily task generator error: {e}")
        await asyncio.sleep(3600)

async def bg_achievement_checker():
    await asyncio.sleep(120)
    while True:
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    colonies = await db_query(cur, "SELECT id, user_id FROM colonies LIMIT 100")
                    for c in colonies:
                        try:
                            await check_achievements(cur, c["id"], c["user_id"])
                        except: pass
        except Exception as e:
            log.error(f"Achievement checker error: {e}")
        await asyncio.sleep(600)

async def bg_faction_mission_refresh():
    await asyncio.sleep(60)
    while True:
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    today = date.today().isoformat()
                    factions = await db_query(cur, "SELECT id FROM factions")
                    mission_templates = [
                        ("trade", "派系交易任务", "成员完成10笔交易", 10, 200, 100, 20),
                        ("build", "派系建设任务", "成员建造5座建筑", 5, 150, 80, 15),
                        ("explore", "派系探索任务", "成员完成3次探索", 3, 300, 120, 25),
                        ("battle", "派系战斗任务", "成员赢得3场战斗", 3, 250, 150, 30),
                        ("donate", "派系捐献任务", "成员累计捐献100资源", 100, 100, 50, 10),
                    ]
                    for f in factions:
                        existing = await db_one(cur, "SELECT id FROM faction_missions WHERE faction_id=%s AND task_date=%s LIMIT 1", (f["id"], today))
                        if existing: continue
                        selected = random.sample(mission_templates, min(3, len(mission_templates)))
                        for mt in selected:
                            await db_exec(cur, """INSERT INTO faction_missions (faction_id,mission_type,title,description,target_value,reward_gold,reward_score,reward_faction_pts,task_date)
                                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""", (f["id"], mt[0], mt[1], mt[2], mt[3], mt[4], mt[5], mt[6], today))
        except Exception as e:
            log.error(f"Faction mission refresh error: {e}")
        await asyncio.sleep(3600)

async def bg_npc_forum_post():
    await asyncio.sleep(30)
    while True:
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    npcs = await db_query(cur, """SELECT n.*, u.username, c.id as colony_id, c.name as colony_name, c.minerals, c.energy, c.food, c.gold,
                        c.attack_power, c.defense_power, c.score
                        FROM npc_bots n JOIN users u ON n.user_id=u.id JOIN colonies c ON c.user_id=u.id WHERE n.is_active=1""")
                    if npcs:
                        bot = random.choice(npcs)
                        await npc_post(cur, bot)
                        if random.random() < 0.5:
                            hot_posts = await db_query(cur, "SELECT id FROM forum_posts WHERE like_count>3 ORDER BY created_at DESC LIMIT 5")
                            if hot_posts:
                                pid = random.choice(hot_posts)["id"]
                                pers = NPC_PERSONALITIES.get(bot.get("personality","trader"), NPC_PERSONALITIES["trader"])
                                reply_map = {
                                    "trader": ["有道理，不过从交易角度看...", "同意，行情确实如此", "我持不同意见，数据说话", "这个分析不错，参考一下"],
                                    "miner": ["嗯", "说得对", "了解了", "矿工路过"],
                                    "scholar": ["从学术角度来看，这个观点值得深入研究", "数据支持这个结论", "建议补充更多实验数据", "这个理论框架可以进一步优化"],
                                    "warrior": ["说得好！简单直接！", "废话少说，来打一架", "武力才能解决问题", "战场上见真章"],
                                    "merchant": ["好帖！顶一个！", "商机无限啊！", "我也有同感", "大家合作共赢！"],
                                }
                                replies = reply_map.get(bot.get("personality","trader"), ["有道理","同意","不错"])
                                await db_exec(cur, "INSERT INTO forum_replies (post_id,author_id,author_name,content,is_npc) VALUES (%s,%s,%s,%s,1)",
                                    (pid, bot["colony_id"], bot["colony_name"], random.choice(replies)))
                                await db_exec(cur, "UPDATE forum_posts SET reply_count=reply_count+1 WHERE id=%s", (pid,))
        except Exception as e:
            log.error(f"NPC forum post error: {e}")
        await asyncio.sleep(20)

async def bg_forum_influence():
    await asyncio.sleep(180)
    while True:
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await db_exec(cur, "DELETE FROM forum_influence WHERE expires_at IS NOT NULL AND expires_at < NOW()")
                    hot = await db_query(cur, "SELECT id, category, like_count FROM forum_posts WHERE like_count >= 5 AND created_at > DATE_SUB(NOW(), INTERVAL 1 HOUR) ORDER BY like_count DESC LIMIT 3")
                    for p in hot:
                        if p["category"] == "trade" and random.random() < 0.3:
                            rt = random.choice(["minerals","energy","food"])
                            await db_exec(cur, "UPDATE resource_prices SET current_price=LEAST(max_price, current_price+%s) WHERE resource_type=%s", (random.randint(1,2), rt))
        except Exception as e:
            log.error(f"Forum influence error: {e}")
        await asyncio.sleep(300)

# 静态文件
app.mount("/", StaticFiles(directory="/app/static", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
