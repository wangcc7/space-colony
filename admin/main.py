"""
星际殖民地 V7 - 管理后台 (端口58018)
功能：数据看板、API Key管理、模型配置、NPC管理、股票管理、
      市场干预、论坛管理、派系管理、用户管理、全局配置、
      上帝AI管理、数据修改、IPO日历
认证：简单用户名密码 + JWT
"""

import asyncio, json, random, hashlib, time, logging, os
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from typing import Optional, List

import aiomysql
import jwt
import bcrypt
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel

# ======================== 配置 ========================
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "space-colony-admin-v4-2026")
ALGO = "HS256"
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin888")

DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER", "game")
DB_PASS = os.getenv("DB_PASS", "gamepass")
DB_NAME = os.getenv("DB_NAME", "spacecolony")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("admin")

# ======================== 数据库 ========================
pool = None

async def get_db():
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            yield conn, cur

async def db_exec(cur, sql, args=()):
    await cur.execute(sql, args)
    return cur

async def db_query(cur, sql, args=()):
    await cur.execute(sql, args)
    return await cur.fetchall()

async def db_one(cur, sql, args=()):
    await cur.execute(sql, args)
    return await cur.fetchone()

# ======================== Auth ========================
def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt(4)).decode()

def make_admin_token() -> str:
    return jwt.encode({"role": "admin", "exp": time.time() + 86400}, ADMIN_SECRET, algorithm=ALGO)

def verify_admin(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "请先登录管理后台")
    try:
        data = jwt.decode(authorization[7:], ADMIN_SECRET, algorithms=[ALGO])
        if data.get("role") != "admin":
            raise HTTPException(401, "权限不足")
        return data
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "登录已过期，请重新登录")
    except:
        raise HTTPException(401, "无效的认证令牌")

# ======================== Models ========================
class LoginReq(BaseModel):
    username: str
    password: str

class APIKeyReq(BaseModel):
    provider: str
    key_name: str
    api_key: str
    api_base: str = ""
    is_active: bool = True

class ModelConfigReq(BaseModel):
    provider: str
    model_name: str
    model_id: str
    api_url: str = ""
    api_key: str = ""
    max_tokens: int = 2048
    temperature: float = 0.8
    is_default: bool = False

class NPCReq(BaseModel):
    username: str
    colony_name: str
    personality: str = "balanced"
    difficulty: int = 3
    trade_freq: int = 300
    model_name: str = ""
    system_prompt: str = ""
    is_active: bool = True

class StockReq(BaseModel):
    code: str
    name: str
    sector: str = "综合"
    initial_price: float = 100.0
    description: str = ""

class MarketInterventionReq(BaseModel):
    stock_code: str
    action: str  # push_up / push_down / stabilize / halt
    amount: int = 10000

class ForumManageReq(BaseModel):
    post_id: int
    action: str  # pin / unpin / delete

class FactionManageReq(BaseModel):
    faction_id: int
    action: str  # disband / rename
    new_name: str = ""

class GlobalConfigReq(BaseModel):
    config_key: str
    config_value: str

class UserManageReq(BaseModel):
    user_id: int
    action: str  # ban / unban / modify_gold / modify_resources / reset_password / delete
    value: str = ""  # 通用值字段

class GodAIActionReq(BaseModel):
    action: str  # balance_economy, weather_event, fix_data, market_intervention, stock_event, reward_active

class ModifyDataReq(BaseModel):
    table_name: str
    row_id: int
    field: str
    value: str

# ======================== App ========================
@asynccontextmanager
async def lifespan(app):
    global pool
    for attempt in range(30):
        try:
            pool = await aiomysql.create_pool(
                host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS,
                db=DB_NAME, maxsize=10, charset="utf8mb4", autocommit=True,
                init_command="SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            break
        except Exception as e:
            log.warning(f"Admin DB连接失败({attempt+1}/30): {e}")
            await asyncio.sleep(2)
    log.info("Admin DB connected")
    await ensure_admin_tables()
    log.info("Admin tables ready")
    yield
    pool.close()
    await pool.wait_closed()

app = FastAPI(title="星际殖民地管理后台 V7", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

async def ensure_admin_tables():
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS admin_api_keys (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    provider VARCHAR(32) NOT NULL,
                    key_name VARCHAR(64) NOT NULL,
                    api_key VARCHAR(256) NOT NULL,
                    api_base VARCHAR(256) DEFAULT '',
                    is_active TINYINT(1) DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS admin_model_config (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    provider VARCHAR(32) NOT NULL,
                    model_name VARCHAR(64) NOT NULL,
                    model_id VARCHAR(128) NOT NULL,
                    api_url VARCHAR(256) DEFAULT '',
                    api_key VARCHAR(256) DEFAULT '',
                    max_tokens INT DEFAULT 2048,
                    temperature FLOAT DEFAULT 0.8,
                    is_default TINYINT(1) DEFAULT 0,
                    is_active TINYINT(1) DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS admin_global_config (
                    config_key VARCHAR(64) NOT NULL PRIMARY KEY,
                    config_value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            # V7: god_ai_log 表
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS god_ai_log (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    action_type VARCHAR(64) NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            # 添加is_banned列到users表
            try:
                await cur.execute("ALTER TABLE users ADD COLUMN is_banned TINYINT(1) DEFAULT 0")
            except: pass
            # 添加model_name列到npc_bots表
            try:
                await cur.execute("ALTER TABLE npc_bots ADD COLUMN model_name VARCHAR(128) DEFAULT ''")
            except: pass
            await cur.execute("""
                INSERT IGNORE INTO admin_global_config (config_key, config_value) VALUES
                ('market_open_time', '09:30'),
                ('market_close_time', '15:00'),
                ('daily_reset_time', '00:00'),
                ('max_leverage', '10'),
                ('stamp_tax_rate', '0.001'),
                ('commission_rate', '0.0003'),
                ('price_limit_pct', '10'),
                ('npc_count', '7'),
                ('game_speed', '1'),
                ('allow_short_selling', 'true')
            """)
            # 确保DeepSeek默认模型存在
            existing = await db_one(cur, "SELECT id FROM ai_model_configs WHERE provider='deepseek' LIMIT 1")
            if not existing:
                await cur.execute("""INSERT INTO ai_model_configs (provider,name,api_url,api_key,model_name,max_tokens,temperature,is_default,is_active)
                    VALUES ('deepseek','DeepSeek','https://api.deepseek.com/v1/chat/completions','sk-c062cc051eb246a99a4cda527b48ae87','deepseek-chat',2048,0.7,1,1)""")
                log.info("DeepSeek默认模型已插入ai_model_configs")
            # 同步到admin_model_config
            existing_admin = await db_one(cur, "SELECT id FROM admin_model_config WHERE provider='deepseek' LIMIT 1")
            if not existing_admin:
                await cur.execute("""INSERT INTO admin_model_config (provider,model_name,model_id,api_url,api_key,max_tokens,temperature,is_default,is_active)
                    VALUES ('deepseek','DeepSeek','deepseek-chat','https://api.deepseek.com/v1/chat/completions','sk-c062cc051eb246a99a4cda527b48ae87',2048,0.7,1,1)""")
                log.info("DeepSeek默认模型已插入admin_model_config")

# ======================== 根路由 ========================
@app.get("/")
async def root():
    return RedirectResponse(url="/admin")

# ======================== 认证 ========================
@app.post("/admin/api/login")
async def admin_login(req: LoginReq):
    if req.username != ADMIN_USERNAME or req.password != ADMIN_PASSWORD:
        raise HTTPException(401, "用户名或密码错误")
    return {"access_token": make_admin_token(), "msg": "登录成功"}

@app.get("/admin/api/check")
async def check_auth(_=Depends(verify_admin)):
    return {"status": "ok", "role": "admin"}

# ======================== API Key管理 ========================
@app.get("/admin/api/api-keys")
async def list_api_keys(_=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            keys = await db_query(cur, "SELECT * FROM admin_api_keys ORDER BY created_at DESC")
            return {"keys": keys}

@app.post("/admin/api/api-keys")
async def create_api_key(req: APIKeyReq, _=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await db_exec(cur, "INSERT INTO admin_api_keys (provider,key_name,api_key,api_base,is_active) VALUES (%s,%s,%s,%s,%s)",
                         (req.provider, req.key_name, req.api_key, req.api_base, 1 if req.is_active else 0))
            return {"msg": "API Key添加成功", "id": cur.lastrowid}

@app.put("/admin/api/api-keys/{key_id}")
async def update_api_key(key_id: int, req: APIKeyReq, _=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await db_exec(cur, "UPDATE admin_api_keys SET provider=%s,key_name=%s,api_key=%s,api_base=%s,is_active=%s WHERE id=%s",
                         (req.provider, req.key_name, req.api_key, req.api_base, 1 if req.is_active else 0, key_id))
            return {"msg": "API Key更新成功"}

@app.delete("/admin/api/api-keys/{key_id}")
async def delete_api_key(key_id: int, _=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await db_exec(cur, "DELETE FROM admin_api_keys WHERE id=%s", (key_id,))
            return {"msg": "API Key已删除"}

# ======================== 模型配置 ========================
@app.get("/admin/api/model-configs")
async def list_models(_=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            models = await db_query(cur, "SELECT * FROM admin_model_config ORDER BY provider, model_name")
            # 同时获取ai_model_configs以供对比
            ai_models = await db_query(cur, "SELECT * FROM ai_model_configs WHERE is_active=1 ORDER BY provider, name")
            return {"models": models, "ai_models": ai_models}

@app.post("/admin/api/model-configs")
async def create_model(req: ModelConfigReq, _=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            if req.is_default:
                await db_exec(cur, "UPDATE admin_model_config SET is_default=0 WHERE provider=%s", (req.provider,))
            await db_exec(cur, "INSERT INTO admin_model_config (provider,model_name,model_id,api_url,api_key,max_tokens,temperature,is_default) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                         (req.provider, req.model_name, req.model_id, req.api_url, req.api_key, req.max_tokens, req.temperature, 1 if req.is_default else 0))
            # 同步到主后端的ai_model_configs表（无论是否default，只要有url和key就同步）
            if req.api_url and req.api_key:
                # 先检查是否已存在同名配置
                existing = await db_one(cur, "SELECT id FROM ai_model_configs WHERE provider=%s AND model_name=%s", (req.provider, req.model_id))
                if existing:
                    await db_exec(cur, "UPDATE ai_model_configs SET api_url=%s,api_key=%s,name=%s,max_tokens=%s,temperature=%s,is_default=%s,is_active=1 WHERE id=%s",
                        (req.api_url, req.api_key, req.model_name, req.max_tokens, req.temperature, 1 if req.is_default else 0, existing["id"]))
                else:
                    await db_exec(cur, """INSERT INTO ai_model_configs (provider,name,api_url,api_key,model_name,max_tokens,temperature,is_default,is_active)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,1)""",
                        (req.provider, req.model_name, req.api_url, req.api_key, req.model_id, req.max_tokens, req.temperature, 1 if req.is_default else 0))
                # 如果是默认模型，取消其他默认
                if req.is_default:
                    await db_exec(cur, "UPDATE ai_model_configs SET is_default=0 WHERE id!=%s AND provider=%s", (existing["id"] if existing else cur.lastrowid, req.provider))
            return {"msg": "模型配置添加成功", "id": cur.lastrowid}

@app.put("/admin/api/model-configs/{model_id}")
async def update_model(model_id: int, req: ModelConfigReq, _=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            if req.is_default:
                await db_exec(cur, "UPDATE admin_model_config SET is_default=0 WHERE provider=%s AND id!=%s", (req.provider, model_id))
            await db_exec(cur, "UPDATE admin_model_config SET provider=%s,model_name=%s,model_id=%s,api_url=%s,api_key=%s,max_tokens=%s,temperature=%s,is_default=%s WHERE id=%s",
                         (req.provider, req.model_name, req.model_id, req.api_url, req.api_key, req.max_tokens, req.temperature, 1 if req.is_default else 0, model_id))
            # 同步更新ai_model_configs
            if req.api_url and req.api_key:
                existing = await db_one(cur, "SELECT id FROM ai_model_configs WHERE provider=%s AND model_name=%s", (req.provider, req.model_id))
                if existing:
                    await db_exec(cur, "UPDATE ai_model_configs SET api_url=%s,api_key=%s,name=%s,max_tokens=%s,temperature=%s,is_default=%s,is_active=1 WHERE id=%s",
                        (req.api_url, req.api_key, req.model_name, req.max_tokens, req.temperature, 1 if req.is_default else 0, existing["id"]))
                else:
                    await db_exec(cur, """INSERT INTO ai_model_configs (provider,name,api_url,api_key,model_name,max_tokens,temperature,is_default,is_active)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,1)""",
                        (req.provider, req.model_name, req.api_url, req.api_key, req.model_id, req.max_tokens, req.temperature, 1 if req.is_default else 0))
            return {"msg": "模型配置更新成功"}

@app.delete("/admin/api/model-configs/{model_id}")
async def delete_model(model_id: int, _=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await db_exec(cur, "DELETE FROM admin_model_config WHERE id=%s", (model_id,))
            return {"msg": "模型配置已删除"}

# 测试AI模型连通性
@app.post("/admin/api/model-configs/test")
async def test_model(req: ModelConfigReq, _=Depends(verify_admin)):
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(req.api_url,
                headers={"Authorization": f"Bearer {req.api_key}", "Content-Type": "application/json"},
                json={"model": req.model_id, "messages": [{"role":"user","content":"你好，请回复OK"}], "max_tokens": 32, "temperature": 0.5})
            if r.status_code == 200:
                resp = r.json()
                content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
                return {"success": True, "msg": f"连接成功，模型回复: {content[:50]}"}
            else:
                return {"success": False, "msg": f"HTTP {r.status_code}: {r.text[:200]}"}
    except Exception as e:
        return {"success": False, "msg": f"连接失败: {str(e)}"}

# ======================== 用户管理 ========================
@app.get("/admin/api/users")
async def list_users(page: int = 1, search: str = "", _=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            offset = (page - 1) * 20
            where = ""
            args = []
            if search:
                where = "WHERE u.username LIKE %s OR u.email LIKE %s"
                args = [f"%{search}%", f"%{search}%"]
            users = await db_query(cur, f"""
                SELECT u.id, u.username, u.email, u.is_npc, u.is_admin, u.is_banned, u.created_at,
                       c.id as colony_id, c.name as colony_name, c.level, c.score, c.gold,
                       c.minerals, c.energy, c.food, c.attack_power, c.defense_power, c.culture, c.happiness
                FROM users u LEFT JOIN colonies c ON u.id=c.user_id
                {where} ORDER BY u.id LIMIT 20 OFFSET %s
            """, args + [offset])
            total = await db_one(cur, f"SELECT COUNT(*) as cnt FROM users u {where}", args if args else None)
            return {"users": users, "total": total["cnt"] if total else 0, "page": page}

@app.post("/admin/api/users/manage")
async def manage_user(req: UserManageReq, _=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            user = await db_one(cur, "SELECT * FROM users WHERE id=%s", (req.user_id,))
            if not user:
                raise HTTPException(404, "用户不存在")
            if user.get("is_admin"):
                raise HTTPException(400, "不能操作管理员账号")

            if req.action == "ban":
                await db_exec(cur, "UPDATE users SET is_banned=1 WHERE id=%s", (req.user_id,))
                return {"msg": f"用户 {user['username']} 已封禁"}
            elif req.action == "unban":
                await db_exec(cur, "UPDATE users SET is_banned=0 WHERE id=%s", (req.user_id,))
                return {"msg": f"用户 {user['username']} 已解封"}
            elif req.action == "modify_gold":
                colony = await db_one(cur, "SELECT id FROM colonies WHERE user_id=%s", (req.user_id,))
                if colony:
                    await db_exec(cur, "UPDATE colonies SET gold=%s WHERE id=%s", (int(req.value), colony["id"]))
                    return {"msg": f"金币已修改为 {req.value}"}
                raise HTTPException(404, "殖民地不存在")
            elif req.action == "modify_resources":
                colony = await db_one(cur, "SELECT id FROM colonies WHERE user_id=%s", (req.user_id,))
                if colony:
                    parts = req.value.split(",")
                    # 格式: minerals,energy,food,gold
                    if len(parts) == 4:
                        await db_exec(cur, "UPDATE colonies SET minerals=%s,energy=%s,food=%s,gold=%s WHERE id=%s",
                            (int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]), colony["id"]))
                        return {"msg": "资源已修改"}
                    raise HTTPException(400, "格式：矿,能,食,金（逗号分隔）")
                raise HTTPException(404, "殖民地不存在")
            elif req.action == "reset_password":
                import bcrypt as bc
                new_hash = bc.hashpw(req.value.encode(), bc.gensalt(4)).decode()
                await db_exec(cur, "UPDATE users SET password_hash=%s WHERE id=%s", (new_hash, req.user_id))
                return {"msg": f"密码已重置为: {req.value}"}
            elif req.action == "delete":
                if user["is_npc"]:
                    await db_exec(cur, "DELETE FROM npc_bots WHERE user_id=%s", (req.user_id,))
                await db_exec(cur, "DELETE FROM colonies WHERE user_id=%s", (req.user_id,))
                await db_exec(cur, "DELETE FROM users WHERE id=%s", (req.user_id,))
                return {"msg": f"用户 {user['username']} 已删除"}
            else:
                raise HTTPException(400, "未知操作")

# ======================== NPC管理 ========================
@app.get("/admin/api/npcs")
async def list_npcs(_=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            npcs = await db_query(cur, """
                SELECT u.id as user_id, u.username, u.is_npc,
                       c.id as colony_id, c.name as colony_name, c.score, c.gold, c.attack_power, c.defense_power,
                       nb.personality, nb.difficulty, nb.trade_freq, nb.is_active, nb.model_name, nb.last_trade, nb.last_build, nb.last_post
                FROM npc_bots nb
                JOIN users u ON nb.user_id = u.id
                JOIN colonies c ON u.id = c.user_id
                ORDER BY c.score DESC
            """)
            return {"npcs": npcs}

@app.post("/admin/api/npcs")
async def create_npc(req: NPCReq, _=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            existing = await db_one(cur, "SELECT id FROM users WHERE username=%s", (req.username,))
            if existing:
                raise HTTPException(400, "用户名已存在")
            h = bcrypt.hashpw(f"npc_{req.username}".encode(), bcrypt.gensalt(4)).decode()
            await db_exec(cur, "INSERT INTO users (username,email,password_hash,is_npc) VALUES (%s,%s,%s,1)",
                         (req.username, f"npc_{req.username}@bot.com", h))
            uid = cur.lastrowid
            await db_exec(cur, "INSERT INTO colonies (user_id,name,planet_type,gold,minerals,energy,food) VALUES (%s,%s,'terran',5000,2000,2000,2000)",
                         (uid, req.colony_name))
            cid = cur.lastrowid
            await db_exec(cur, "INSERT INTO npc_bots (user_id,personality,difficulty,trade_freq,is_active,model_name) VALUES (%s,%s,%s,%s,%s,%s)",
                         (uid, req.personality, req.difficulty, req.trade_freq, 1 if req.is_active else 0, req.model_name))
            for t in ["mining","energy","farming","military","shield","trade"]:
                await db_exec(cur, "INSERT IGNORE INTO techs (colony_id,tech_type,level) VALUES (%s,%s,1)", (cid, t))
            return {"msg": f"NPC {req.colony_name} 创建成功", "user_id": uid, "colony_id": cid}

@app.put("/admin/api/npcs/{user_id}")
async def update_npc(user_id: int, req: NPCReq, _=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            npc = await db_one(cur, "SELECT * FROM npc_bots WHERE user_id=%s", (user_id,))
            if not npc:
                raise HTTPException(404, "NPC不存在")
            await db_exec(cur, "UPDATE npc_bots SET personality=%s,difficulty=%s,trade_freq=%s,is_active=%s,model_name=%s WHERE user_id=%s",
                         (req.personality, req.difficulty, req.trade_freq, 1 if req.is_active else 0, req.model_name, user_id))
            await db_exec(cur, "UPDATE users SET username=%s WHERE id=%s", (req.username, user_id))
            await db_exec(cur, "UPDATE colonies SET name=%s WHERE user_id=%s", (req.colony_name, user_id))
            return {"msg": f"NPC {req.colony_name} 更新成功"}

@app.delete("/admin/api/npcs/{user_id}")
async def delete_npc(user_id: int, _=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await db_exec(cur, "DELETE FROM npc_bots WHERE user_id=%s", (user_id,))
            await db_exec(cur, "DELETE FROM colonies WHERE user_id=%s", (user_id,))
            await db_exec(cur, "DELETE FROM users WHERE id=%s AND is_npc=1", (user_id,))
            return {"msg": "NPC已删除"}

@app.put("/admin/api/npcs/{user_id}/toggle")
async def toggle_npc(user_id: int, _=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            npc = await db_one(cur, "SELECT is_active FROM npc_bots WHERE user_id=%s", (user_id,))
            if not npc:
                raise HTTPException(404, "NPC不存在")
            new_status = 0 if npc["is_active"] else 1
            await db_exec(cur, "UPDATE npc_bots SET is_active=%s WHERE user_id=%s", (new_status, user_id))
            return {"msg": f"NPC已{'启用' if new_status else '停用'}", "is_active": bool(new_status)}

# ======================== 股票管理 ========================
@app.get("/admin/api/stocks")
async def list_stocks(_=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            stocks = await db_query(cur, "SELECT * FROM stocks ORDER BY code")
            for s in stocks:
                s["current_price"] = float(s["current_price"])
                s["change_pct"] = float(s["change_pct"])
            return {"stocks": stocks}

@app.post("/admin/api/stocks")
async def create_stock(req: StockReq, _=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            existing = await db_one(cur, "SELECT code FROM stocks WHERE code=%s", (req.code,))
            if existing:
                raise HTTPException(400, "股票代码已存在")
            await db_exec(cur, """INSERT INTO stocks (code,name,sector,current_price,open_price,high_price,low_price,prev_close,market_cap,pe_ratio)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (req.code, req.name, req.sector, req.initial_price, req.initial_price, req.initial_price, req.initial_price, req.initial_price,
                 int(req.initial_price * 10000000), round(req.initial_price * random.uniform(8, 50), 2)))
            today = datetime.now().date()
            for i in range(60):
                d = today - timedelta(days=60-i)
                p = float(req.initial_price) * (0.8 + random.random() * 0.4)
                await db_exec(cur, """INSERT IGNORE INTO stock_klines (stock_code,k_date,open_price,high_price,low_price,close_price,volume,change_pct)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (req.code, d, round(p,2), round(p*1.03,2), round(p*0.97,2), round(p*random.uniform(0.98,1.02),2), random.randint(10000,100000), round(random.uniform(-3,3),2)))
            return {"msg": f"股票 {req.name}({req.code}) 创建成功"}

@app.put("/admin/api/stocks/{code}")
async def update_stock(code: str, req: StockReq, _=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await db_exec(cur, "UPDATE stocks SET name=%s,sector=%s WHERE code=%s",
                         (req.name, req.sector, code))
            return {"msg": "股票信息更新成功"}

@app.delete("/admin/api/stocks/{code}")
async def delete_stock(code: str, _=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await db_exec(cur, "DELETE FROM stock_klines WHERE stock_code=%s", (code,))
            await db_exec(cur, "DELETE FROM stock_orderbook WHERE stock_code=%s", (code,))
            await db_exec(cur, "DELETE FROM stock_trades WHERE stock_code=%s", (code,))
            await db_exec(cur, "DELETE FROM stock_portfolios WHERE stock_code=%s", (code,))
            await db_exec(cur, "DELETE FROM stock_watchlist WHERE stock_code=%s", (code,))
            await db_exec(cur, "DELETE FROM stocks WHERE code=%s", (code,))
            return {"msg": "股票及关联数据已删除"}

# ======================== 市场干预 ========================
@app.post("/admin/api/market/intervene")
async def market_intervene(req: MarketInterventionReq, _=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            stock = await db_one(cur, "SELECT * FROM stocks WHERE code=%s", (req.stock_code,))
            if not stock:
                raise HTTPException(404, "股票不存在")
            old_price = float(stock["current_price"])
            if req.action == "push_up":
                new_price = old_price * (1 + random.uniform(0.03, 0.08))
            elif req.action == "push_down":
                new_price = old_price * (1 - random.uniform(0.03, 0.08))
            elif req.action == "stabilize":
                new_price = old_price * (1 + random.uniform(-0.01, 0.01))
            elif req.action == "halt":
                await db_exec(cur, "UPDATE stocks SET is_active=0 WHERE code=%s", (req.stock_code,))
                return {"msg": f"股票 {stock['name']} 已停牌"}
            else:
                raise HTTPException(400, "未知干预操作")
            change_pct = round((new_price - old_price) / old_price * 100, 2)
            await db_exec(cur, "UPDATE stocks SET current_price=%s,change_pct=%s WHERE code=%s", (round(new_price,2), change_pct, req.stock_code))
            return {"msg": f"干预成功，{stock['name']} {'上涨' if new_price>old_price else '下跌'}至 {round(new_price,2)} ({change_pct:+.2f}%)"}

@app.post("/admin/api/market/halt/{code}")
async def toggle_halt(code: str, _=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            stock = await db_one(cur, "SELECT * FROM stocks WHERE code=%s", (code,))
            if not stock:
                raise HTTPException(404, "股票不存在")
            new_status = 0 if stock["is_active"] else 1
            await db_exec(cur, "UPDATE stocks SET is_active=%s WHERE code=%s", (new_status, code))
            return {"msg": f"股票已{'停牌' if not new_status else '复牌'}"}

# ======================== 论坛管理 ========================
@app.get("/admin/api/forum/posts")
async def list_forum_posts(category: str = "", page: int = 1, _=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            offset = (page - 1) * 20
            if category:
                posts = await db_query(cur, "SELECT * FROM forum_posts WHERE category=%s ORDER BY is_pinned DESC, created_at DESC LIMIT 20 OFFSET %s", (category, offset))
            else:
                posts = await db_query(cur, "SELECT * FROM forum_posts ORDER BY is_pinned DESC, created_at DESC LIMIT 20 OFFSET %s", (offset,))
            return {"posts": posts, "page": page}

@app.post("/admin/api/forum/manage")
async def manage_forum(req: ForumManageReq, _=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            if req.action == "pin":
                await db_exec(cur, "UPDATE forum_posts SET is_pinned=1 WHERE id=%s", (req.post_id,))
                return {"msg": "帖子已置顶"}
            elif req.action == "unpin":
                await db_exec(cur, "UPDATE forum_posts SET is_pinned=0 WHERE id=%s", (req.post_id,))
                return {"msg": "帖子已取消置顶"}
            elif req.action == "delete":
                await db_exec(cur, "DELETE FROM forum_replies WHERE post_id=%s", (req.post_id,))
                await db_exec(cur, "DELETE FROM forum_posts WHERE id=%s", (req.post_id,))
                return {"msg": "帖子已删除"}
            else:
                raise HTTPException(400, "未知操作")

# ======================== 派系管理 ========================
@app.get("/admin/api/factions")
async def list_factions(_=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            factions = await db_query(cur, "SELECT f.*,c.name as leader_name FROM factions f LEFT JOIN colonies c ON f.leader_id=c.id ORDER BY total_score DESC")
            return {"factions": factions}

@app.post("/admin/api/factions/manage")
async def manage_faction(req: FactionManageReq, _=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            if req.action == "disband":
                await db_exec(cur, "DELETE FROM colony_factions WHERE faction_id=%s", (req.faction_id,))
                await db_exec(cur, "DELETE FROM diplomacy WHERE faction_a=%s OR faction_b=%s", (req.faction_id, req.faction_id))
                await db_exec(cur, "DELETE FROM factions WHERE id=%s", (req.faction_id,))
                return {"msg": "派系已解散"}
            elif req.action == "rename" and req.new_name:
                await db_exec(cur, "UPDATE factions SET name=%s WHERE id=%s", (req.new_name, req.faction_id))
                return {"msg": f"派系已更名为 {req.new_name}"}
            else:
                raise HTTPException(400, "未知操作")

# ======================== 上帝AI管理 ========================
class GodAIActionReq(BaseModel):
    action: str

class ModifyDataReq(BaseModel):
    table_name: str
    row_id: int
    field: str
    value: str

@app.get("/admin/api/god-ai/logs")
async def god_ai_logs(page: int = 1, _=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            offset = (page - 1) * 20
            logs = await db_query(cur, "SELECT * FROM god_ai_log ORDER BY created_at DESC LIMIT 20 OFFSET %s", (offset,))
            total = await db_one(cur, "SELECT COUNT(*) as cnt FROM god_ai_log")
            return {"logs": logs, "total": total["cnt"] if total else 0, "page": page}

@app.post("/admin/api/god-ai/execute")
async def god_ai_execute(req: GodAIActionReq, _=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            desc = ""
            if req.action == "balance_economy":
                prices = await db_query(cur, "SELECT * FROM resource_prices")
                for p in prices:
                    if p["current_price"] > p["base_price"] * 3:
                        new_p = int(p["current_price"] * 0.85)
                        await db_exec(cur, "UPDATE resource_prices SET current_price=%s WHERE resource_type=%s", (new_p, p["resource_type"]))
                        desc += f"{p['resource_type']}过高→{new_p}; "
                    elif p["current_price"] < p["base_price"] * 0.3:
                        new_p = int(p["current_price"] * 1.2)
                        await db_exec(cur, "UPDATE resource_prices SET current_price=%s WHERE resource_type=%s", (new_p, p["resource_type"]))
                        desc += f"{p['resource_type']}过低→{new_p}; "
                if not desc: desc = "经济系统正常，无需干预"
            elif req.action == "weather_event":
                events = [("暗物质风暴","暗物质风暴席卷银河系边缘","minerals",-0.05),("量子潮汐","量子潮汐带来能量波动","energy",0.1),
                    ("星际寒流","星际寒流来袭","food",-0.08),("等离子雨","等离子雨降临","energy",0.15),("陨石群","陨石群经过","minerals",0.12)]
                evt = random.choice(events)
                colonies = await db_query(cur, "SELECT id FROM colonies")
                for c in colonies:
                    await db_exec(cur, f"UPDATE colonies SET {evt[2]}={evt[2]}*(1+%s) WHERE id=%s", (evt[3], c["id"]))
                desc = f"{evt[0]}: {evt[1]}"
            elif req.action == "fix_data":
                await db_exec(cur, "UPDATE colonies SET minerals=GREATEST(minerals,0), energy=GREATEST(energy,0), food=GREATEST(food,0), gold=GREATEST(gold,0)")
                await db_exec(cur, "UPDATE colonies SET attack_power=GREATEST(attack_power,10), defense_power=GREATEST(defense_power,10)")
                desc = "数据修复完成：负值归零、异常值修正"
            elif req.action == "market_intervention":
                stocks = await db_query(cur, "SELECT * FROM stocks WHERE is_active=1 ORDER BY RAND() LIMIT 3")
                for s in stocks:
                    direction = random.choice(["up","down"])
                    pct = random.uniform(1.0, 3.0)
                    old_p = float(s["current_price"])
                    new_p = old_p * (1 + pct/100) if direction=="up" else old_p * (1 - pct/100)
                    prev = float(s["prev_close"])
                    new_p = max(round(prev*0.9,2), min(round(prev*1.1,2), round(new_p,2)))
                    await db_exec(cur, "UPDATE stocks SET current_price=%s WHERE code=%s", (new_p, s["code"]))
                    desc += f"{s['name']}{'↑' if direction=='up' else '↓'}{pct:.1f}%; "
            elif req.action == "stock_event":
                events = [("利好政策","星际联邦发布新政策",1),("行业丑闻","某企业爆出丑闻",-1),("技术突破","重大技术突破",1)]
                evt = random.choice(events)
                stocks = await db_query(cur, "SELECT code FROM stocks WHERE is_active=1 ORDER BY RAND() LIMIT 5")
                for s in stocks:
                    chg = round(random.uniform(0.3,1.5)*evt[2], 2)
                    await db_exec(cur, "UPDATE stocks SET change_pct=change_pct+%s WHERE code=%s", (chg, s["code"]))
                desc = f"{evt[0]}: {evt[1]}"
            elif req.action == "reward_active":
                active = await db_query(cur, "SELECT id FROM colonies WHERE last_online > DATE_SUB(NOW(), INTERVAL 1 HOUR) LIMIT 10")
                for c in active:
                    reward = random.randint(50, 200)
                    await db_exec(cur, "UPDATE colonies SET gold=gold+%s WHERE id=%s", (reward, c["id"]))
                desc = f"发放活跃奖励给{len(active)}个殖民地"
            else:
                raise HTTPException(400, f"未知操作: {req.action}")
            await db_exec(cur, "INSERT INTO god_ai_log (action_type,description) VALUES ('admin_%s',%s)", (req.action, desc))
            return {"msg": f"上帝AI执行 [{req.action}]: {desc}"}

@app.post("/admin/api/god-ai/modify")
async def god_ai_modify(req: ModifyDataReq, _=Depends(verify_admin)):
    ALLOWED_TABLES = {"colonies", "stocks", "resource_prices", "factions", "territories", "npc_bots", "users"}
    if req.table_name not in ALLOWED_TABLES:
        raise HTTPException(400, f"不允许修改表 {req.table_name}，允许: {list(ALLOWED_TABLES)}")
    if not req.field.replace("_","").isalnum():
        raise HTTPException(400, "字段名不合法")
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            row = await db_one(cur, f"SELECT id FROM {req.table_name} WHERE id=%s", (req.row_id,))
            if not row:
                raise HTTPException(404, f"{req.table_name} id={req.row_id} 不存在")
            try:
                val = float(req.value) if "." in req.value else int(req.value)
            except:
                val = req.value
            await db_exec(cur, f"UPDATE {req.table_name} SET {req.field}=%s WHERE id=%s", (val, req.row_id))
            await db_exec(cur, "INSERT INTO god_ai_log (action_type,description) VALUES ('admin_modify',%s)",
                (f"管理员修改 {req.table_name} id={req.row_id} {req.field}={req.value}",))
            return {"msg": f"已修改 {req.table_name}.{req.field} = {req.value}"}

@app.get("/admin/api/stocks/ipo-calendar")
async def ipo_calendar(_=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            ipos = await db_query(cur, "SELECT * FROM stock_ipo_log ORDER BY created_at DESC LIMIT 30")
            return {"ipos": ipos}

# ======================== 全局配置 ========================
@app.get("/admin/api/config")
async def get_configs(_=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            configs = await db_query(cur, "SELECT * FROM admin_global_config ORDER BY config_key")
            return {"configs": configs}

@app.post("/admin/api/config")
async def set_config(req: GlobalConfigReq, _=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await db_exec(cur, "INSERT INTO admin_global_config (config_key,config_value) VALUES (%s,%s) ON DUPLICATE KEY UPDATE config_value=%s",
                         (req.config_key, req.config_value, req.config_value))
            return {"msg": f"配置 {req.config_key} 已更新"}

# ======================== 数据看板 ========================
@app.get("/admin/api/dashboard")
async def dashboard(_=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            total_users = await db_one(cur, "SELECT COUNT(*) as cnt FROM users WHERE is_npc=0")
            banned_users = await db_one(cur, "SELECT COUNT(*) as cnt FROM users WHERE is_banned=1")
            total_npcs = await db_one(cur, "SELECT COUNT(*) as cnt FROM npc_bots")
            total_colonies = await db_one(cur, "SELECT COUNT(*) as cnt FROM colonies")
            total_posts = await db_one(cur, "SELECT COUNT(*) as cnt FROM forum_posts")
            total_replies = await db_one(cur, "SELECT COUNT(*) as cnt FROM forum_replies")
            total_trades = await db_one(cur, "SELECT COUNT(*) as cnt FROM trade_history")
            total_stock_trades = await db_one(cur, "SELECT COUNT(*) as cnt FROM stock_trades")
            total_stocks = await db_one(cur, "SELECT COUNT(*) as cnt FROM stocks WHERE is_active=1")
            open_futures = await db_one(cur, "SELECT COUNT(*) as cnt FROM futures_contracts WHERE status='open'")
            total_battles = await db_one(cur, "SELECT COUNT(*) as cnt FROM battle_logs")
            total_factions = await db_one(cur, "SELECT COUNT(*) as cnt FROM factions")
            total_gold = await db_one(cur, "SELECT SUM(gold) as total FROM colonies")
            recent_trades = await db_query(cur, "SELECT * FROM trade_history ORDER BY created_at DESC LIMIT 10")
            top_stocks = await db_query(cur, "SELECT code,name,current_price,change_pct,volume FROM stocks WHERE is_active=1 ORDER BY ABS(change_pct) DESC LIMIT 10")
            top_colonies = await db_query(cur, "SELECT c.name,u.username,c.score,c.gold,c.attack_power FROM colonies c JOIN users u ON c.user_id=u.id WHERE u.is_npc=0 ORDER BY c.score DESC LIMIT 10")
            ai_models = await db_query(cur, "SELECT provider,name,model_name,is_default,is_active FROM ai_model_configs")

            for s in top_stocks:
                s["current_price"] = float(s["current_price"])
                s["change_pct"] = float(s["change_pct"])

            return {
                "stats": {
                    "total_users": total_users["cnt"],
                    "banned_users": banned_users["cnt"],
                    "total_npcs": total_npcs["cnt"],
                    "total_colonies": total_colonies["cnt"],
                    "total_posts": total_posts["cnt"],
                    "total_replies": total_replies["cnt"],
                    "total_trades": total_trades["cnt"],
                    "total_stock_trades": total_stock_trades["cnt"],
                    "total_stocks": total_stocks["cnt"],
                    "open_futures": open_futures["cnt"],
                    "total_battles": total_battles["cnt"],
                    "total_factions": total_factions["cnt"],
                    "total_gold": total_gold["total"] or 0
                },
                "recent_trades": recent_trades,
                "top_stocks": top_stocks,
                "top_colonies": top_colonies,
                "ai_models": ai_models
            }

# ======================== V7: 上帝AI管理 ========================
@app.get("/admin/api/god-ai/logs")
async def god_ai_logs(page: int = 1, _=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            offset = (page - 1) * 20
            logs = await db_query(cur, "SELECT * FROM god_ai_log ORDER BY created_at DESC LIMIT 20 OFFSET %s", (offset,))
            total = await db_one(cur, "SELECT COUNT(*) as cnt FROM god_ai_log")
            return {"logs": logs, "total": total["cnt"], "page": page}

@app.post("/admin/api/god-ai/execute")
async def god_ai_execute(req: GodAIActionReq, _=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            desc = ""
            if req.action == "balance_economy":
                prices = await db_query(cur, "SELECT * FROM resource_prices")
                for p in prices:
                    if p["current_price"] > p["base_price"] * 3:
                        new_p = int(p["current_price"] * 0.85)
                        await db_exec(cur, "UPDATE resource_prices SET current_price=%s WHERE resource_type=%s", (new_p, p["resource_type"]))
                        desc += f"{p['resource_type']}过高→{new_p}; "
                    elif p["current_price"] < p["base_price"] * 0.3:
                        new_p = int(p["current_price"] * 1.2)
                        await db_exec(cur, "UPDATE resource_prices SET current_price=%s WHERE resource_type=%s", (new_p, p["resource_type"]))
                        desc += f"{p['resource_type']}过低→{new_p}; "
                if not desc: desc = "经济系统正常，无需干预"
            elif req.action == "weather_event":
                events = [
                    ("暗物质风暴", "暗物质风暴席卷银河系边缘", "minerals", -0.05),
                    ("量子潮汐", "量子潮汐带来能量波动", "energy", 0.1),
                    ("星际寒流", "星际寒流来袭", "food", -0.08),
                    ("等离子雨", "等离子雨降临", "energy", 0.15),
                    ("陨石群", "陨石群经过", "minerals", 0.12),
                ]
                evt = random.choice(events)
                colonies = await db_query(cur, "SELECT id FROM colonies")
                for c in colonies:
                    await db_exec(cur, f"UPDATE colonies SET {evt[2]}={evt[2]}*(1+%s) WHERE id=%s", (evt[3], c["id"]))
                desc = f"{evt[0]}: {evt[1]}"
            elif req.action == "fix_data":
                await db_exec(cur, "UPDATE colonies SET minerals=GREATEST(minerals,0), energy=GREATEST(energy,0), food=GREATEST(food,0), gold=GREATEST(gold,0)")
                await db_exec(cur, "UPDATE colonies SET attack_power=GREATEST(attack_power,10), defense_power=GREATEST(defense_power,10)")
                desc = "数据修复完成：负值归零、异常值修正"
            elif req.action == "market_intervention":
                stocks = await db_query(cur, "SELECT * FROM stocks WHERE is_active=1 ORDER BY RAND() LIMIT 3")
                for s in stocks:
                    direction = random.choice(["up","down"])
                    pct = random.uniform(1.0, 3.0)
                    if direction == "up":
                        new_price = round(float(s["current_price"]) * (1 + pct/100), 2)
                    else:
                        new_price = round(float(s["current_price"]) * (1 - pct/100), 2)
                    prev = float(s["prev_close"])
                    new_price = max(round(prev*0.9,2), min(round(prev*1.1,2), new_price))
                    await db_exec(cur, "UPDATE stocks SET current_price=%s WHERE code=%s", (new_price, s["code"]))
                    desc += f"{s['name']}{'↑' if direction=='up' else '↓'}{pct:.1f}%; "
            elif req.action == "stock_event":
                events = [
                    ("利好政策", "星际联邦发布新政策", 1),
                    ("行业丑闻", "某企业爆出丑闻", -1),
                    ("技术突破", "重大技术突破", 1),
                ]
                evt = random.choice(events)
                stocks = await db_query(cur, "SELECT code FROM stocks WHERE is_active=1 ORDER BY RAND() LIMIT 5")
                for s in stocks:
                    chg = round(random.uniform(0.3, 1.5) * evt[2], 2)
                    await db_exec(cur, "UPDATE stocks SET change_pct=change_pct+%s WHERE code=%s", (chg, s["code"]))
                desc = f"{evt[0]}: {evt[1]}"
            elif req.action == "reward_active":
                active = await db_query(cur, "SELECT id FROM colonies WHERE last_online > DATE_SUB(NOW(), INTERVAL 1 HOUR) LIMIT 10")
                for c in active:
                    reward = random.randint(50, 200)
                    await db_exec(cur, "UPDATE colonies SET gold=gold+%s WHERE id=%s", (reward, c["id"]))
                desc = f"发放活跃奖励给{len(active)}个殖民地"
            else:
                raise HTTPException(400, f"未知操作: {req.action}")
            await db_exec(cur, "INSERT INTO god_ai_log (action_type,description) VALUES (%s,%s)", (req.action, desc))
            return {"msg": f"上帝AI执行 [{req.action}]: {desc}"}

@app.post("/admin/api/god-ai/modify")
async def god_ai_modify(req: ModifyDataReq, _=Depends(verify_admin)):
    ALLOWED_TABLES = {"colonies", "stocks", "resource_prices", "factions", "territories", "npc_bots", "users"}
    if req.table_name not in ALLOWED_TABLES:
        raise HTTPException(400, f"不允许修改表 {req.table_name}，允许的表: {list(ALLOWED_TABLES)}")
    if not req.field.replace("_","").isalnum():
        raise HTTPException(400, "字段名不合法")
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            row = await db_one(cur, f"SELECT id FROM {req.table_name} WHERE id=%s", (req.row_id,))
            if not row:
                raise HTTPException(404, f"{req.table_name} id={req.row_id} 不存在")
            try:
                val = float(req.value) if "." in req.value else int(req.value)
            except:
                val = req.value
            await db_exec(cur, f"UPDATE {req.table_name} SET {req.field}=%s WHERE id=%s", (val, req.row_id))
            await db_exec(cur, "INSERT INTO god_ai_log (action_type,description) VALUES ('admin_modify',%s)",
                (f"管理员修改 {req.table_name} id={req.row_id} {req.field}={req.value}",))
            return {"msg": f"已修改 {req.table_name}.{req.field} = {req.value}"}

# ======================== V7: IPO日历 ========================
@app.get("/admin/api/stocks/ipo-calendar")
async def ipo_calendar(_=Depends(verify_admin)):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            ipos = await db_query(cur, "SELECT * FROM stock_ipo_log ORDER BY created_at DESC LIMIT 30")
            return {"ipos": ipos}

# ======================== 管理后台HTML ========================
@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    return HTMLResponse(ADMIN_HTML)

ADMIN_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>星际殖民地 - 管理后台</title>
<style>
:root {
  --bg: #0a0a1a;
  --bg2: #111133;
  --bg3: #1a1a44;
  --accent: #00e5ff;
  --accent2: #7c4dff;
  --gold: #ffd740;
  --red: #ff5252;
  --green: #69f0ae;
  --text: #e0e0ff;
  --text2: #8888cc;
  --border: #222255;
  --radius: 8px;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', sans-serif; background: var(--bg); color: var(--text); font-size: 15px; line-height: 1.6; min-height: 100vh; }
#login-screen { display: flex; align-items: center; justify-content: center; min-height: 100vh; background: linear-gradient(135deg, #0a0a2e 0%, #1a0a3e 50%, #0a0a2e 100%); }
.login-box { background: var(--bg2); border: 1px solid var(--border); border-radius: 16px; padding: 48px 40px; width: 400px; max-width: 90vw; box-shadow: 0 0 60px rgba(0,229,255,0.1); }
.login-box h1 { text-align: center; font-size: 28px; color: var(--accent); margin-bottom: 8px; }
.login-box .subtitle { text-align: center; color: var(--text2); font-size: 13px; margin-bottom: 32px; }
.login-box input { width: 100%; padding: 12px 16px; margin-bottom: 16px; background: var(--bg3); border: 1px solid var(--border); border-radius: var(--radius); color: var(--text); font-size: 15px; outline: none; transition: border-color .3s; }
.login-box input:focus { border-color: var(--accent); }
.login-box button { width: 100%; padding: 12px; background: linear-gradient(135deg, var(--accent), var(--accent2)); border: none; border-radius: var(--radius); color: #000; font-size: 16px; font-weight: 600; cursor: pointer; transition: opacity .3s; }
.login-box button:hover { opacity: 0.9; }
.login-box .error { color: var(--red); font-size: 13px; text-align: center; margin-top: 8px; min-height: 20px; }
#app-screen { display: none; }
.sidebar { position: fixed; left: 0; top: 0; bottom: 0; width: 220px; background: var(--bg2); border-right: 1px solid var(--border); padding: 20px 0; overflow-y: auto; z-index: 10; }
.sidebar h2 { padding: 0 20px 20px; color: var(--accent); font-size: 18px; border-bottom: 1px solid var(--border); margin-bottom: 12px; }
.sidebar .nav-item { display: block; padding: 10px 20px; color: var(--text2); cursor: pointer; transition: all .2s; border-left: 3px solid transparent; font-size: 14px; text-decoration: none; }
.sidebar .nav-item:hover { color: var(--text); background: rgba(255,255,255,0.03); }
.sidebar .nav-item.active { color: var(--accent); background: rgba(0,229,255,0.08); border-left-color: var(--accent); }
.main { margin-left: 220px; padding: 24px 32px; min-height: 100vh; }
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--border); }
.header h1 { font-size: 24px; color: var(--accent); }
.header .logout-btn { padding: 6px 16px; background: transparent; border: 1px solid var(--red); color: var(--red); border-radius: var(--radius); cursor: pointer; font-size: 13px; }
.panel { display: none; }.panel.active { display: block; }
.card { background: var(--bg2); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; margin-bottom: 20px; }
.card h3 { color: var(--accent); font-size: 16px; margin-bottom: 16px; }
.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px; margin-bottom: 20px; }
.stat-card { background: var(--bg2); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; text-align: center; }
.stat-card .value { font-size: 28px; font-weight: 700; color: var(--accent); }
.stat-card .label { font-size: 12px; color: var(--text2); margin-top: 4px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--border); }
th { color: var(--accent); font-weight: 600; white-space: nowrap; }
tr:hover { background: rgba(255,255,255,0.02); }
.btn { padding: 6px 14px; border-radius: var(--radius); border: none; cursor: pointer; font-size: 13px; transition: opacity .2s; }
.btn:hover { opacity: 0.85; }
.btn-primary { background: var(--accent); color: #000; }
.btn-danger { background: var(--red); color: #fff; }
.btn-success { background: var(--green); color: #000; }
.btn-warning { background: var(--gold); color: #000; }
.btn-gold { background: var(--gold); color: #000; }
.btn-accent2 { background: var(--accent2); color: #fff; }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.form-group { margin-bottom: 12px; }
.form-group label { display: block; font-size: 13px; color: var(--text2); margin-bottom: 4px; }
.form-group input, .form-group select, .form-group textarea { width: 100%; padding: 8px 12px; background: var(--bg3); border: 1px solid var(--border); border-radius: var(--radius); color: var(--text); font-size: 14px; outline: none; }
.form-group input:focus, .form-group select:focus, .form-group textarea:focus { border-color: var(--accent); }
.form-group textarea { min-height: 80px; resize: vertical; }
.form-row { display: flex; gap: 12px; }
.form-row .form-group { flex: 1; }
.alert { padding: 10px 16px; border-radius: var(--radius); margin-bottom: 12px; font-size: 13px; }
.alert-success { background: rgba(105,240,174,0.1); border: 1px solid var(--green); color: var(--green); }
.alert-error { background: rgba(255,82,82,0.1); border: 1px solid var(--red); color: var(--red); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }
.badge-active { background: rgba(105,240,174,0.2); color: var(--green); }
.badge-inactive { background: rgba(255,82,82,0.2); color: var(--red); }
.badge-banned { background: rgba(255,82,82,0.3); color: #ff8a80; }
.badge-npc { background: rgba(124,77,255,0.2); color: var(--accent2); }
.price-up { color: var(--red); }
.price-down { color: var(--green); }
</style>
</head>
<body>

<div id="login-screen">
  <div class="login-box">
    <h1>🌌 管理后台</h1>
    <div class="subtitle">星际殖民地</div>
    <input type="text" id="login-user" placeholder="管理员用户名">
    <input type="password" id="login-pass" placeholder="管理员密码">
    <button onclick="doLogin()">登 录</button>
    <div class="error" id="login-error"></div>
  </div>
</div>

<div id="app-screen">
  <div class="sidebar">
    <h2>🌌 管理后台</h2>
    <div class="nav-item active" data-panel="dashboard">📊 数据看板</div>
    <div class="nav-item" data-panel="users">👥 用户管理</div>
    <div class="nav-item" data-panel="api-keys">🔑 API Key</div>
    <div class="nav-item" data-panel="models">🤖 模型配置</div>
    <div class="nav-item" data-panel="npcs">👤 NPC管理</div>
    <div class="nav-item" data-panel="stocks">📈 股票管理</div>
    <div class="nav-item" data-panel="market">💰 市场干预</div>
    <div class="nav-item" data-panel="forum">💬 论坛管理</div>
    <div class="nav-item" data-panel="factions">🏛️ 派系管理</div>
    <div class="nav-item" data-panel="god-ai">🧠 上帝AI</div>
    <div class="nav-item" data-panel="config">⚙️ 全局配置</div>
  </div>
  <div class="main">
    <div class="header">
      <h1 id="panel-title">数据看板</h1>
      <button class="logout-btn" onclick="doLogout()">退出登录</button>
    </div>
    <div id="alerts"></div>

    <div class="panel active" id="panel-dashboard">
      <div class="card-grid" id="stats-grid"></div>
      <div class="card"><h3>AI模型状态</h3><table id="ai-models-table"><thead><tr><th>提供商</th><th>名称</th><th>模型ID</th><th>默认</th><th>状态</th></tr></thead><tbody></tbody></table></div>
      <div class="card"><h3>股票涨幅排行</h3><table id="top-stocks"><thead><tr><th>代码</th><th>名称</th><th>现价</th><th>涨跌幅</th><th>成交量</th></tr></thead><tbody></tbody></table></div>
      <div class="card"><h3>玩家排行</h3><table id="top-players"><thead><tr><th>殖民地</th><th>玩家</th><th>积分</th><th>金币</th><th>战力</th></tr></thead><tbody></tbody></table></div>
    </div>

    <div class="panel" id="panel-users">
      <div class="card"><h3>搜索用户</h3>
        <div class="form-row">
          <div class="form-group"><input id="user-search" placeholder="用户名或邮箱"></div>
          <button class="btn btn-primary" onclick="loadUsers()" style="align-self:flex-end">搜索</button>
        </div>
      </div>
      <div class="card"><h3>用户列表</h3><table id="users-table"><thead><tr><th>ID</th><th>用户名</th><th>邮箱</th><th>殖民地</th><th>等级</th><th>金币</th><th>积分</th><th>NPC</th><th>状态</th><th>操作</th></tr></thead><tbody></tbody></table></div>
      <div id="user-manage-modal" style="display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.6);z-index:100;display:none;align-items:center;justify-content:center">
        <div style="background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:24px;width:400px;max-width:90vw">
          <h3 style="color:var(--accent);margin-bottom:12px">用户管理 - <span id="um-username"></span></h3>
          <div id="um-info" style="font-size:13px;margin-bottom:12px"></div>
          <div style="display:flex;flex-wrap:wrap;gap:8px">
            <button class="btn btn-danger" onclick="manageUser('ban')">🚫 封禁</button>
            <button class="btn btn-success" onclick="manageUser('unban')">✅ 解封</button>
            <button class="btn btn-warning" onclick="manageUser('modify_gold')">💰 修改金币</button>
            <button class="btn btn-warning" onclick="manageUser('modify_resources')">📦 修改资源</button>
            <button class="btn btn-primary" onclick="manageUser('reset_password')">🔑 重置密码</button>
            <button class="btn btn-danger" onclick="manageUser('delete')">🗑️ 删除</button>
          </div>
          <button class="btn" onclick="closeUserModal()" style="margin-top:12px;width:100%">关闭</button>
        </div>
      </div>
    </div>

    <div class="panel" id="panel-api-keys">
      <div class="card"><h3>添加API Key</h3>
        <div class="form-row">
          <div class="form-group"><label>提供商</label><select id="key-provider"><option value="openai">OpenAI</option><option value="qwen">通义千问</option><option value="deepseek">DeepSeek</option><option value="zhipu">智谱AI</option><option value="custom">自定义</option></select></div>
          <div class="form-group"><label>名称</label><input id="key-name" placeholder="例如：生产环境Key"></div>
        </div>
        <div class="form-row">
          <div class="form-group"><label>API Key</label><input id="key-value" placeholder="sk-..."></div>
          <div class="form-group"><label>API Base URL（可选）</label><input id="key-base" placeholder="https://api.openai.com/v1"></div>
        </div>
        <button class="btn btn-primary" onclick="addApiKey()">添加</button>
      </div>
      <div class="card"><h3>已配置的API Keys</h3><table id="keys-table"><thead><tr><th>ID</th><th>提供商</th><th>名称</th><th>Key预览</th><th>状态</th><th>操作</th></tr></thead><tbody></tbody></table></div>
    </div>

    <div class="panel" id="panel-models">
      <div class="card"><h3>添加模型配置</h3>
        <div class="form-row">
          <div class="form-group"><label>提供商</label><select id="model-provider"><option value="openai">OpenAI</option><option value="qwen">通义千问</option><option value="deepseek" selected>DeepSeek</option><option value="zhipu">智谱AI</option><option value="custom">自定义</option></select></div>
          <div class="form-group"><label>模型名称</label><input id="model-name" placeholder="GPT-4o"></div>
          <div class="form-group"><label>模型ID</label><input id="model-id" placeholder="gpt-4o"></div>
        </div>
        <div class="form-row">
          <div class="form-group"><label>API URL</label><input id="model-url" placeholder="https://api.deepseek.com/v1/chat/completions"></div>
          <div class="form-group"><label>API Key</label><input id="model-key" placeholder="sk-..."></div>
        </div>
        <div class="form-row">
          <div class="form-group"><label>Max Tokens</label><input id="model-tokens" type="number" value="2048"></div>
          <div class="form-group"><label>Temperature</label><input id="model-temp" type="number" step="0.1" value="0.8" min="0" max="2"></div>
          <div class="form-group"><label style="display:flex;align-items:center;gap:8px;padding-top:20px"><input type="checkbox" id="model-default"> 设为默认</label></div>
        </div>
        <button class="btn btn-primary" onclick="addModel()">添加</button>
        <button class="btn btn-success" onclick="testModel()" style="margin-left:8px">🧪 测试连通</button>
      </div>
      <div class="card"><h3>已配置的模型</h3><table id="models-table"><thead><tr><th>ID</th><th>提供商</th><th>名称</th><th>模型ID</th><th>URL</th><th>Tokens</th><th>默认</th><th>操作</th></tr></thead><tbody></tbody></table></div>
      <div class="card"><h3>主后端AI模型配置(ai_model_configs)</h3><table id="ai-models-admin-table"><thead><tr><th>ID</th><th>提供商</th><th>名称</th><th>模型ID</th><th>默认</th><th>活跃</th></tr></thead><tbody></tbody></table></div>
    </div>

    <div class="panel" id="panel-npcs">
      <div class="card"><h3>创建NPC</h3>
        <div class="form-row">
          <div class="form-group"><label>用户名</label><input id="npc-username" placeholder="bot_trader"></div>
          <div class="form-group"><label>殖民地名称</label><input id="npc-colony" placeholder="贸易帝国"></div>
        </div>
        <div class="form-row">
          <div class="form-group"><label>性格</label><select id="npc-personality"><option value="balanced">均衡</option><option value="aggressive">好战</option><option value="peaceful">和平</option><option value="trader">贸易</option><option value="scholar">学者</option></select></div>
          <div class="form-group"><label>难度(1-5)</label><input id="npc-difficulty" type="number" value="3" min="1" max="5"></div>
          <div class="form-group"><label>交易频率(秒)</label><input id="npc-freq" type="number" value="300" min="60"></div>
        </div>
        <div class="form-group"><label>使用的AI模型</label><input id="npc-model" placeholder="留空则使用简单AI逻辑"></div>
        <button class="btn btn-primary" onclick="addNpc()">创建NPC</button>
      </div>
      <div class="card"><h3>NPC列表</h3><table id="npcs-table"><thead><tr><th>用户名</th><th>殖民地</th><th>性格</th><th>难度</th><th>积分</th><th>金币</th><th>战力</th><th>模型</th><th>状态</th><th>操作</th></tr></thead><tbody></tbody></table></div>
    </div>

    <div class="panel" id="panel-stocks">
      <div class="card"><h3>添加股票</h3>
        <div class="form-row">
          <div class="form-group"><label>股票代码</label><input id="stock-code" placeholder="XC600021"></div>
          <div class="form-group"><label>股票名称</label><input id="stock-name" placeholder="新星际公司"></div>
          <div class="form-group"><label>板块</label><input id="stock-sector" placeholder="科技"></div>
        </div>
        <div class="form-row">
          <div class="form-group"><label>初始价格</label><input id="stock-price" type="number" step="0.01" value="100.00"></div>
        </div>
        <button class="btn btn-primary" onclick="addStock()">添加股票</button>
      </div>
      <div class="card"><h3>股票列表</h3><table id="stocks-table"><thead><tr><th>代码</th><th>名称</th><th>板块</th><th>现价</th><th>涨跌幅</th><th>成交量</th><th>状态</th><th>操作</th></tr></thead><tbody></tbody></table></div>
    </div>

    <div class="panel" id="panel-market">
      <div class="card"><h3>市场干预</h3>
        <div class="form-row">
          <div class="form-group"><label>目标股票</label><select id="intervene-stock"></select></div>
          <div class="form-group"><label>操作</label><select id="intervene-action"><option value="push_up">拉升股价</option><option value="push_down">打压股价</option><option value="stabilize">稳定价格</option><option value="halt">停牌</option></select></div>
        </div>
        <button class="btn btn-warning" onclick="doIntervene()">执行干预</button>
      </div>
      <div class="card"><h3>实时股票行情</h3><table id="market-stocks-table"><thead><tr><th>代码</th><th>名称</th><th>现价</th><th>涨跌幅</th><th>成交量</th><th>操作</th></tr></thead><tbody></tbody></table></div>
    </div>

    <div class="panel" id="panel-forum">
      <div class="card"><h3>帖子管理</h3>
        <select id="forum-category-filter" onchange="loadForumPosts()" style="margin-bottom:12px;padding:6px 12px;background:var(--bg3);border:1px solid var(--border);border-radius:var(--radius);color:var(--text);">
          <option value="">全部分区</option><option value="general">综合讨论</option><option value="trade">交易市场</option><option value="strategy">策略研究</option><option value="social">社交</option>
        </select>
        <table id="forum-posts-table"><thead><tr><th>ID</th><th>分区</th><th>标题</th><th>作者</th><th>回复</th><th>点赞</th><th>置顶</th><th>时间</th><th>操作</th></tr></thead><tbody></tbody></table>
      </div>
    </div>

    <div class="panel" id="panel-factions">
      <div class="card"><h3>派系列表</h3><table id="factions-table"><thead><tr><th>ID</th><th>名称</th><th>口号</th><th>首领</th><th>成员</th><th>总分</th><th>思想</th><th>操作</th></tr></thead><tbody></tbody></table></div>
    </div>

    <div class="panel" id="panel-god-ai">
      <div class="card"><h3>上帝AI控制台</h3>
        <p style="color:var(--text2);font-size:13px;margin-bottom:12px">手动执行上帝AI操作或修改任意游戏数据</p>
        <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px">
          <button class="btn btn-primary" onclick="executeGodAI('balance_economy')">⚖️ 经济平衡</button>
          <button class="btn btn-warning" onclick="executeGodAI('weather_event')">🌦️ 天气事件</button>
          <button class="btn btn-success" onclick="executeGodAI('fix_data')">🔧 数据修复</button>
          <button class="btn btn-gold" onclick="executeGodAI('market_intervention')">💰 市场干预</button>
          <button class="btn btn-accent2" onclick="executeGodAI('stock_event')">📈 股市事件</button>
          <button class="btn btn-success" onclick="executeGodAI('reward_active')">🎁 奖励活跃</button>
        </div>
      </div>
      <div class="card"><h3>修改游戏数据</h3>
        <div class="form-row">
          <div class="form-group"><label>表名</label><select id="mod-table"><option value="colonies">colonies</option><option value="stocks">stocks</option><option value="resource_prices">resource_prices</option><option value="factions">factions</option><option value="territories">territories</option><option value="npc_bots">npc_bots</option><option value="users">users</option></select></div>
          <div class="form-group"><label>ID</label><input id="mod-id" type="number" placeholder="行ID"></div>
        </div>
        <div class="form-row">
          <div class="form-group"><label>字段名</label><input id="mod-field" placeholder="如 gold, current_price"></div>
          <div class="form-group"><label>新值</label><input id="mod-value" placeholder="新值"></div>
        </div>
        <button class="btn btn-danger" onclick="modifyData()">执行修改</button>
      </div>
      <div class="card"><h3>IPO/退市日历</h3><table id="ipo-table"><thead><tr><th>代码</th><th>名称</th><th>IPO价格</th><th>IPO日期</th><th>状态</th></tr></thead><tbody></tbody></table></div>
      <div class="card"><h3>上帝AI操作日志</h3><table id="god-logs-table"><thead><tr><th>时间</th><th>操作类型</th><th>描述</th></tr></thead><tbody></tbody></table></div>
    </div>

    <div class="panel" id="panel-config">
      <div class="card"><h3>系统配置</h3>
        <div id="config-form"></div>
        <div class="form-row" style="margin-top:12px">
          <div class="form-group"><label>配置键</label><input id="cfg-key" placeholder="config_key"></div>
          <div class="form-group"><label>配置值</label><input id="cfg-value" placeholder="config_value"></div>
        </div>
        <button class="btn btn-primary" onclick="addConfig()">保存配置</button>
      </div>
    </div>
  </div>
</div>

<script>
let token = localStorage.getItem('admin_token');
const API = '/admin/api';
let currentUserId = null;

async function api(path, method='GET', body=null) {
  const opts = { method, headers: { 'Authorization': 'Bearer ' + token } };
  if (body) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  const r = await fetch(API + path, opts);
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || data.msg || '请求失败');
  return data;
}

function showAlert(msg, type='success') {
  const d = document.getElementById('alerts');
  d.innerHTML = `<div class="alert alert-${type}">${msg}</div>`;
  setTimeout(() => d.innerHTML = '', 3000);
}

async function doLogin() {
  try {
    const u = document.getElementById('login-user').value;
    const p = document.getElementById('login-pass').value;
    const r = await fetch(API + '/login', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({username:u, password:p}) });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail);
    token = data.access_token;
    localStorage.setItem('admin_token', token);
    document.getElementById('login-screen').style.display = 'none';
    document.getElementById('app-screen').style.display = 'block';
    loadDashboard();
  } catch(e) { document.getElementById('login-error').textContent = e.message; }
}

function doLogout() {
  localStorage.removeItem('admin_token'); token = null;
  document.getElementById('login-screen').style.display = 'flex';
  document.getElementById('app-screen').style.display = 'none';
}

document.querySelectorAll('.nav-item').forEach(item => {
  item.addEventListener('click', () => {
    document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
    item.classList.add('active');
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    document.getElementById('panel-' + item.dataset.panel).classList.add('active');
    document.getElementById('panel-title').textContent = item.textContent.trim();
    const loader = item.dataset.panel;
    if (loader === 'dashboard') loadDashboard();
    else if (loader === 'users') loadUsers();
    else if (loader === 'api-keys') loadApiKeys();
    else if (loader === 'models') loadModels();
    else if (loader === 'npcs') loadNpcs();
    else if (loader === 'stocks') loadStocks();
    else if (loader === 'market') loadMarket();
    else if (loader === 'forum') loadForumPosts();
    else if (loader === 'factions') loadFactions();
    else if (loader === 'god-ai') loadGodAI();
    else if (loader === 'config') loadConfig();
  });
});

async function loadDashboard() {
  const d = await api('/dashboard');
  const s = d.stats;
  document.getElementById('stats-grid').innerHTML = `
    <div class="stat-card"><div class="value">${s.total_users}</div><div class="label">玩家总数</div></div>
    <div class="stat-card"><div class="value" style="color:var(--red)">${s.banned_users}</div><div class="label">封禁用户</div></div>
    <div class="stat-card"><div class="value">${s.total_npcs}</div><div class="label">NPC数量</div></div>
    <div class="stat-card"><div class="value">${s.total_colonies}</div><div class="label">殖民地总数</div></div>
    <div class="stat-card"><div class="value">${s.total_posts}</div><div class="label">论坛帖子</div></div>
    <div class="stat-card"><div class="value">${s.total_trades}</div><div class="label">资源交易</div></div>
    <div class="stat-card"><div class="value">${s.total_stock_trades}</div><div class="label">股票交易</div></div>
    <div class="stat-card"><div class="value">${s.total_stocks}</div><div class="label">上市股票</div></div>
    <div class="stat-card"><div class="value">${(s.total_gold/1000000).toFixed(1)}M</div><div class="label">金币流通量</div></div>
  `;
  document.querySelector('#top-stocks tbody').innerHTML = d.top_stocks.map(s =>
    `<tr><td>${s.code}</td><td>${s.name}</td><td>${s.current_price.toFixed(2)}</td>
    <td class="${s.change_pct>=0?'price-up':'price-down'}">${s.change_pct>=0?'+':''}${s.change_pct.toFixed(2)}%</td>
    <td>${s.volume}</td></tr>`
  ).join('');
  document.querySelector('#top-players tbody').innerHTML = d.top_colonies.map(c =>
    `<tr><td>${c.name}</td><td>${c.username}</td><td>${c.score}</td><td>${c.gold}</td><td>${c.attack_power}</td></tr>`
  ).join('');
  if (d.ai_models) {
    document.querySelector('#ai-models-table tbody').innerHTML = d.ai_models.map(m =>
      `<tr><td>${m.provider}</td><td>${m.name}</td><td>${m.model_name}</td>
      <td>${m.is_default?'⭐':''}</td><td><span class="badge ${m.is_active?'badge-active':'badge-inactive'}">${m.is_active?'活跃':'停用'}</span></td></tr>`
    ).join('');
  }
}

// ===== 用户管理 =====
async function loadUsers() {
  const search = document.getElementById('user-search')?.value || '';
  const d = await api('/users?search=' + encodeURIComponent(search));
  document.querySelector('#users-table tbody').innerHTML = d.users.map(u => `
    <tr>
      <td>${u.id}</td><td>${u.username}</td><td>${u.email}</td>
      <td>${u.colony_name||'-'}</td><td>Lv.${u.level||0}</td><td>${u.gold||0}</td><td>${u.score||0}</td>
      <td>${u.is_npc?'<span class="badge badge-npc">NPC</span>':''}</td>
      <td>${u.is_banned?'<span class="badge badge-banned">封禁</span>':'<span class="badge badge-active">正常</span>'}</td>
      <td><button class="btn btn-sm btn-primary" onclick="openUserModal(${u.id},'${u.username}',${u.gold||0},${u.minerals||0},${u.energy||0},${u.food||0})">管理</button></td>
    </tr>`).join('');
}
function openUserModal(id, name, gold, minerals, energy, food) {
  currentUserId = id;
  document.getElementById('um-username').textContent = name;
  document.getElementById('um-info').innerHTML = `金币: ${gold} | 矿: ${minerals} | 能: ${energy} | 食: ${food}`;
  const modal = document.getElementById('user-manage-modal');
  modal.style.display = 'flex';
}
function closeUserModal() {
  document.getElementById('user-manage-modal').style.display = 'none';
  currentUserId = null;
}
async function manageUser(action) {
  if (!currentUserId) return;
  let value = '';
  if (action === 'modify_gold') { value = prompt('输入新的金币数量:'); if (!value) return; }
  else if (action === 'modify_resources') { value = prompt('输入资源（格式：矿,能,食,金）:'); if (!value) return; }
  else if (action === 'reset_password') { value = prompt('输入新密码（6位以上）:'); if (!value) return; }
  else if (action === 'delete') { if (!confirm('确认删除该用户？此操作不可撤销！')) return; }
  else if (action === 'ban') { if (!confirm('确认封禁该用户？')) return; }
  try {
    const d = await api('/users/manage', 'POST', { user_id: currentUserId, action, value });
    showAlert(d.msg); closeUserModal(); loadUsers();
  } catch(e) { showAlert(e.message, 'error'); }
}

async function loadApiKeys() {
  const d = await api('/api-keys');
  document.querySelector('#keys-table tbody').innerHTML = d.keys.map(k =>
    `<tr><td>${k.id}</td><td>${k.provider}</td><td>${k.key_name}</td><td>${k.api_key.substring(0,20)}...</td>
    <td><span class="badge ${k.is_active?'badge-active':'badge-inactive'}">${k.is_active?'启用':'禁用'}</span></td>
    <td><button class="btn btn-danger btn-sm" onclick="deleteApiKey(${k.id})">删除</button></td></tr>`
  ).join('');
}
async function addApiKey() { await api('/api-keys', 'POST', { provider: document.getElementById('key-provider').value, key_name: document.getElementById('key-name').value, api_key: document.getElementById('key-value').value, api_base: document.getElementById('key-base').value }); showAlert('API Key添加成功'); loadApiKeys(); }
async function deleteApiKey(id) { if (!confirm('确认删除？')) return; await api('/api-keys/' + id, 'DELETE'); showAlert('已删除'); loadApiKeys(); }

async function loadModels() {
  const d = await api('/model-configs');
  document.querySelector('#models-table tbody').innerHTML = d.models.map(m =>
    `<tr><td>${m.id}</td><td>${m.provider}</td><td>${m.model_name}</td><td>${m.model_id}</td><td>${m.api_url||'-'}</td>
    <td>${m.max_tokens}</td><td>${m.is_default?'⭐':''}</td>
    <td><button class="btn btn-danger btn-sm" onclick="deleteModel(${m.id})">删除</button></td></tr>`
  ).join('');
  if (d.ai_models) {
    document.querySelector('#ai-models-admin-table tbody').innerHTML = d.ai_models.map(m =>
      `<tr><td>${m.id}</td><td>${m.provider}</td><td>${m.name}</td><td>${m.model_name}</td>
      <td>${m.is_default?'⭐':''}</td><td><span class="badge ${m.is_active?'badge-active':'badge-inactive'}">${m.is_active?'活跃':'停用'}</span></td></tr>`
    ).join('');
  }
}
async function addModel() {
  try {
    await api('/model-configs', 'POST', {
      provider: document.getElementById('model-provider').value,
      model_name: document.getElementById('model-name').value,
      model_id: document.getElementById('model-id').value,
      api_url: document.getElementById('model-url').value,
      api_key: document.getElementById('model-key').value,
      max_tokens: parseInt(document.getElementById('model-tokens').value),
      temperature: parseFloat(document.getElementById('model-temp').value),
      is_default: document.getElementById('model-default').checked
    });
    showAlert('模型配置添加成功'); loadModels();
  } catch(e) { showAlert(e.message, 'error'); }
}
async function deleteModel(id) { if (!confirm('确认删除？')) return; await api('/model-configs/' + id, 'DELETE'); showAlert('已删除'); loadModels(); }
async function testModel() {
  showAlert('正在测试连接...', 'success');
  try {
    const d = await api('/model-configs/test', 'POST', {
      provider: document.getElementById('model-provider').value,
      model_name: document.getElementById('model-name').value,
      model_id: document.getElementById('model-id').value,
      api_url: document.getElementById('model-url').value,
      api_key: document.getElementById('model-key').value,
      max_tokens: parseInt(document.getElementById('model-tokens').value),
      temperature: parseFloat(document.getElementById('model-temp').value),
      is_default: document.getElementById('model-default').checked
    });
    showAlert(d.msg, d.success ? 'success' : 'error');
  } catch(e) { showAlert('测试失败: ' + e.message, 'error'); }
}

async function loadNpcs() {
  const d = await api('/npcs');
  document.querySelector('#npcs-table tbody').innerHTML = d.npcs.map(n =>
    `<tr><td>${n.username}</td><td>${n.colony_name}</td><td>${n.personality}</td><td>${n.difficulty}</td>
    <td>${n.score}</td><td>${n.gold}</td><td>${n.attack_power}</td>
    <td>${n.model_name || '简单AI'}</td>
    <td><span class="badge ${n.is_active?'badge-active':'badge-inactive'}">${n.is_active?'活跃':'停用'}</span></td>
    <td><button class="btn btn-warning btn-sm" onclick="toggleNpc(${n.user_id})">${n.is_active?'停用':'启用'}</button>
    <button class="btn btn-danger btn-sm" onclick="deleteNpc(${n.user_id})">删除</button></td></tr>`
  ).join('');
}
async function addNpc() { await api('/npcs', 'POST', { username: document.getElementById('npc-username').value, colony_name: document.getElementById('npc-colony').value, personality: document.getElementById('npc-personality').value, difficulty: parseInt(document.getElementById('npc-difficulty').value), trade_freq: parseInt(document.getElementById('npc-freq').value), model_name: document.getElementById('npc-model').value }); showAlert('NPC创建成功'); loadNpcs(); }
async function toggleNpc(uid) { await api('/npcs/' + uid + '/toggle', 'PUT'); showAlert('NPC状态已切换'); loadNpcs(); }
async function deleteNpc(uid) { if (!confirm('确认删除？')) return; await api('/npcs/' + uid, 'DELETE'); showAlert('已删除'); loadNpcs(); }

async function loadStocks() {
  const d = await api('/stocks');
  document.querySelector('#stocks-table tbody').innerHTML = d.stocks.map(s =>
    `<tr><td>${s.code}</td><td>${s.name}</td><td>${s.sector}</td>
    <td>${s.current_price.toFixed(2)}</td>
    <td class="${s.change_pct>=0?'price-up':'price-down'}">${s.change_pct>=0?'+':''}${s.change_pct.toFixed(2)}%</td>
    <td>${s.volume}</td>
    <td><span class="badge ${s.is_active?'badge-active':'badge-inactive'}">${s.is_active?'交易中':'停牌'}</span></td>
    <td><button class="btn btn-warning btn-sm" onclick="toggleHalt('${s.code}')">${s.is_active?'停牌':'复牌'}</button>
    <button class="btn btn-danger btn-sm" onclick="deleteStock('${s.code}')">删除</button></td></tr>`
  ).join('');
  const sel = document.getElementById('intervene-stock');
  sel.innerHTML = d.stocks.map(s => `<option value="${s.code}">${s.code} ${s.name}</option>`).join('');
}
async function addStock() { await api('/stocks', 'POST', { code: document.getElementById('stock-code').value, name: document.getElementById('stock-name').value, sector: document.getElementById('stock-sector').value, initial_price: parseFloat(document.getElementById('stock-price').value) }); showAlert('股票添加成功'); loadStocks(); }
async function toggleHalt(code) { await api('/market/halt/' + code, 'POST'); showAlert('股票状态已切换'); loadStocks(); }
async function deleteStock(code) { if (!confirm('确认删除？')) return; await api('/stocks/' + code, 'DELETE'); showAlert('已删除'); loadStocks(); }

async function loadMarket() {
  const d = await api('/stocks');
  document.querySelector('#market-stocks-table tbody').innerHTML = d.stocks.map(s =>
    `<tr><td>${s.code}</td><td>${s.name}</td><td>${s.current_price.toFixed(2)}</td>
    <td class="${s.change_pct>=0?'price-up':'price-down'}">${s.change_pct>=0?'+':''}${s.change_pct.toFixed(2)}%</td>
    <td>${s.volume}</td>
    <td><button class="btn btn-warning btn-sm" onclick="quickIntervene('${s.code}')">干预</button>
    <button class="btn btn-danger btn-sm" onclick="toggleHalt('${s.code}')">停/复牌</button></td></tr>`
  ).join('');
  document.getElementById('intervene-stock').innerHTML = d.stocks.map(s => `<option value="${s.code}">${s.code} ${s.name}</option>`).join('');
}
async function doIntervene() { await api('/market/intervene', 'POST', { stock_code: document.getElementById('intervene-stock').value, action: document.getElementById('intervene-action').value }); showAlert('干预已执行'); loadMarket(); }
async function quickIntervene(code) { document.getElementById('intervene-stock').value = code; document.getElementById('intervene-stock').scrollIntoView(); }

async function loadForumPosts() {
  const cat = document.getElementById('forum-category-filter').value;
  const d = await api('/forum/posts?category=' + cat);
  document.querySelector('#forum-posts-table tbody').innerHTML = d.posts.map(p =>
    `<tr><td>${p.id}</td><td>${p.category}</td><td>${p.title}</td><td>${p.author_name}</td>
    <td>${p.reply_count}</td><td>${p.like_count}</td><td>${p.is_pinned?'📌':''}</td>
    <td>${p.created_at ? new Date(p.created_at).toLocaleDateString('zh-CN') : ''}</td>
    <td><button class="btn btn-warning btn-sm" onclick="pinPost(${p.id},${p.is_pinned?0:1})">${p.is_pinned?'取消置顶':'置顶'}</button>
    <button class="btn btn-danger btn-sm" onclick="deletePost(${p.id})">删除</button></td></tr>`
  ).join('');
}
async function pinPost(id, pin) { await api('/forum/manage', 'POST', { post_id: id, action: pin ? 'pin' : 'unpin' }); showAlert('操作成功'); loadForumPosts(); }
async function deletePost(id) { if (!confirm('确认删除？')) return; await api('/forum/manage', 'POST', { post_id: id, action: 'delete' }); showAlert('已删除'); loadForumPosts(); }

async function loadFactions() {
  const d = await api('/factions');
  document.querySelector('#factions-table tbody').innerHTML = d.factions.map(f =>
    `<tr><td>${f.id}</td><td>${f.name}</td><td>${f.motto||''}</td><td>${f.leader_name||'无'}</td>
    <td>${f.member_count}</td><td>${f.total_score}</td><td>${f.ideology}</td>
    <td><button class="btn btn-danger btn-sm" onclick="disbandFaction(${f.id})">解散</button></td></tr>`
  ).join('');
}
async function disbandFaction(id) { if (!confirm('确认解散？')) return; await api('/factions/manage', 'POST', { faction_id: id, action: 'disband' }); showAlert('已解散'); loadFactions(); }

// ===== V7: 上帝AI =====
async function loadGodAI() {
  try {
    const d = await api('/god-ai/logs');
    document.querySelector('#god-logs-table tbody').innerHTML = d.logs.map(l =>
      `<tr><td>${l.created_at ? new Date(l.created_at).toLocaleString('zh-CN') : ''}</td><td>${l.action_type}</td><td>${l.description}</td></tr>`
    ).join('');
  } catch(e) {}
  try {
    const d = await api('/stocks/ipo-calendar');
    document.querySelector('#ipo-table tbody').innerHTML = d.ipos.map(i =>
      `<tr><td>${i.stock_code}</td><td>${i.stock_name}</td><td>${i.ipo_price}</td><td>${i.ipo_date}</td><td><span class="badge ${i.status==='listed'?'badge-active':'badge-inactive'}">${i.status}</span></td></tr>`
    ).join('');
  } catch(e) {}
}

async function executeGodAI(action) {
  if (!confirm('确认执行上帝AI操作: ' + action + '？')) return;
  try {
    const d = await api('/god-ai/execute', 'POST', { action });
    showAlert(d.msg);
    loadGodAI();
  } catch(e) { showAlert(e.message, 'error'); }
}

async function modifyData() {
  const table = document.getElementById('mod-table').value;
  const id = parseInt(document.getElementById('mod-id').value);
  const field = document.getElementById('mod-field').value;
  const value = document.getElementById('mod-value').value;
  if (!id || !field || !value) { showAlert('请填写完整', 'error'); return; }
  if (!confirm(`确认修改 ${table} id=${id} 的 ${field} 为 ${value}？`)) return;
  try {
    const d = await api('/god-ai/modify', 'POST', { table_name: table, row_id: id, field, value });
    showAlert(d.msg);
  } catch(e) { showAlert(e.message, 'error'); }
}

async function loadConfig() {
  const d = await api('/config');
  document.getElementById('config-form').innerHTML = d.configs.map(c =>
    `<div class="form-row" style="margin-bottom:8px"><div class="form-group"><label>${c.config_key}</label><input value="${c.config_value}" onchange="updateConfig('${c.config_key}', this.value)"></div></div>`
  ).join('');
}
async function addConfig() { await api('/config', 'POST', { config_key: document.getElementById('cfg-key').value, config_value: document.getElementById('cfg-value').value }); showAlert('配置已保存'); loadConfig(); }
async function updateConfig(key, value) { await api('/config', 'POST', { config_key: key, config_value: value }); showAlert(key + ' 已更新'); }

if (token) {
  api('/check').then(() => { document.getElementById('login-screen').style.display = 'none'; document.getElementById('app-screen').style.display = 'block'; loadDashboard(); }).catch(() => { localStorage.removeItem('admin_token'); token = null; });
}
</script>
</body>
</html>"""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=58018)
