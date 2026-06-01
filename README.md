# 🚀 星际殖民地 Space Colony V9.0

<h3 align="center">🌌 AI 自主运营的多人太空殖民模拟游戏</h3>
<p align="center">
  <b>17 大游戏系统 · 40+ 数据库表 · 零前端依赖 · Docker 一键部署</b>
</p>

<p align="center">
  <a href="http://150.158.10.10:8081"><img src="https://img.shields.io/badge/🎮_在线试玩-150.158.10.10:8081-00d4ff?style=for-the-badge" alt="Demo"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=for-the-badge" alt="License"></a>
  <a href="#"><img src="https://img.shields.io/badge/version-9.0_深渊纪元-ff4444?style=for-the-badge" alt="Version"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-blue?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-latest-009688?logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/MySQL-5.7-4479A1?logo=mysql" alt="MySQL">
  <img src="https://img.shields.io/badge/Redis-latest-DC382D?logo=redis" alt="Redis">
  <img src="https://img.shields.io/badge/Docker-🐳-2496ED?logo=docker" alt="Docker">
  <img src="https://img.shields.io/badge/Nginx-1.25-009639?logo=nginx" alt="Nginx">
  <img src="https://img.shields.io/badge/前端-原生_JS_零依赖-FFD43B?logo=javascript" alt="Vanilla JS">
  <img src="https://img.shields.io/badge/后端-6500行_FastAPI-009688" alt="Backend Lines">
</p>

---

## 🤔 这是什么？

一个浏览器打开就能玩的太空殖民策略游戏——**但和传统游戏不同**：

> 🧠 **股市价格、NPC 对话、战争结果、每日事件——全部由 AI 算法实时驱动，无需人工运营。**

你扮演星际殖民地的统治者：挖矿建设、炒股投机、加杠杆做期货、加入派系发动战争、竞技场 PK 上分、派遣间谍窃取情报……**致富路线不止一条**。

但小心——**90% 的玩家会在股市里亏光**。这不是 bug，是设计。

---

## 🎯 游戏系统一览

| 🏗️ 经济建设 | ⚔️ 冲突对抗 | 💬 社交世界 |
|:---|:---|:---|
| 3×3 格子殖民建造 | 6×6 阵型战争博弈 | AI NPC 群体聊天（经济/政治/军事）|
| 8 支动态股票 + K 线 | 派系宣战/联盟/和平 | 论坛发帖讨论 |
| 1-10 倍杠杆期货多空 | 竞技场 ELO 排位 | 赏金悬赏仇敌 |
| 9 种资源 + 合成系统 | 间谍渗透/策反 | 排行榜竞争 |
| 星际领地占领与争夺 | 防御工事 + 护盾 | 成就 & 每日任务 |
| 舰队远征探索 8 大星区 | 复仇系统 1.5x 掠夺 | 通知中心 |

**股市细节**：标准差 0.045（远高于真实市场）、5% 黑天鹅事件、±10% 涨跌停、T+1 结算、滑点 0.5~2%、0.3% 佣金 + 0.1% 印花税——**仿 A 股真实费率**。

**NPC 聊天细节**：6 个讨论话题、每个话题 4 种观点、50% 概率发起群体讨论、30% 概率回复他人——**不再是各说各话**，而是像真实群聊。

---

## 🏗️ 技术架构

```
         Internet
            │
     ┌──────▼──────┐
     │    Nginx    │  ← 反向代理 + 静态文件
     │    :80      │
     └──┬──────┬───┘
        │      │
   ┌────▼──┐ ┌─▼──────────┐
   │ 前端   │ │  Backend   │  ← FastAPI :8000 (~3500行)
   │ HTML   │ │  Admin     │  ← FastAPI :58018 (~1500行)
   │ SPA    │ │  :8000     │
   └───────┘ └─┬──────┬───┘
               │      │
        ┌──────▼─┐ ┌──▼──────┐
        │ MySQL  │ │  Redis  │
        │ 5.7    │ │  Cache  │
        │ :3306  │ │  :6379  │
        └────────┘ └─────────┘
```

| 层 | 技术栈 | 亮点 |
|:---|:---|:---|
| 后端 | FastAPI + aiomysql + Redis + APScheduler | 全异步、定时任务驱动 AI 引擎 |
| 前端 | 原生 HTML/CSS/JS 单页应用 | **零框架依赖**，一个文件包含完整 UI |
| 数据库 | MySQL 5.7（40+ 张表） | 完整游戏世界建模 |
| 部署 | Docker Compose（5 容器） | 一条命令拉起全部服务 |
| AI | 随机漫步 + 话题池 + 事件触发 | 股市/NPC/事件全自动运转 |

---

## 🚀 30 秒部署

```bash
git clone https://github.com/wangcc7/space-colony.git
cd space-colony
docker-compose up -d --build
```

打开浏览器访问 `http://<你的IP>:8081` 开始游戏。

**要求**：Docker 20.10+ · 2GB+ 内存 · 1 核 CPU

管理后台：`http://<你的IP>:58018/admin`（admin / admin888）

---

## 📂 项目结构

```
space-colony/
├── docker-compose.yml       # 容器编排（5 个服务）
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt     # FastAPI + aiomysql + Redis + JWT
│   └── main.py              # 🎮 游戏主程序 (~3500行)
├── frontend/
│   └── index.html           # 🖥️ 完整前端 SPA (~1300行)
├── admin/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── main.py              # 🔧 管理后台 (~1500行)
├── nginx/
│   └── default.conf         # 反向代理配置
├── db/
│   ├── charset.cnf
│   └── init.sql             # 🗄️ 完整建表 + 种子数据 (771行)
├── DESIGN.md                # 📖 游戏设计文档
├── LICENSE                  # MIT
└── README.md
```

---

## 📖 深入了解

想知道为什么故意让 90% 玩家在股市亏钱？NPC 聊天系统怎么从"各说各话"变成"群体讨论"？战争阵型的剪刀石头布博弈矩阵？

👉 **[阅读完整设计文档 DESIGN.md](./DESIGN.md)**

---

## 🎮 版本演进

| 版本 | 代号 | 里程碑 |
|:---|:---|:---|
| V5.x | 基础纪元 | 建造 · 聊天 · 排行 · 合成 |
| V6.x | 殖民扩张 | 股票 · 领地 · 派系 · 探险 |
| V7.x | 商业时代 | 期货 · 任务 · 成就 |
| V8.0 | 战争纪元 | 袭击 · 防御 · 赏金 · 竞技场 · 间谍 · 跨模块联动 |
| **V9.0** | **深渊纪元** | 🔥 股市黑天鹅 · 智能群聊 · 一键操作 · 全面修复 |

---

## 👤 关于

**作者**：wangcc

这个项目的特别之处——**全部 6500+ 行代码由 AI（WorkBuddy）辅助生成**，从游戏规则设计到数据库建模，从行情算法到 NPC 人格系统。这是一个实验：AI 能独立设计和运营一个完整的多人游戏吗？

答案：V5 → V9，迭代还在继续。

- 🐙 GitHub: [@wangcc7](https://github.com/wangcc7)
- 🎮 Demo: [http://150.158.10.10:8081](http://150.158.10.10:8081)

---

## 📜 License

MIT — 随意使用、修改、分发。如果部署了自己的版本，欢迎告诉我！

---

<p align="center">
  <b>⭐ 觉得有意思？点个 Star，让更多人发现这个 AI 创造的游戏世界</b>
</p>
