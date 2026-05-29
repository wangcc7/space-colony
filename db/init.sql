-- =============================================
-- 星际殖民地 V4 - 完整数据库Schema
-- 26张原有表 + 新增股票/AI/成就等表
-- =============================================
SET NAMES utf8mb4;

-- ---------- 原有核心表（保留） ----------
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(32) NOT NULL UNIQUE,
    email VARCHAR(128) NOT NULL UNIQUE,
    password_hash VARCHAR(128) NOT NULL,
    is_npc TINYINT(1) DEFAULT 0,
    is_admin TINYINT(1) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS colonies (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,
    name VARCHAR(64) NOT NULL,
    level INT DEFAULT 1,
    xp INT DEFAULT 0,
    planet_type VARCHAR(32) DEFAULT 'terran',
    minerals INT DEFAULT 500,
    energy INT DEFAULT 500,
    food INT DEFAULT 500,
    gold INT DEFAULT 1000,
    attack_power INT DEFAULT 10,
    defense_power INT DEFAULT 10,
    score INT DEFAULT 0,
    win_count INT DEFAULT 0,
    lose_count INT DEFAULT 0,
    happiness INT DEFAULT 50,
    culture INT DEFAULT 0,
    reputation INT DEFAULT 0,
    investment_amount INT DEFAULT 0,
    investment_returns INT DEFAULT 0,
    is_invested TINYINT(1) DEFAULT 0,
    offline_accumulation_hours INT DEFAULT 0,
    last_online TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS buildings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    colony_id INT NOT NULL,
    building_type VARCHAR(32) NOT NULL,
    slot INT NOT NULL,
    level INT DEFAULT 1,
    built_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (colony_id) REFERENCES colonies(id) ON DELETE CASCADE,
    UNIQUE KEY uk_colony_slot (colony_id, slot)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS techs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    colony_id INT NOT NULL,
    tech_type VARCHAR(32) NOT NULL,
    level INT DEFAULT 0,
    FOREIGN KEY (colony_id) REFERENCES colonies(id) ON DELETE CASCADE,
    UNIQUE KEY uk_colony_tech (colony_id, tech_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS battle_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    attacker_id INT NOT NULL,
    defender_id INT NOT NULL,
    result VARCHAR(16) NOT NULL,
    gold_stolen INT DEFAULT 0,
    minerals_stolen INT DEFAULT 0,
    energy_stolen INT DEFAULT 0,
    food_stolen INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (attacker_id) REFERENCES colonies(id) ON DELETE CASCADE,
    FOREIGN KEY (defender_id) REFERENCES colonies(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS market_orders (
    id INT AUTO_INCREMENT PRIMARY KEY,
    colony_id INT NOT NULL,
    order_type VARCHAR(8) NOT NULL,
    resource_type VARCHAR(16) NOT NULL,
    amount INT NOT NULL,
    price INT NOT NULL,
    filled INT DEFAULT 0,
    status VARCHAR(16) DEFAULT 'open',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NULL,
    FOREIGN KEY (colony_id) REFERENCES colonies(id) ON DELETE CASCADE,
    INDEX idx_market_status (status, resource_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS territories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    planet_type VARCHAR(32) DEFAULT 'terran',
    bonus_minerals INT DEFAULT 0,
    bonus_energy INT DEFAULT 0,
    bonus_food INT DEFAULT 0,
    bonus_score INT DEFAULT 0,
    owner_colony INT,
    captured_at TIMESTAMP NULL,
    expires_at TIMESTAMP NULL DEFAULT '2099-12-31 23:59:59',
    is_active TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_territory_active (is_active, expires_at),
    FOREIGN KEY (owner_colony) REFERENCES colonies(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS daily_events (
    id INT AUTO_INCREMENT PRIMARY KEY,
    event_date DATE NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    title VARCHAR(128) NOT NULL,
    description TEXT NOT NULL,
    effect_minerals INT DEFAULT 0,
    effect_energy INT DEFAULT 0,
    effect_food INT DEFAULT 0,
    effect_score INT DEFAULT 0,
    effect_gold INT DEFAULT 0,
    effect_happiness INT DEFAULT 0,
    effect_market VARCHAR(16),
    effect_market_pct INT DEFAULT 0,
    is_global TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_event_date (event_date),
    INDEX idx_events_date (event_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS event_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    colony_id INT NOT NULL,
    event_id INT NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_colony_event (colony_id, event_id),
    FOREIGN KEY (colony_id) REFERENCES colonies(id) ON DELETE CASCADE,
    FOREIGN KEY (event_id) REFERENCES daily_events(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS rate_limit_login (
    ip VARCHAR(64) NOT NULL PRIMARY KEY,
    attempts INT DEFAULT 1,
    window_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS building_config (
    building_type VARCHAR(32) NOT NULL PRIMARY KEY,
    display_name VARCHAR(64) NOT NULL,
    cost_minerals INT DEFAULT 0,
    cost_energy INT DEFAULT 0,
    cost_food INT DEFAULT 0,
    cost_gold INT DEFAULT 0,
    produces_minerals INT DEFAULT 0,
    produces_energy INT DEFAULT 0,
    produces_food INT DEFAULT 0,
    produces_gold INT DEFAULT 0,
    attack_bonus INT DEFAULT 0,
    defense_bonus INT DEFAULT 0,
    happiness_bonus INT DEFAULT 0,
    description TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS tech_config (
    tech_type VARCHAR(32) NOT NULL PRIMARY KEY,
    display_name VARCHAR(64) NOT NULL,
    max_level INT DEFAULT 5,
    cost_minerals_per_level INT DEFAULT 100,
    cost_energy_per_level INT DEFAULT 80,
    cost_food_per_level INT DEFAULT 50,
    cost_gold INT DEFAULT 0,
    description TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------- V3原有新表 ----------
CREATE TABLE IF NOT EXISTS resource_prices (
    resource_type VARCHAR(16) NOT NULL PRIMARY KEY,
    current_price INT NOT NULL DEFAULT 100,
    base_price INT NOT NULL DEFAULT 100,
    min_price INT NOT NULL DEFAULT 20,
    max_price INT NOT NULL DEFAULT 500,
    total_volume INT DEFAULT 0,
    volatility INT DEFAULT 5,
    trend VARCHAR(16) DEFAULT 'stable',
    maker_balance INT DEFAULT 100000,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS market_prices (
    id INT AUTO_INCREMENT PRIMARY KEY,
    resource_type VARCHAR(16) NOT NULL,
    price INT NOT NULL,
    volume INT DEFAULT 0,
    change_pct INT DEFAULT 0,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_price_time (resource_type, recorded_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS trade_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    buyer_id INT,
    seller_id INT,
    resource_type VARCHAR(16) NOT NULL,
    amount INT NOT NULL,
    unit_price INT NOT NULL,
    total_gold INT NOT NULL,
    is_npc TINYINT(1) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_trade_time (created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS futures_contracts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    colony_id INT NOT NULL,
    resource_type VARCHAR(16) NOT NULL,
    direction VARCHAR(8) NOT NULL,
    amount INT NOT NULL,
    entry_price INT NOT NULL,
    leverage INT DEFAULT 2,
    margin INT NOT NULL,
    status VARCHAR(16) DEFAULT 'open',
    profit_loss INT DEFAULT 0,
    opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP NULL,
    FOREIGN KEY (colony_id) REFERENCES colonies(id) ON DELETE CASCADE,
    INDEX idx_futures_status (status, colony_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS forum_posts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    author_id INT NOT NULL,
    author_name VARCHAR(32) NOT NULL,
    category VARCHAR(16) DEFAULT 'general',
    title VARCHAR(128) NOT NULL,
    content TEXT NOT NULL,
    is_pinned TINYINT(1) DEFAULT 0,
    reply_count INT DEFAULT 0,
    like_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_forum_cat (category, is_pinned DESC, created_at DESC),
    FOREIGN KEY (author_id) REFERENCES colonies(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS forum_replies (
    id INT AUTO_INCREMENT PRIMARY KEY,
    post_id INT NOT NULL,
    author_id INT NOT NULL,
    author_name VARCHAR(32) NOT NULL,
    content TEXT NOT NULL,
    like_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (post_id) REFERENCES forum_posts(id) ON DELETE CASCADE,
    FOREIGN KEY (author_id) REFERENCES colonies(id) ON DELETE CASCADE,
    INDEX idx_reply_post (post_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS factions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL UNIQUE,
    motto VARCHAR(128),
    description TEXT,
    leader_id INT,
    member_count INT DEFAULT 1,
    total_score INT DEFAULT 0,
    ideology VARCHAR(32) DEFAULT 'balanced',
    tax_rate INT DEFAULT 5,
    treasury INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (leader_id) REFERENCES colonies(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS colony_factions (
    colony_id INT NOT NULL,
    faction_id INT NOT NULL,
    role VARCHAR(16) DEFAULT 'member',
    contribution INT DEFAULT 0,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (colony_id, faction_id),
    FOREIGN KEY (colony_id) REFERENCES colonies(id) ON DELETE CASCADE,
    FOREIGN KEY (faction_id) REFERENCES factions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS diplomacy (
    id INT AUTO_INCREMENT PRIMARY KEY,
    faction_a INT NOT NULL,
    faction_b INT NOT NULL,
    relation_type VARCHAR(16) DEFAULT 'neutral',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_diplo_pair (faction_a, faction_b)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS npc_bots (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,
    personality VARCHAR(16) DEFAULT 'balanced',
    difficulty INT DEFAULT 3,
    trade_freq INT DEFAULT 300,
    is_active TINYINT(1) DEFAULT 1,
    ai_model VARCHAR(64) DEFAULT 'rule_based',
    ai_api_url VARCHAR(256),
    ai_api_key VARCHAR(256),
    last_trade TIMESTAMP NULL,
    last_build TIMESTAMP NULL,
    last_post TIMESTAMP NULL,
    last_attack TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS notifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    colony_id INT NOT NULL,
    title VARCHAR(128) NOT NULL,
    content TEXT NOT NULL,
    ntype VARCHAR(16) DEFAULT 'info',
    is_read TINYINT(1) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (colony_id) REFERENCES colonies(id) ON DELETE CASCADE,
    INDEX idx_notif_unread (colony_id, is_read, created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS philosophy_config (
    philosophy_type VARCHAR(32) NOT NULL PRIMARY KEY,
    display_name VARCHAR(64) NOT NULL,
    max_level INT DEFAULT 5,
    cost_gold_base INT DEFAULT 500,
    description TEXT,
    bonus_type VARCHAR(32) NOT NULL,
    bonus_value INT DEFAULT 10
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS colony_philosophy (
    id INT AUTO_INCREMENT PRIMARY KEY,
    colony_id INT NOT NULL,
    philosophy_type VARCHAR(32) NOT NULL,
    level INT DEFAULT 0,
    UNIQUE KEY uk_colony_philo (colony_id, philosophy_type),
    FOREIGN KEY (colony_id) REFERENCES colonies(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- =============================================
-- V4 新增表：A股风格股票系统
-- =============================================

-- 股票基本信息（参考A股行业龙头）
CREATE TABLE IF NOT EXISTS stocks (
    code VARCHAR(8) NOT NULL PRIMARY KEY,
    name VARCHAR(32) NOT NULL,
    sector VARCHAR(32) NOT NULL,
    current_price DECIMAL(10,2) NOT NULL DEFAULT 10.00,
    open_price DECIMAL(10,2) DEFAULT 10.00,
    prev_close DECIMAL(10,2) DEFAULT 10.00,
    high_price DECIMAL(10,2) DEFAULT 10.00,
    low_price DECIMAL(10,2) DEFAULT 10.00,
    volume BIGINT DEFAULT 0,
    turnover DECIMAL(16,2) DEFAULT 0.00,
    change_pct DECIMAL(6,2) DEFAULT 0.00,
    change_amt DECIMAL(10,2) DEFAULT 0.00,
    market_cap BIGINT DEFAULT 1000000,
    pe_ratio DECIMAL(8,2) DEFAULT 0.00,
    pb_ratio DECIMAL(8,2) DEFAULT 0.00,
    amplitude DECIMAL(6,2) DEFAULT 0.00,
    turnover_rate DECIMAL(6,2) DEFAULT 0.00,
    is_active TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_stock_sector (sector),
    INDEX idx_stock_change (change_pct DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- K线数据（日K）
CREATE TABLE IF NOT EXISTS stock_klines (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(8) NOT NULL,
    k_date DATE NOT NULL,
    open_price DECIMAL(10,2) NOT NULL,
    high_price DECIMAL(10,2) NOT NULL,
    low_price DECIMAL(10,2) NOT NULL,
    close_price DECIMAL(10,2) NOT NULL,
    volume BIGINT DEFAULT 0,
    turnover DECIMAL(16,2) DEFAULT 0.00,
    change_pct DECIMAL(6,2) DEFAULT 0.00,
    INDEX idx_kline_date (stock_code, k_date),
    UNIQUE KEY uk_stock_kdate (stock_code, k_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 五档行情
CREATE TABLE IF NOT EXISTS stock_orderbook (
    id INT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(8) NOT NULL,
    direction VARCHAR(4) NOT NULL COMMENT 'buy/sell',
    price_level INT NOT NULL COMMENT '1-5档',
    price DECIMAL(10,2) NOT NULL,
    volume BIGINT DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_book_level (stock_code, direction, price_level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 股票交易记录
CREATE TABLE IF NOT EXISTS stock_trades (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    colony_id INT,
    stock_code VARCHAR(8) NOT NULL,
    direction VARCHAR(4) NOT NULL COMMENT 'buy/sell',
    price DECIMAL(10,2) NOT NULL,
    amount INT NOT NULL,
    total_gold DECIMAL(16,2) NOT NULL,
    commission DECIMAL(10,2) DEFAULT 0.00,
    is_npc TINYINT(1) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_stock_trade_time (stock_code, created_at DESC),
    FOREIGN KEY (colony_id) REFERENCES colonies(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 玩家持仓
CREATE TABLE IF NOT EXISTS stock_portfolios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    colony_id INT NOT NULL,
    stock_code VARCHAR(8) NOT NULL,
    amount INT DEFAULT 0,
    avg_cost DECIMAL(10,2) DEFAULT 0.00,
    total_cost DECIMAL(16,2) DEFAULT 0.00,
    current_value DECIMAL(16,2) DEFAULT 0.00,
    profit_loss DECIMAL(16,2) DEFAULT 0.00,
    profit_pct DECIMAL(6,2) DEFAULT 0.00,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_portfolio (colony_id, stock_code),
    FOREIGN KEY (colony_id) REFERENCES colonies(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 自选股
CREATE TABLE IF NOT EXISTS stock_watchlist (
    colony_id INT NOT NULL,
    stock_code VARCHAR(8) NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (colony_id, stock_code),
    FOREIGN KEY (colony_id) REFERENCES colonies(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 股票期货/合约
CREATE TABLE IF NOT EXISTS stock_futures (
    id INT AUTO_INCREMENT PRIMARY KEY,
    colony_id INT NOT NULL,
    stock_code VARCHAR(8) NOT NULL,
    direction VARCHAR(8) NOT NULL COMMENT 'long/short',
    amount INT NOT NULL,
    entry_price DECIMAL(10,2) NOT NULL,
    leverage INT DEFAULT 2,
    margin DECIMAL(16,2) NOT NULL,
    status VARCHAR(16) DEFAULT 'open',
    profit_loss DECIMAL(16,2) DEFAULT 0.00,
    opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP NULL,
    FOREIGN KEY (colony_id) REFERENCES colonies(id) ON DELETE CASCADE,
    INDEX idx_sfutures_status (status, colony_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- =============================================
-- V4 新增表：AI模型配置（管理后台用）
-- =============================================

CREATE TABLE IF NOT EXISTS ai_model_configs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    provider VARCHAR(32) NOT NULL COMMENT 'openai/deepseek/qwen/custom',
    name VARCHAR(64) NOT NULL,
    api_url VARCHAR(256) NOT NULL,
    api_key VARCHAR(512) NOT NULL,
    model_name VARCHAR(64) NOT NULL,
    max_tokens INT DEFAULT 2048,
    temperature DECIMAL(3,2) DEFAULT 0.70,
    is_default TINYINT(1) DEFAULT 0,
    is_active TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- NPC AI对话日志
CREATE TABLE IF NOT EXISTS npc_ai_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    npc_id INT NOT NULL,
    action_type VARCHAR(32) NOT NULL,
    prompt TEXT,
    response TEXT,
    tokens_used INT DEFAULT 0,
    duration_ms INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (npc_id) REFERENCES npc_bots(id) ON DELETE CASCADE,
    INDEX idx_ai_log_npc (npc_id, created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- =============================================
-- V4 新增表：成就系统
-- =============================================

CREATE TABLE IF NOT EXISTS achievements (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(32) NOT NULL UNIQUE,
    name VARCHAR(64) NOT NULL,
    description TEXT,
    category VARCHAR(16) NOT NULL COMMENT 'economy/combat/social/culture/stock',
    icon VARCHAR(32) DEFAULT 'trophy',
    reward_gold INT DEFAULT 0,
    reward_score INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS colony_achievements (
    id INT AUTO_INCREMENT PRIMARY KEY,
    colony_id INT NOT NULL,
    achievement_id INT NOT NULL,
    unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_colony_ach (colony_id, achievement_id),
    FOREIGN KEY (colony_id) REFERENCES colonies(id) ON DELETE CASCADE,
    FOREIGN KEY (achievement_id) REFERENCES achievements(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- =============================================
-- V4 新增表：星际探索 & 每日任务
-- =============================================

CREATE TABLE IF NOT EXISTS expeditions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    colony_id INT NOT NULL,
    target_sector VARCHAR(64) NOT NULL,
    fleet_size INT DEFAULT 1,
    duration_hours INT DEFAULT 2,
    status VARCHAR(16) DEFAULT 'preparing',
    reward_minerals INT DEFAULT 0,
    reward_energy INT DEFAULT 0,
    reward_food INT DEFAULT 0,
    reward_gold INT DEFAULT 0,
    reward_score INT DEFAULT 0,
    reward_discovery TEXT,
    started_at TIMESTAMP NULL,
    completed_at TIMESTAMP NULL,
    FOREIGN KEY (colony_id) REFERENCES colonies(id) ON DELETE CASCADE,
    INDEX idx_expedition_status (status, colony_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS daily_tasks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    task_date DATE NOT NULL,
    task_type VARCHAR(32) NOT NULL,
    title VARCHAR(128) NOT NULL,
    description TEXT,
    target_value INT NOT NULL,
    reward_gold INT DEFAULT 50,
    reward_score INT DEFAULT 10,
    is_global TINYINT(1) DEFAULT 1,
    UNIQUE KEY uk_daily_task (task_date, task_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS colony_daily_tasks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    colony_id INT NOT NULL,
    task_id INT NOT NULL,
    progress INT DEFAULT 0,
    is_completed TINYINT(1) DEFAULT 0,
    completed_at TIMESTAMP NULL,
    UNIQUE KEY uk_colony_daily (colony_id, task_id),
    FOREIGN KEY (colony_id) REFERENCES colonies(id) ON DELETE CASCADE,
    FOREIGN KEY (task_id) REFERENCES daily_tasks(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- =============================================
-- 配置数据种子
-- =============================================

-- 建筑配置
INSERT IGNORE INTO building_config VALUES
  ('mine','矿场',50,20,0,0,30,0,0,0,0,0,0,'每小时产出矿物 +30（每级）'),
  ('solar_plant','太阳能站',40,0,10,0,0,40,0,0,0,0,0,'每小时产出能量 +40'),
  ('farm','农场',30,20,0,0,0,0,35,0,0,0,0,'每小时产出食物 +35'),
  ('lab','研究所',80,50,30,0,5,5,0,0,0,0,0,'研究科技加速'),
  ('barracks','兵营',60,40,40,0,0,0,0,15,20,0,'攻击+15 防御+20'),
  ('shield_gen','护盾发生器',100,80,0,0,0,0,0,0,30,0,'防御+30'),
  ('trade_port','贸易港',70,30,20,50,0,0,0,5,0,0,0,'交易手续费降低10%'),
  ('cannon','离子炮',120,60,0,0,0,0,0,40,0,0,'攻击+40'),
  ('gold_mine','金矿',80,40,20,0,0,0,0,15,0,0,0,'每小时产出金币+15'),
  ('theater','剧院',40,10,20,30,0,0,0,0,0,0,10,'幸福度+10'),
  ('library','图书馆',60,20,10,40,0,0,0,0,0,0,5,'文化+5'),
  ('wall','防御墙',80,30,30,0,0,0,0,0,0,50,0,'防御+50');

-- 科技配置
INSERT IGNORE INTO tech_config VALUES
  ('mining','矿业科技',5,100,60,30,0,'矿物产出+20%/级'),
  ('energy','能源科技',5,80,100,20,0,'能量产出+20%/级'),
  ('farming','农业科技',5,60,40,100,0,'食物产出+20%/级'),
  ('military','军事科技',5,120,80,60,0,'攻击力+15%/级'),
  ('shield','护盾科技',5,100,100,40,0,'护盾值+15%/级'),
  ('storage','仓储科技',3,200,100,80,0,'存储上限+500/级'),
  ('trade','贸易科技',5,80,40,20,150,'交易优惠+10%/级'),
  ('culture','文化科技',5,60,30,30,200,'文化产出+20%/级');

-- 哲学配置
INSERT IGNORE INTO philosophy_config VALUES
  ('pragmatism','实用主义',5,500,'效率优先，资源产出最大化','production',10),
  ('utilitarian','功利主义',5,500,'最大多数人的最大幸福','happiness',15),
  ('existentialism','存在主义',5,600,'存在先于本质','resilience',20),
  ('daoism','道家思想',5,700,'道法自然，无为而治','defense',25),
  ('legalism','法家思想',5,700,'以法治国，令行禁止','attack',25),
  ('confucianism','儒家思想',5,800,'仁义礼智信','reputation',30),
  ('capitalism','资本论',5,600,'资本逻辑驱动市场','gold_bonus',20),
  ('cybernetics','控制论',5,900,'反馈与调节','efficiency',15);

-- 资源初始价格（基础+高级资源）
INSERT IGNORE INTO resource_prices VALUES
  ('minerals',100,100,20,500,0,5,'stable',100000,NOW()),
  ('energy',80,80,15,400,0,5,'stable',80000,NOW()),
  ('food',60,60,10,300,0,5,'stable',60000,NOW()),
  ('rare_metals',250,250,50,1000,0,8,'stable',50000,NOW()),
  ('crystals',180,180,30,800,0,7,'stable',40000,NOW()),
  ('plasma',350,350,80,1200,0,10,'stable',30000,NOW()),
  ('dark_matter',800,800,200,3000,0,15,'stable',20000,NOW()),
  ('antimatter',1200,1200,300,5000,0,20,'stable',10000,NOW());

-- =============================================
-- V4 股票种子数据（参考A股行业龙头）
-- =============================================
INSERT IGNORE INTO stocks (code,name,sector,current_price,prev_close,market_cap,pe_ratio) VALUES
  ('XC600001','星际矿业','矿业',15.80,15.60,158000000,12.50),
  ('XC600002','光能科技','新能源',28.50,28.20,285000000,35.20),
  ('XC600003','银河地产','房地产',6.80,6.85,68000000,5.60),
  ('XC600004','量子银行','金融',22.30,22.10,223000000,8.90),
  ('XC600005','天工制造','高端制造',35.60,35.20,356000000,28.30),
  ('XC600006','中华医药','医药',42.10,41.80,421000000,32.10),
  ('XC600007','芯片国际','半导体',68.50,67.20,685000000,55.60),
  ('XC600008','宇宙消费','消费',18.90,18.70,189000000,22.40),
  ('XC600009','星际传媒','传媒',12.30,12.50,123000000,18.70),
  ('XC600010','天网通信','通信',25.60,25.40,256000000,26.80),
  ('XC600011','深海能源','石油',18.20,18.00,182000000,10.20),
  ('XC600012','银河证券','券商',16.80,16.60,168000000,15.30),
  ('XC600013','天合汽车','汽车',31.20,30.80,312000000,22.60),
  ('XC600014','星云电力','电力',8.90,8.85,89000000,14.50),
  ('XC600015','星际物流','物流',14.50,14.40,145000000,19.80),
  ('XC600016','量子计算','人工智能',85.20,83.50,852000000,120.00),
  ('XC600017','银河军工','军工',26.70,26.50,267000000,38.20),
  ('XC600018','太空农业','农业',9.80,9.75,98000000,16.30),
  ('XC600019','星际旅游','旅游',11.20,11.10,112000000,25.60),
  ('XC600020','元宇宙科技','元宇宙',45.80,44.90,458000000,95.00);

-- 成就种子
INSERT IGNORE INTO achievements (code,name,description,category,icon,reward_gold,reward_score) VALUES
  ('first_trade','初入商海','完成第一次市场交易','economy','chart-line',100,10),
  ('trade_100','交易达人','累计完成100笔交易','economy','chart-bar',500,50),
  ('rich_10k','小有积蓄','金币超过10000','economy','coins',1000,100),
  ('rich_100k','财大气粗','金币超过100000','economy','crown',5000,500),
  ('stock_master','股神','股票总盈亏超过50%','stock','trending-up',10000,1000),
  ('stock_loss','韭菜','股票总亏损超过30%','stock','trending-down',100,0),
  ('win_first','初战告捷','赢得第一次战斗','combat','sword',200,20),
  ('win_50','百战百胜','累计赢得50场战斗','combat','shield',2000,200),
  ('faction_leader','一呼百应','创建一个派系并拥有10名成员','social','users',3000,300),
  ('forum_star','论坛之星','帖子获赞超过100','social','star',500,50),
  ('philosopher','思想家','完成5种哲学研究','culture','book',5000,500),
  ('explorer','星际探索者','完成10次星际探索','culture','compass',3000,300),
  ('level_10','十级殖民地','殖民地升到10级','social','arrow-up',10000,1000),
  ('daily_7','坚持一周','连续7天完成每日任务','social','calendar',2000,200);

-- =============================================
-- V8 战争纪元 新增表
-- =============================================

CREATE TABLE IF NOT EXISTS raids (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS colony_shields (
    id INT AUTO_INCREMENT PRIMARY KEY, colony_id INT NOT NULL UNIQUE,
    shield_type VARCHAR(16) DEFAULT 'none', shield_until TIMESTAMP NULL,
    shield_charges INT DEFAULT 0, last_broken_at TIMESTAMP NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS colony_defenses (
    id INT AUTO_INCREMENT PRIMARY KEY, colony_id INT NOT NULL,
    defense_type VARCHAR(32) NOT NULL, level INT DEFAULT 1,
    hp INT DEFAULT 100, max_hp INT DEFAULT 100,
    slot INT NOT NULL, is_active TINYINT(1) DEFAULT 1,
    UNIQUE KEY uk_defense_slot (colony_id, slot)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS colony_defense_formation (
    colony_id INT NOT NULL PRIMARY KEY, formation VARCHAR(16) DEFAULT 'fortress'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS battle_reports (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS faction_wars (
    id INT AUTO_INCREMENT PRIMARY KEY,
    attacker_faction INT NOT NULL, defender_faction INT NOT NULL,
    war_type VARCHAR(16) DEFAULT 'declaration',
    status VARCHAR(16) DEFAULT 'active',
    attacker_score INT DEFAULT 0, defender_score INT DEFAULT 0,
    territory_id INT, started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP NULL, INDEX idx_war_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS bounties (
    id INT AUTO_INCREMENT PRIMARY KEY,
    target_id INT NOT NULL, placer_id INT NOT NULL,
    amount INT NOT NULL, reason VARCHAR(256),
    status VARCHAR(16) DEFAULT 'active',
    claimed_by INT, claimed_at TIMESTAMP NULL,
    escalation INT DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NULL,
    INDEX idx_bounty_target (target_id, status),
    INDEX idx_bounty_active (status, created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS arena_tournaments (
    id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(64) NOT NULL,
    tournament_type VARCHAR(16) DEFAULT 'daily',
    tier VARCHAR(16) DEFAULT 'open', max_participants INT DEFAULT 32,
    entry_fee INT DEFAULT 100, prize_pool INT DEFAULT 1000,
    status VARCHAR(16) DEFAULT 'upcoming',
    started_at TIMESTAMP NULL, completed_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS arena_participants (
    id INT AUTO_INCREMENT PRIMARY KEY, tournament_id INT NOT NULL,
    colony_id INT NOT NULL, bracket_pos INT DEFAULT 0,
    wins INT DEFAULT 0, losses INT DEFAULT 0,
    is_eliminated TINYINT(1) DEFAULT 0, final_rank INT,
    UNIQUE KEY uk_tournament_colony (tournament_id, colony_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS arena_matches (
    id INT AUTO_INCREMENT PRIMARY KEY, tournament_id INT NOT NULL,
    round_num INT NOT NULL, colony_a INT NOT NULL, colony_b INT NOT NULL,
    winner_id INT, result_json TEXT, fought_at TIMESTAMP NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS espionage_ops (
    id INT AUTO_INCREMENT PRIMARY KEY, spy_id INT NOT NULL,
    target_id INT NOT NULL, op_type VARCHAR(16) NOT NULL,
    success_rate FLOAT DEFAULT 0.5, result VARCHAR(16),
    intel_json TEXT, damage_json TEXT, cost_gold INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_espionage_spy (spy_id, created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- V8 成就种子
INSERT IGNORE INTO achievements (code,name,description,category,icon,reward_gold,reward_score) VALUES
  ('raider_1','初次掠夺','成功完成1次袭击','combat','crossed-swords',200,100),
  ('raider_50','战争之王','累计赢得50次袭击','combat','crossed-swords',3000,300),
  ('revenge_master','复仇者','成功复仇5次','combat','crossed-swords',1000,200),
  ('arena_champion','竞技场冠军','赢得1次锦标赛','combat','trophy',5000,500),
  ('bounty_hunter','赏金猎人','领取3次赏金','combat','target',2000,200),
  ('spy_master','暗影大师','成功10次间谍行动','combat','eye',2000,200);
