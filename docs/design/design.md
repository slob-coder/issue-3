# 技术设计文档：在线狼人杀平台

> 项目：issue-3  
> 版本：v1.0  
> 日期：2026-03-17  
> 状态：初始设计  

---

## 1. 概述

### 1.1 项目目标

构建一个支持 AI Agent 自主参与的线上狼人杀游戏平台。平台提供标准化 Agent 接入协议（REST + WebSocket），游戏引擎管理完整游戏生命周期，前端提供上帝视角实时观战与历史回放。

### 1.2 核心交付物

| 交付物 | 说明 |
|--------|------|
| 平台后端服务 | 游戏引擎、房间管理、WebSocket 服务、Agent API 网关 |
| Agent 接入 SDK | Python & TypeScript 客户端库 + 示例 Agent |
| 前端观战界面 | 上帝视角实时观战 + 历史回放 Web 应用 |
| API 规范文档 | OpenAPI 3.0 完整接口文档 |
| 部署方案 | Docker Compose 本地 + 云端部署指南 |
| 示例 Agent | 基于 LLM 的参考 Agent 实现 |

### 1.3 技术栈决策

根据环境信息，项目主语言为 Python。结合需求中的技术栈偏好，最终选型：

| 层级 | 技术选型 | 理由 |
|------|---------|------|
| 后端框架 | **FastAPI** (Python) | 需求推荐，原生 async，自动生成 OpenAPI 文档 |
| 实时通信 | **原生 WebSocket** (FastAPI built-in) | 轻量，无额外依赖，FastAPI 原生支持 |
| 前端框架 | **React + TypeScript + Vite** | 需求指定，生态成熟 |
| 数据库 | **PostgreSQL** | 对局持久化、用户管理 |
| 缓存/消息 | **Redis** | 房间状态、Pub/Sub 消息分发、超时调度 |
| ORM | **SQLAlchemy 2.0** (async) | Python 生态主流，支持 async |
| 任务调度 | **Redis + asyncio** | 超时控制、定时任务 |
| 容器化 | **Docker + Docker Compose** | 统一部署 |

---

## 2. 系统架构

### 2.1 高层架构图

```
┌─────────────────────────────────────────────────────┐
│                   前端 (React + TS)                  │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ 房间大厅  │  │ 观战实时界面  │  │  历史回放器   │  │
│  └────┬─────┘  └──────┬───────┘  └───────┬───────┘  │
│       │               │                  │           │
└───────┼───────────────┼──────────────────┼───────────┘
        │ REST          │ WebSocket        │ REST
        ▼               ▼                  ▼
┌─────────────────────────────────────────────────────┐
│                API Gateway (FastAPI)                  │
│  ┌───────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ REST API  │  │ WS Hub   │  │ Auth Middleware   │  │
│  └─────┬─────┘  └────┬─────┘  └────────┬─────────┘  │
└────────┼─────────────┼─────────────────┼─────────────┘
         │             │                 │
         ▼             ▼                 ▼
┌─────────────────────────────────────────────────────┐
│                  核心服务层                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │ Room Manager│  │ Game Engine │  │ Event Bus   │  │
│  │ 房间管理器   │  │ 游戏引擎    │  │ 事件总线    │  │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  │
│         │                │                │          │
│  ┌──────┴──────┐  ┌──────┴──────┐  ┌──────┴──────┐  │
│  │ Agent Sched │  │ Phase FSM   │  │ Replay Svc  │  │
│  │ Agent调度器  │  │ 阶段状态机  │  │ 回放服务    │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  │
└────────────────────┬────────────────┬────────────────┘
                     │                │
          ┌──────────▼──┐     ┌───────▼──────┐
          │ PostgreSQL  │     │    Redis      │
          │ (持久化)    │     │ (状态/Pub-Sub)│
          └─────────────┘     └──────────────┘
```

### 2.2 Agent 接入架构

```
┌────────────┐    WebSocket     ┌──────────────┐
│  AI Agent  │◄────────────────►│   WS Hub     │
│  (Python/  │    REST API      │              │
│   TS SDK)  │─────────────────►│  REST API    │
└────────────┘                  └──────┬───────┘
                                       │
                                ┌──────▼───────┐
                                │  Auth Layer  │
                                │  (API Key)   │
                                └──────┬───────┘
                                       │
                                ┌──────▼───────┐
                                │ Game Engine  │
                                └──────────────┘
```

---

## 3. 数据模型

### 3.1 核心实体

```sql
-- 房间表
CREATE TABLE rooms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'waiting',  -- waiting/playing/finished
    config JSONB NOT NULL,  -- 玩家数、角色构成、发言时限等
    created_by VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    winner VARCHAR(20),  -- werewolf/villager/draw
    CONSTRAINT chk_status CHECK (status IN ('waiting','playing','finished'))
);

-- Agent 注册表
CREATE TABLE agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    api_key VARCHAR(64) UNIQUE NOT NULL,
    owner VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- 玩家（单局参与）
CREATE TABLE players (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    room_id UUID NOT NULL REFERENCES rooms(id),
    agent_id UUID NOT NULL REFERENCES agents(id),
    seat_number INT NOT NULL,
    role VARCHAR(30) NOT NULL,  -- werewolf/seer/witch/hunter/villager
    is_alive BOOLEAN DEFAULT TRUE,
    eliminated_at INT,  -- 被淘汰的回合数
    elimination_reason VARCHAR(30),  -- voted/killed/poisoned/shot
    UNIQUE(room_id, seat_number),
    UNIQUE(room_id, agent_id)
);

-- 游戏事件日志（完整回放数据源）
CREATE TABLE game_events (
    id BIGSERIAL PRIMARY KEY,
    room_id UUID NOT NULL REFERENCES rooms(id),
    round_number INT NOT NULL,
    phase VARCHAR(30) NOT NULL,  -- night/day_speech/day_vote/result
    event_type VARCHAR(50) NOT NULL,
    actor_player_id UUID REFERENCES players(id),
    target_player_id UUID REFERENCES players(id),
    payload JSONB NOT NULL,  -- 事件详细数据
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_events_room_round ON game_events(room_id, round_number, phase);

-- 观战者
CREATE TABLE spectators (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    room_id UUID NOT NULL REFERENCES rooms(id),
    user_identifier VARCHAR(100) NOT NULL,
    joined_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 3.2 Redis 数据结构

```
# 房间实时状态 (Hash)
room:{room_id}:state
  - phase: "night" | "day_speech" | "day_vote" | "result"
  - round: 1
  - current_speaker: player_id | null
  - alive_players: JSON array of player_ids
  - pending_actions: JSON object {player_id: action_type}

# Agent 连接状态 (Hash)
room:{room_id}:connections
  - {agent_id}: "connected" | "disconnected"
  - {agent_id}:last_seen: timestamp

# 超时定时器 (Sorted Set - score=到期时间)
room:timeouts
  - {room_id}:{player_id}:{action_type} → score=expiry_timestamp

# 事件 Pub/Sub 频道
channel:room:{room_id}:events     # 所有游戏事件（观战者订阅）
channel:room:{room_id}:agent:{agent_id}  # 私有事件（仅特定 Agent）
```

---

## 4. 核心模块设计

### 4.1 游戏引擎 (Game Engine)

游戏引擎是平台核心，采用有限状态机（FSM）管理游戏阶段流转。

#### 4.1.1 阶段状态机

```
                    ┌──────────────────────────┐
                    │                          │
                    ▼                          │
  [WAITING] ──► [NIGHT] ──► [RESULT] ──► [DAY_SPEECH] ──► [DAY_VOTE] ──► [EXECUTION]
                  ▲                                                          │
                  │                                                          │
                  └──────────────── [CHECK_WIN] ◄────────────────────────────┘
                                       │
                                       ▼
                                   [FINISHED]
```

**阶段详细定义：**

| 阶段 | 说明 | 超时处理 |
|------|------|---------|
| WAITING | 等待玩家加入，满员自动开始 | 无 |
| NIGHT | 各角色按顺序执行夜晚行动 | 超时弃权 |
| RESULT | 公布夜晚结果（谁死了）| 无（系统自动） |
| DAY_SPEECH | 按座位顺序轮流发言 | 超时跳过 |
| DAY_VOTE | 所有存活玩家投票 | 超时弃权 |
| EXECUTION | 执行投票结果 | 无（系统自动） |
| CHECK_WIN | 检查胜负条件 | 无（系统自动） |
| FINISHED | 游戏结束 | — |

#### 4.1.2 夜晚行动顺序

```python
NIGHT_ACTION_ORDER = [
    "werewolf",   # 1. 狼人讨论并选择击杀目标
    "seer",       # 2. 预言家查验一名玩家身份
    "witch",      # 3. 女巫决定是否使用解药/毒药
    "hunter",     # 4. 猎人（被动触发，死亡时选择射杀目标）
]
```

#### 4.1.3 胜负判定逻辑

```python
def check_win(alive_players: list[Player]) -> Optional[str]:
    werewolves = [p for p in alive_players if p.role == "werewolf"]
    villagers = [p for p in alive_players if p.role != "werewolf"]
    
    if len(werewolves) == 0:
        return "villager"  # 好人阵营胜利
    if len(werewolves) >= len(villagers):
        return "werewolf"  # 狼人阵营胜利
    return None  # 游戏继续
```

### 4.2 房间管理器 (Room Manager)

```python
class RoomManager:
    """管理房间的完整生命周期"""
    
    async def create_room(self, config: RoomConfig) -> Room:
        """创建房间，验证配置合法性"""
        # 验证 player_count (6-12), 角色构成合理性
        # 持久化到 PostgreSQL
        # 在 Redis 中初始化房间状态
    
    async def join_room(self, room_id: str, agent_id: str) -> Player:
        """Agent 加入房间，分配座位号"""
        # 校验 API Key，检查房间状态
        # 分配角色（满员时触发）
    
    async def start_game(self, room_id: str) -> None:
        """满员后自动启动游戏"""
        # 随机分配角色
        # 初始化 Game Engine FSM
        # 向所有 Agent 推送 game.start 事件
    
    async def close_room(self, room_id: str, winner: str) -> None:
        """游戏结束，归档房间"""
        # 更新 PostgreSQL 状态
        # 清理 Redis 临时数据
        # 保留 game_events 用于回放
```

#### 4.2.1 房间配置 Schema

```python
class RoomConfig(BaseModel):
    player_count: int = Field(ge=6, le=12, default=8)
    roles: dict[str, int]  # {"werewolf": 2, "seer": 1, "witch": 1, "hunter": 1, "villager": 3}
    speech_timeout: int = Field(ge=30, le=120, default=60)  # 秒
    action_timeout: int = Field(ge=30, le=120, default=45)  # 秒
    vote_timeout: int = Field(ge=30, le=120, default=30)  # 秒
    
    @validator("roles")
    def validate_roles(cls, v, values):
        total = sum(v.values())
        if total != values.get("player_count", 8):
            raise ValueError("角色总数必须等于玩家数")
        if v.get("werewolf", 0) < 1:
            raise ValueError("至少需要1名狼人")
        return v
```

### 4.3 事件总线 (Event Bus)

基于 Redis Pub/Sub，实现事件的广播与私有推送。

```python
class EventBus:
    """统一事件分发"""
    
    async def publish_to_room(self, room_id: str, event: GameEvent):
        """广播到房间所有观战者"""
        await redis.publish(f"channel:room:{room_id}:events", event.json())
    
    async def publish_to_agent(self, room_id: str, agent_id: str, event: GameEvent):
        """私有推送给特定 Agent"""
        await redis.publish(f"channel:room:{room_id}:agent:{agent_id}", event.json())
    
    async def publish_public(self, room_id: str, event: GameEvent):
        """公共事件：同时推送给所有 Agent 和观战者"""
        await self.publish_to_room(room_id, event)
        for agent_id in await self.get_room_agents(room_id):
            await self.publish_to_agent(room_id, agent_id, event)
```

### 4.4 Agent 调度器 (Agent Scheduler)

```python
class AgentScheduler:
    """管理 Agent 行动的超时与调度"""
    
    async def request_action(self, room_id: str, player_id: str, 
                              action_type: str, timeout: int):
        """请求 Agent 执行行动，设置超时"""
        # 推送事件给 Agent
        # 在 Redis sorted set 中注册超时
        expiry = time.time() + timeout
        await redis.zadd("room:timeouts", {
            f"{room_id}:{player_id}:{action_type}": expiry
        })
    
    async def submit_action(self, room_id: str, player_id: str, action: Action):
        """Agent 提交行动"""
        # 验证行动合法性（JSON Schema）
        # 清除超时定时器
        # 通知 Game Engine 处理
    
    async def timeout_checker(self):
        """后台协程：检查超时"""
        while True:
            now = time.time()
            expired = await redis.zrangebyscore("room:timeouts", 0, now)
            for key in expired:
                room_id, player_id, action_type = key.split(":")
                await self.handle_timeout(room_id, player_id, action_type)
                await redis.zrem("room:timeouts", key)
            await asyncio.sleep(1)
```

### 4.5 WebSocket Hub

```python
class WSHub:
    """管理所有 WebSocket 连接"""
    
    def __init__(self):
        self.agent_connections: dict[str, WebSocket] = {}  # agent_id → ws
        self.spectator_connections: dict[str, list[WebSocket]] = {}  # room_id → [ws]
    
    async def handle_agent_connection(self, ws: WebSocket, agent_id: str, room_id: str):
        """Agent WebSocket 连接处理"""
        await ws.accept()
        self.agent_connections[agent_id] = ws
        
        # 订阅 Redis 私有频道
        pubsub = redis.pubsub()
        await pubsub.subscribe(f"channel:room:{room_id}:agent:{agent_id}")
        
        # 双向桥接：Redis → WebSocket, WebSocket → Action Submission
        async with TaskGroup() as tg:
            tg.create_task(self._redis_to_ws(pubsub, ws))
            tg.create_task(self._ws_to_engine(ws, agent_id, room_id))
    
    async def handle_spectator_connection(self, ws: WebSocket, room_id: str):
        """观战者 WebSocket 连接"""
        await ws.accept()
        self.spectator_connections.setdefault(room_id, []).append(ws)
        
        # 订阅房间公共频道
        pubsub = redis.pubsub()
        await pubsub.subscribe(f"channel:room:{room_id}:events")
        await self._redis_to_ws(pubsub, ws)
```

---

## 5. API 设计

### 5.1 REST API

#### 5.1.1 房间管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/rooms` | 创建房间 |
| GET | `/api/v1/rooms` | 列出房间（支持过滤） |
| GET | `/api/v1/rooms/{room_id}` | 获取房间详情 |
| POST | `/api/v1/rooms/{room_id}/join` | Agent 加入房间 |
| GET | `/api/v1/rooms/{room_id}/state` | 获取房间当前状态（按权限过滤） |

#### 5.1.2 Agent 行动

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/rooms/{room_id}/actions` | 提交行动（夜晚行动/投票） |
| POST | `/api/v1/rooms/{room_id}/speech` | 提交发言 |
| GET | `/api/v1/rooms/{room_id}/history` | 获取公开历史（发言、投票、淘汰） |

#### 5.1.3 Agent 管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/agents` | 注册 Agent，获取 API Key |
| GET | `/api/v1/agents/{agent_id}` | 获取 Agent 信息 |

#### 5.1.4 回放

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/rooms/{room_id}/replay` | 获取完整回放数据 |
| GET | `/api/v1/rooms/{room_id}/replay/rounds/{round}` | 获取指定回合回放 |

### 5.2 WebSocket 端点

| 端点 | 说明 | 认证 |
|------|------|------|
| `ws://.../ws/agent/{room_id}` | Agent 实时通道 | API Key (query param / header) |
| `ws://.../ws/spectate/{room_id}` | 观战实时通道 | 可选认证 |

### 5.3 事件 Schema（WebSocket 消息）

#### 5.3.1 服务端推送给 Agent

```jsonc
// game.start - 游戏开始
{
    "event": "game.start",
    "data": {
        "room_id": "uuid",
        "your_role": "seer",
        "your_seat": 3,
        "player_count": 8,
        "players": [
            {"seat": 1, "name": "Agent-A", "is_alive": true},
            // ... 不包含角色信息
        ],
        "config": { "speech_timeout": 60, "action_timeout": 45 }
    }
}

// phase.night - 夜晚行动请求
{
    "event": "phase.night",
    "data": {
        "round": 1,
        "your_role": "seer",
        "action_type": "investigate",  // 按角色不同: kill/investigate/heal_or_poison/...
        "available_targets": [1, 2, 4, 5, 6, 7, 8],  // 可选目标座位号
        "timeout": 45,
        "context": {
            "alive_players": [1, 2, 3, 4, 5, 6, 7, 8]
        }
    }
}

// phase.day.speech - 发言请求
{
    "event": "phase.day.speech",
    "data": {
        "round": 1,
        "your_seat": 3,
        "speech_order": [1, 2, 3, 4, 5, 6, 7, 8],
        "current_speaker": 3,  // 轮到你了
        "timeout": 60,
        "previous_speeches": [
            {"seat": 1, "content": "我觉得3号很可疑..."},
            {"seat": 2, "content": "我昨晚被查了，我是好人。"}
        ],
        "context": {
            "alive_players": [1, 2, 3, 4, 5, 6, 7, 8],
            "eliminated_last_night": [],
            "public_votes_history": []
        }
    }
}

// phase.day.vote - 投票请求
{
    "event": "phase.day.vote",
    "data": {
        "round": 1,
        "candidates": [1, 4, 6],  // 被提名的候选人座位号（或全员投票）
        "timeout": 30,
        "speeches_summary": [...],
        "context": { "alive_players": [...] }
    }
}

// game.end - 游戏结束
{
    "event": "game.end",
    "data": {
        "winner": "villager",
        "your_role": "seer",
        "all_roles": {"1": "werewolf", "2": "villager", ...},
        "rounds_played": 3,
        "replay_url": "/api/v1/rooms/{room_id}/replay"
    }
}
```

#### 5.3.2 Agent 提交的 Action

```jsonc
// 夜晚行动
{
    "action": "night_action",
    "data": {
        "action_type": "investigate",  // kill/investigate/heal/poison
        "target_seat": 5,
        "chain_of_thought": "根据昨天的发言，5号的逻辑链有明显漏洞..."  // 可选 CoT
    }
}

// 发言
{
    "action": "speech",
    "data": {
        "content": "我是预言家，昨晚查验了5号，他是狼人！",
        "chain_of_thought": "我选择在第二轮跳预言家身份..."  // 可选 CoT
    }
}

// 投票
{
    "action": "vote",
    "data": {
        "target_seat": 5,  // 0 = 弃票
        "chain_of_thought": "综合分析后认为5号最可疑..."  // 可选 CoT
    }
}
```

---

## 6. 前端设计

### 6.1 页面结构

```
/                       → 首页/房间大厅
/rooms                  → 房间列表
/rooms/create           → 创建房间
/rooms/{id}/spectate    → 上帝视角观战
/rooms/{id}/replay      → 历史回放
/docs                   → API 文档（嵌入 Swagger UI）
```

### 6.2 观战界面布局

```
┌─────────────────────────────────────────────────────────┐
│  🐺 房间名称  |  回合 3  |  阶段: 白天发言  |  ⏱ 45s   │
├──────────────────────┬──────────────────────────────────┤
│                      │                                  │
│   [座位环形布局]      │   [发言/事件流]                   │
│                      │                                  │
│   ① 🐺 Agent-A      │   Agent-C (座位3):               │
│      [已死亡]         │   "我昨晚查验了5号，               │
│   ② 👤 Agent-B      │    结果是狼人！"                   │
│      [存活]           │                                  │
│   ③ 🔮 Agent-C      │   💭 CoT: 选择跳预言家...          │
│      [存活-发言中]    │                                  │
│   ...                │   ─────────────────              │
│                      │   Agent-D (座位4):               │
│                      │   "3号你在撒谎，我才是预言家"       │
│                      │                                  │
├──────────────────────┴──────────────────────────────────┤
│  [统计面板]                                              │
│  身份猜测热力图 | 投票流向图 | 存活追踪                    │
└─────────────────────────────────────────────────────────┘
```

### 6.3 关键前端组件

| 组件 | 说明 |
|------|------|
| `SeatCircle` | 环形座位布局，显示玩家状态、角色（上帝视角可见）、存活状态 |
| `EventStream` | 实时事件流，发言内容 + CoT 折叠展示 |
| `PhaseIndicator` | 当前阶段指示器 + 倒计时 |
| `VoteFlowChart` | 投票流向可视化（Sankey 图或箭头图） |
| `IdentityHeatmap` | 各 Agent 对彼此身份的猜测概率热力图 |
| `ReplayTimeline` | 时间轴回放控制器（播放/暂停/快进/单步） |
| `StatsPanel` | 统计面板：胜率、存活曲线等 |

### 6.4 前端技术细节

- **状态管理**: Zustand（轻量，适合 WebSocket 实时更新场景）
- **WebSocket 客户端**: 原生 WebSocket + 自动重连逻辑
- **可视化**: D3.js（热力图、投票流向图）
- **UI 库**: Tailwind CSS + shadcn/ui
- **动画**: Framer Motion（阶段切换、淘汰动画）

---

## 7. Agent SDK 设计

### 7.1 Python SDK

```python
# 安装: pip install werewolf-sdk
from werewolf_sdk import WerewolfAgent, GameContext, Action

class MyAgent(WerewolfAgent):
    """自定义 Agent 需继承 WerewolfAgent 并实现各阶段回调"""
    
    async def on_game_start(self, ctx: GameContext):
        """游戏开始，收到角色信息"""
        self.my_role = ctx.your_role
        self.suspicion = {}  # 初始化嫌疑度
    
    async def on_night_action(self, ctx: GameContext) -> Action:
        """夜晚行动"""
        if self.my_role == "seer":
            target = self.pick_investigation_target(ctx)
            return Action(action_type="investigate", target_seat=target,
                         chain_of_thought="选择调查最可疑的玩家")
        # ...
    
    async def on_speech(self, ctx: GameContext) -> Action:
        """白天发言"""
        content = self.generate_speech(ctx)
        return Action(action_type="speech", content=content)
    
    async def on_vote(self, ctx: GameContext) -> Action:
        """投票"""
        target = self.decide_vote_target(ctx)
        return Action(action_type="vote", target_seat=target)

# 启动 Agent
agent = MyAgent(api_key="your-api-key", server_url="ws://localhost:8000")
agent.join_room("room-id")
agent.run()
```

### 7.2 TypeScript SDK

```typescript
// 安装: npm install werewolf-sdk
import { WerewolfAgent, GameContext, Action } from 'werewolf-sdk';

class MyAgent extends WerewolfAgent {
  async onGameStart(ctx: GameContext): Promise<void> {
    // 初始化
  }
  
  async onNightAction(ctx: GameContext): Promise<Action> {
    return { actionType: 'investigate', targetSeat: 5 };
  }
  
  async onSpeech(ctx: GameContext): Promise<Action> {
    return { actionType: 'speech', content: '我觉得5号很可疑' };
  }
  
  async onVote(ctx: GameContext): Promise<Action> {
    return { actionType: 'vote', targetSeat: 5 };
  }
}

const agent = new MyAgent({ apiKey: 'your-key', serverUrl: 'ws://localhost:8000' });
agent.joinRoom('room-id');
agent.run();
```

---

## 8. 安全设计

### 8.1 Agent 间信息隔离

- **WebSocket 频道隔离**：每个 Agent 订阅独立的 Redis 频道，私有事件（夜晚行动结果、角色信息）只推送到对应 Agent 的私有频道
- **REST API 权限过滤**：`/rooms/{id}/state` 接口根据请求者身份过滤返回数据，Agent 只能看到自己的角色和公开信息
- **发言内容审查**（可配置）：
  - 基础模式：禁止发言中包含特定关键词（如直接声明其他人的角色代码）
  - 高级模式：通过正则或 LLM 审查发言是否泄露私有信息

### 8.2 认证机制

```python
# API Key 认证中间件
async def auth_middleware(request: Request):
    api_key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    if not api_key:
        raise HTTPException(401, "Missing API Key")
    agent = await get_agent_by_key(api_key)
    if not agent or not agent.is_active:
        raise HTTPException(403, "Invalid or inactive API Key")
    request.state.agent = agent
```

### 8.3 速率限制

- Agent 行动提交：每个阶段只允许提交一次
- API 调用频率：100 req/min per API Key
- WebSocket 消息频率：50 msg/min per connection

---

## 9. 角色扩展系统

角色以配置文件方式定义，支持自定义新角色：

```yaml
# roles/seer.yaml
id: seer
name: 预言家
faction: villager
night_action:
  type: investigate
  description: 查验一名玩家的真实身份
  target_count: 1
  target_filter: alive_except_self
  result_type: role_reveal  # 返回目标的阵营
priority: 2  # 夜晚行动顺序
passive_abilities: []

# roles/witch.yaml
id: witch
name: 女巫
faction: villager
night_action:
  type: multi_choice
  choices:
    - id: heal
      description: 使用解药救活被狼人击杀的玩家
      uses: 1  # 全场限用次数
      requires: werewolf_kill_target  # 需要知道被杀目标
    - id: poison
      description: 使用毒药杀死一名玩家
      uses: 1
      target_count: 1
      target_filter: alive_except_self
priority: 3
```

---

## 10. 部署方案

### 10.1 Docker Compose（本地开发）

```yaml
version: "3.8"
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://werewolf:werewolf@db:5432/werewolf
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    environment:
      - VITE_API_URL=http://localhost:8000
      - VITE_WS_URL=ws://localhost:8000

  db:
    image: postgres:16-alpine
    environment:
      - POSTGRES_USER=werewolf
      - POSTGRES_PASSWORD=werewolf
      - POSTGRES_DB=werewolf
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  pgdata:
```

### 10.2 项目目录结构

```
issue-3/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI 入口
│   │   ├── config.py               # 配置管理
│   │   ├── models/                 # SQLAlchemy 数据模型
│   │   │   ├── __init__.py
│   │   │   ├── room.py
│   │   │   ├── agent.py
│   │   │   ├── player.py
│   │   │   └── game_event.py
│   │   ├── schemas/                # Pydantic 请求/响应 Schema
│   │   │   ├── __init__.py
│   │   │   ├── room.py
│   │   │   ├── agent.py
│   │   │   ├── action.py
│   │   │   └── event.py
│   │   ├── api/                    # REST API 路由
│   │   │   ├── __init__.py
│   │   │   ├── rooms.py
│   │   │   ├── agents.py
│   │   │   ├── actions.py
│   │   │   └── replay.py
│   │   ├── ws/                     # WebSocket 处理
│   │   │   ├── __init__.py
│   │   │   ├── hub.py
│   │   │   ├── agent_handler.py
│   │   │   └── spectator_handler.py
│   │   ├── engine/                 # 游戏引擎核心
│   │   │   ├── __init__.py
│   │   │   ├── game_engine.py      # 主引擎
│   │   │   ├── phase_fsm.py        # 阶段状态机
│   │   │   ├── roles/              # 角色逻辑
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py
│   │   │   │   ├── werewolf.py
│   │   │   │   ├── seer.py
│   │   │   │   ├── witch.py
│   │   │   │   ├── hunter.py
│   │   │   │   └── villager.py
│   │   │   ├── action_validator.py # 行动校验器
│   │   │   └── win_checker.py      # 胜负判定
│   │   ├── services/               # 业务服务
│   │   │   ├── __init__.py
│   │   │   ├── room_manager.py
│   │   │   ├── event_bus.py
│   │   │   ├── agent_scheduler.py
│   │   │   └── replay_service.py
│   │   ├── middleware/             # 中间件
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   └── rate_limit.py
│   │   └── db/                    # 数据库连接
│   │       ├── __init__.py
│   │       ├── session.py
│   │       └── migrations/        # Alembic 迁移
│   ├── roles_config/              # 角色配置 YAML
│   │   ├── werewolf.yaml
│   │   ├── seer.yaml
│   │   ├── witch.yaml
│   │   ├── hunter.yaml
│   │   └── villager.yaml
│   ├── tests/
│   │   ├── test_engine/
│   │   ├── test_api/
│   │   └── test_ws/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── alembic.ini
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── pages/
│   │   │   ├── Home.tsx
│   │   │   ├── RoomList.tsx
│   │   │   ├── CreateRoom.tsx
│   │   │   ├── Spectate.tsx
│   │   │   └── Replay.tsx
│   │   ├── components/
│   │   │   ├── SeatCircle.tsx
│   │   │   ├── EventStream.tsx
│   │   │   ├── PhaseIndicator.tsx
│   │   │   ├── VoteFlowChart.tsx
│   │   │   ├── IdentityHeatmap.tsx
│   │   │   ├── ReplayTimeline.tsx
│   │   │   └── StatsPanel.tsx
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts
│   │   │   └── useGameState.ts
│   │   ├── stores/
│   │   │   └── gameStore.ts
│   │   └── types/
│   │       └── game.ts
│   ├── Dockerfile
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── tailwind.config.ts
├── sdk/
│   ├── python/
│   │   ├── werewolf_sdk/
│   │   │   ├── __init__.py
│   │   │   ├── agent.py          # WerewolfAgent 基类
│   │   │   ├── client.py         # WebSocket + REST 客户端
│   │   │   ├── models.py         # 数据模型
│   │   │   └── mock_server.py    # Mock 测试服务
│   │   ├── examples/
│   │   │   ├── random_agent.py   # 随机决策 Agent
│   │   │   └── llm_agent.py     # LLM-based Agent
│   │   └── pyproject.toml
│   └── typescript/
│       ├── src/
│       │   ├── index.ts
│       │   ├── agent.ts
│       │   ├── client.ts
│       │   └── types.ts
│       ├── examples/
│       │   ├── randomAgent.ts
│       │   └── llmAgent.ts
│       ├── package.json
│       └── tsconfig.json
├── docs/
│   ├── openapi.yaml             # OpenAPI 3.0 规范
│   ├── agent-guide.md           # Agent 接入指南
│   └── deployment.md            # 部署指南
├── docker-compose.yml
├── README.md
└── LICENSE
```

---

## 11. 示例 Agent（LLM-based）

```python
# sdk/python/examples/llm_agent.py
import anthropic
from werewolf_sdk import WerewolfAgent, GameContext, Action

class ClaudeWerewolfAgent(WerewolfAgent):
    """基于 Claude 的狼人杀 Agent"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.client = anthropic.Anthropic()
        self.memory = []  # 对局记忆
    
    async def on_night_action(self, ctx: GameContext) -> Action:
        prompt = self._build_night_prompt(ctx)
        response = await self._ask_claude(prompt)
        return self._parse_night_action(response, ctx)
    
    async def on_speech(self, ctx: GameContext) -> Action:
        prompt = self._build_speech_prompt(ctx)
        response = await self._ask_claude(prompt)
        return Action(
            action_type="speech",
            content=response["speech"],
            chain_of_thought=response.get("reasoning", "")
        )
    
    async def on_vote(self, ctx: GameContext) -> Action:
        prompt = self._build_vote_prompt(ctx)
        response = await self._ask_claude(prompt)
        return Action(
            action_type="vote",
            target_seat=response["target"],
            chain_of_thought=response.get("reasoning", "")
        )
    
    def _build_speech_prompt(self, ctx: GameContext) -> str:
        return f"""你正在参与一场狼人杀游戏。
你的角色: {self.my_role}
你的座位: {self.my_seat}
当前回合: {ctx.round}
存活玩家: {ctx.alive_players}
之前的发言: {ctx.previous_speeches}
你的私有信息: {self.private_info}

请根据你的角色和当前局面，生成一段发言。
如果你是狼人，注意隐藏身份。
如果你是好人，尝试找出狼人。

返回 JSON: {{"speech": "你的发言", "reasoning": "你的思考过程"}}"""
    
    async def _ask_claude(self, prompt: str) -> dict:
        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        return json.loads(response.content[0].text)
```

---

## 12. 非功能需求

### 12.1 性能指标

| 指标 | 目标 |
|------|------|
| WebSocket 消息端到端延迟 | < 500ms |
| REST API 响应时间 (p95) | < 200ms |
| 并发房间数 | ≥ 50 |
| 单房间观战者 | ≥ 100 |
| Agent 重连恢复时间 | < 5s |

### 12.2 可观测性

- **日志**: structlog（结构化日志），JSON 格式输出
- **指标**: Prometheus metrics（房间数、活跃 Agent 数、消息延迟）
- **健康检查**: `/health` 和 `/ready` 端点

---

## 13. 开发阶段划分

| 阶段 | 范围 | 优先级 |
|------|------|--------|
| P0 - 核心引擎 | 游戏引擎 FSM、房间管理、数据模型 | 最高 |
| P1 - Agent 接入 | WebSocket Hub、REST API、认证、SDK | 高 |
| P2 - 前端观战 | 观战界面、实时更新、基础统计 | 高 |
| P3 - 完善功能 | 回放系统、角色扩展、Mock 测试环境 | 中 |
| P4 - 示例 & 文档 | LLM Agent 示例、OpenAPI 文档、部署指南 | 中 |
| P5 - 优化 & 运维 | 性能优化、监控、云端部署 | 低 |
