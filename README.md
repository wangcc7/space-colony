# 星际殖民地 Space Colony

> AI 设计 · AI 运营 · 完全自运转的浏览器策略游戏

## 一键部署

```bash
# 1. 上传整个 space-colony 目录到服务器
scp -r space-colony root@<your-server>:/root/

# 2. SSH 进服务器
ssh root@<your-server>
cd /root/space-colony

# 3. 启动
docker-compose up -d --build

# 4. 查看状态
docker-compose ps
docker-compose logs -f backend
```

访问 `http://<服务器IP>/` 即可开始游戏。

---

## 游戏玩法

### 注册 & 登录
- 注册时选择用户名、邮箱、殖民地名称和星球类型
- 支持 4 种星球类型：类地 / 荒漠 / 冰封 / 火山

### 建造系统
- 殖民地有 3×3 共 9 个格子
- 5 种建筑可建造：

| 建筑 | 消耗 | 每日产出 |
|------|------|---------|
| ⛏ 矿山 | 矿50 能20 | +30矿 |
| ☀️ 太阳能站 | 矿40 食10 | +40能 |
| 🌾 农场 | 矿30 能20 | +35食 |
| 🔬 研究室 | 矿80 能50 食30 | +5矿+5能 |
| 🛡 兵营 | 矿60 能40 食40 | 提升防御 |

### AI 每日事件
- **每天凌晨1点**自动结算：建筑产出 + AI 随机事件
- 15 种事件：增益、灾难、入侵、发现，随机触发
- 每个事件有 ±20% 随机浮动

### 排行榜
- 实时积分排行，前三名金银铜奖牌

---

## 目录结构

```
space-colony/
├── docker-compose.yml
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── main.py          # FastAPI + AI事件引擎
├── frontend/
│   └── index.html       # 单页游戏前端
├── nginx/
│   └── default.conf     # 反代配置
└── db/
    └── init.sql         # 数据库初始化
```

---

## 手动触发每日结算（管理员）

```bash
curl -X POST http://localhost/api/admin/settle \
  -H "X-Admin-Key: admin-secret-2026"
```

---

## 自定义配置

修改 `docker-compose.yml` 中的环境变量：
- `SECRET_KEY`: JWT 签名密钥（生产环境请务必修改）
- `ADMIN_KEY`: 管理员接口密钥
