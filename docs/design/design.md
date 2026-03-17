# 技术设计文档：在线狼人杀平台

> 项目：issue-3  
> 版本：v3.0  
> 日期：2026-03-18  
> 状态：细化设计（完整版）  

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
| 部署方案 | Docker Compose 本地部署 + 云端部署指南 |
| 示例 Agent | 基于 LLM 的参考 Agent 实现 |

### 1.3 技术栈

| 层级 | 技术选型 | 理由 |
|------|---------|------|
| 后端框架 | **FastAPI** (Python 3.12+) | 需求推荐，原生 async，自动生成 OpenAPI 文档 |
| 实时通信 | **原生 WebSocket** (FastAPI built-in) | 轻量，无额外依赖 |
| 前端框架 | **React 18 + TypeScript 5 + Vite** | 需求指定，生态成熟 |
| 数据库 | **PostgreSQL 16** | 对局持久化 |
| 缓存/消息 | **Redis 7** | 房间状态、Pub/Sub、超时调度 |
| ORM | **SQLAlchemy 2.0** (async) | Python 主流，支持 asyncpg |
| 状态管理 | **Zustand** | 轻量，适合 WebSocket 场景 |
| UI | **Tailwind CSS + shadcn/ui** | 快速搭建，组件质量高 |
| 可视化 | **D3.js** | 热力图、投票流向图 |
| 容器化 | **Docker + Docker Compose** | 统一部署 |

---

## 2. 系统架构

### 2.1 高层架构

```
┌─────────────────────────────────────────────────────┐
│                   前端 (React + TS)                  │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ 房间大厅  │  │ 观战实时界面  │  │  历史回放器   │  │
│  └────┬─────┘  └──────┬───────┘  └───────┬───────┘  │
└───────┼───────────────┼──────────────────┼───────────┘
        │ REST          │ WebSocket        │ REST
        ▼               ▼                  ▼
┌─────────────────────────────────────────────────────┐
│                API Gateway (FastAPI)                  │
│  ┌───────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ REST API  │  │ WS Hub   │  │ Auth Middleware   │  │
│  └─────┬─────┘  └────┬─────┘  └────────┬─────────┘  │
└────────┼─────────────┼─────────────────┼─────────────┘
         ▼             ▼                 ▼
┌─────────────────────────────────────────────────────┐
│                  核心服务层                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │ Room Service│  │ Game Engine │  │ Event Bus   │  │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  │
│  ┌──────┴──────┐  ┌──────┴──────┐  ┌──────┴──────┐  │
│  │ Agent Sched │  │ Phase FSM   │  │ Replay Svc  │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  │
└────────────────────┬────────────────┬────────────────┘
          ┌──────────▼──┐     ┌───────▼──────┐
          │ PostgreSQL  │     │    Redis      │
          └─────────────┘     └──────────────┘
```

### 2.2 核心设计模式

#### 依赖注入 (DI)

所有服务通过 FastAPI 的 `Depends()` 注入。服务实例在 `app/dependencies.py` 集中管理。

```python
# app/dependencies.py
from functools import lru_cache

@lru_cache
def get_settings() -> Settings:
    return Settings()

async def get_db(settings: Settings = Depends(get_settings)) -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory(settings.database_url)() as session:
        yield session

async def get_redis(settings: Settings = Depends(get_settings)) -> Redis:
    return await aioredis.from_url(settings.redis_url)

async def get_event_bus(redis: Redis = Depends(get_redis)) -> EventBus:
    return EventBus(redis)

async def get_room_service(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    event_bus: EventBus = Depends(get_event_bus),
) -> RoomService:
    return RoomService(db, redis, event_bus)
```

#### 事件驱动架构 (EDA)

所有游戏状态变更通过 `GameEvent` 发布到 `EventBus`。消费者（WebSocket Hub、回放服务、统计服务）各自独立订阅。

```
GameEngine → EventBus → [WSHub → Agents/Spectators]
                      → [ReplayService → PostgreSQL]
                      → [StatsCollector → Redis]
```

#### 策略模式 (Strategy) - 角色行为

每个角色实现 `RoleStrategy` 接口，游戏引擎通过角色 ID 查找策略实例。新增角色只需添加策略类 + YAML 配置。

#### 状态模式 (State) - 游戏阶段

每个阶段实现 `PhaseHandler` 接口，FSM 将当前阶段委托给对应 handler 处理。阶段流转由 FSM 统一管控。

---

## 3. 项目目录结构

```
werewolf-arena/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI 入口，lifespan，路由注册
│   │   ├── config.py                  # Settings (pydantic-settings)
│   │   ├── dependencies.py            # 全局依赖注入
│   │   ├── exceptions.py              # 自定义异常 + 全局异常处理器
│   │   ├── db/
│   │   │   ├── __init__.py
│   │   │   ├── session.py             # async engine + session factory
│   │   │   ├── redis.py               # Redis 连接池
│   │   │   └── base.py                # SQLAlchemy Base
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── room.py
│   │   │   ├── agent.py
│   │   │   ├── player.py
│   │   │   └── game_event.py
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── room.py                # RoomCreate, RoomConfig, RoomResponse
│   │   │   ├── agent.py               # AgentCreate, AgentResponse
│   │   │   ├── action.py              # NightAction, SpeechAction, VoteAction, ActionSubmit
│   │   │   └── event.py               # GameEventSchema, WS message schemas
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── router.py              # 汇聚所有路由
│   │   │   ├── rooms.py               # /api/v1/rooms/*
│   │   │   ├── agents.py              # /api/v1/agents/*
│   │   │   ├── actions.py             # /api/v1/rooms/{id}/actions
│   │   │   └── replay.py              # /api/v1/rooms/{id}/replay
│   │   ├── ws/
│   │   │   ├── __init__.py
│   │   │   ├── hub.py                 # ConnectionManager
│   │   │   ├── agent_handler.py       # Agent WS 端点
│   │   │   └── spectator_handler.py   # 观战者 WS 端点
│   │   ├── middleware/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py                # API Key 认证
│   │   │   └── rate_limit.py          # 速率限制
│   │   ├── engine/
│   │   │   ├── __init__.py
│   │   │   ├── game_engine.py         # GameEngine 主控制器
│   │   │   ├── game_state.py          # GameState 数据类（内存+Redis同步）
│   │   │   ├── phase_fsm.py           # 阶段状态机
│   │   │   ├── win_checker.py         # 胜负判定
│   │   │   ├── action_validator.py    # 行动合法性校验
│   │   │   ├── phases/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py            # PhaseHandler ABC
│   │   │   │   ├── night.py           # NightPhaseHandler
│   │   │   │   ├── result.py          # ResultPhaseHandler
│   │   │   │   ├── day_speech.py      # DaySpeechPhaseHandler
│   │   │   │   ├── day_vote.py        # DayVotePhaseHandler
│   │   │   │   ├── execution.py       # ExecutionPhaseHandler
│   │   │   │   └── check_win.py       # CheckWinPhaseHandler
│   │   │   └── roles/
│   │   │       ├── __init__.py
│   │   │       ├── base.py            # RoleStrategy ABC
│   │   │       ├── registry.py        # RoleRegistry
│   │   │       ├── werewolf.py
│   │   │       ├── seer.py
│   │   │       ├── witch.py
│   │   │       ├── hunter.py
│   │   │       └── villager.py
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── room_service.py        # 房间 CRUD + 生命周期
│   │       ├── agent_service.py       # Agent 注册 + 管理
│   │       ├── agent_scheduler.py     # 超时 + 调度 + 连接追踪
│   │       ├── event_bus.py           # Redis Pub/Sub 封装
│   │       └── replay_service.py      # 回放数据生成
│   ├── roles_config/
│   │   ├── werewolf.yaml
│   │   ├── seer.yaml
│   │   ├── witch.yaml
│   │   ├── hunter.yaml
│   │   └── villager.yaml
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   ├── alembic.ini
│   ├── tests/
│   │   ├── conftest.py                # pytest fixtures (async db, redis mock)
│   │   ├── test_engine/
│   │   │   ├── test_phase_fsm.py
│   │   │   ├── test_roles.py
│   │   │   ├── test_win_checker.py
│   │   │   └── test_action_validator.py
│   │   ├── test_api/
│   │   │   ├── test_rooms.py
│   │   │   ├── test_agents.py
│   │   │   └── test_actions.py
│   │   ├── test_ws/
│   │   │   ├── test_agent_ws.py
│   │   │   └── test_spectator_ws.py
│   │   └── test_integration/
│   │       └── test_full_game.py      # 端到端完整游戏流程
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── vite-env.d.ts
│   │   ├── index.css
│   │   ├── pages/
│   │   │   ├── Home.tsx               # 首页 / 房间大厅
│   │   │   ├── CreateRoom.tsx         # 创建房间
│   │   │   ├── Spectate.tsx           # 观战主页面
│   │   │   └── Replay.tsx             # 回放页面
│   │   ├── components/
│   │   │   ├── ui/                    # shadcn/ui 组件
│   │   │   ├── layout/
│   │   │   │   ├── Header.tsx
│   │   │   │   └── Layout.tsx
│   │   │   ├── room/
│   │   │   │   ├── RoomCard.tsx
│   │   │   │   ├── RoomList.tsx
│   │   │   │   └── RoomConfigForm.tsx
│   │   │   ├── game/
│   │   │   │   ├── SeatCircle.tsx     # 环形座位布局
│   │   │   │   ├── PlayerCard.tsx     # 单个玩家卡片（角色、状态）
│   │   │   │   ├── PhaseIndicator.tsx # 阶段指示器 + 倒计时
│   │   │   │   ├── EventStream.tsx    # 发言/事件流
│   │   │   │   ├── CoTPanel.tsx       # Chain-of-Thought 面板
│   │   │   │   └── NightOverlay.tsx   # 夜晚阶段覆盖层动画
│   │   │   ├── stats/
│   │   │   │   ├── VoteFlowChart.tsx  # D3 投票流向图
│   │   │   │   ├── IdentityHeatmap.tsx# D3 身份猜测热力图
│   │   │   │   └── StatsPanel.tsx     # 统计汇总面板
│   │   │   └── replay/
│   │   │       ├── ReplayTimeline.tsx # 时间轴控制器
│   │   │       └── ReplayControls.tsx # 播放/暂停/快进
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts        # WebSocket 连接 hook
│   │   │   ├── useGameState.ts        # 游戏状态订阅 hook
│   │   │   └── useReplay.ts           # 回放控制 hook
│   │   ├── stores/
│   │   │   ├── gameStore.ts           # Zustand: 游戏状态
│   │   │   ├── roomStore.ts           # Zustand: 房间列表
│   │   │   └── replayStore.ts         # Zustand: 回放状态
│   │   ├── lib/
│   │   │   ├── api.ts                 # REST API 客户端 (fetch wrapper)
│   │   │   ├── ws.ts                  # WebSocket 客户端封装
│   │   │   └── utils.ts              # 工具函数
│   │   └── types/
│   │       └── game.ts                # 所有 TypeScript 类型定义
│   ├── public/
│   │   └── favicon.ico
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── postcss.config.js
│   ├── components.json               # shadcn/ui 配置
│   └── Dockerfile
├── sdk/
│   ├── python/
│   │   ├── werewolf_sdk/
│   │   │   ├── __init__.py
│   │   │   ├── agent.py               # WerewolfAgent 基类
│   │   │   ├── client.py              # HTTP + WS 客户端
│   │   │   ├── models.py              # 数据模型 (Pydantic)
│   │   │   └── mock_server.py         # 本地 Mock 测试服务器
│   │   ├── examples/
│   │   │   ├── random_agent.py        # 随机决策 Agent
│   │   │   └── llm_agent.py           # LLM 驱动 Agent (Claude/GPT)
│   │   ├── pyproject.toml
│   │   └── README.md
│   └── typescript/
│       ├── src/
│       │   ├── index.ts
│       │   ├── agent.ts               # WerewolfAgent 基类
│       │   ├── client.ts              # HTTP + WS 客户端
│       │   └── types.ts               # TypeScript 类型
│       ├── examples/
│       │   ├── randomAgent.ts
│       │   └── llmAgent.ts
│       ├── package.json
│       ├── tsconfig.json
│       └── README.md
├── docs/
│   ├── openapi.yaml                   # OpenAPI 3.0 规范（自动生成+手动补充）
│   ├── agent-guide.md                 # Agent 接入指南
│   ├── deployment.md                  # 部署指南
│   └── design/
│       └── design.md                  # 本设计文档（同步副本）
├── docker-compose.yml
├── docker-compose.dev.yml             # 开发环境（含 hot-reload）
├── .env.example
├── README.md
├── LICENSE                            # MIT
└── Makefile                           # 常用命令快捷方式
```

---

## 4. 数据模型

### 4.1 PostgreSQL Schema

```sql
-- 房间表
CREATE TABLE rooms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'waiting',
    config JSONB NOT NULL,
    created_by VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    winner VARCHAR(20),
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

-- 玩家（单局参与记录）
CREATE TABLE players (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    room_id UUID NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    agent_id UUID NOT NULL REFERENCES agents(id),
    seat_number INT NOT NULL,
    role VARCHAR(30) NOT NULL,
    is_alive BOOLEAN DEFAULT TRUE,
    eliminated_at_round INT,
    elimination_reason VARCHAR(30),
    UNIQUE(room_id, seat_number),
    UNIQUE(room_id, agent_id)
);

-- 游戏事件日志（完整回放数据源）
CREATE TABLE game_events (
    id BIGSERIAL PRIMARY KEY,
    room_id UUID NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    round_number INT NOT NULL,
    phase VARCHAR(30) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    actor_player_id UUID REFERENCES players(id),
    target_player_id UUID REFERENCES players(id),
    payload JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_events_room_round ON game_events(room_id, round_number, phase);
CREATE INDEX idx_events_room_id ON game_events(room_id);
```

### 4.2 SQLAlchemy 模型

```python
# app/models/room.py
class Room(Base):
    __tablename__ = "rooms"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="waiting")
    config: Mapped[dict] = mapped_column(JSONB)
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, default=func.now())
    started_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMPTZ)
    finished_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMPTZ)
    winner: Mapped[Optional[str]] = mapped_column(String(20))
    
    players: Mapped[list["Player"]] = relationship(back_populates="room", cascade="all, delete-orphan")
    events: Mapped[list["GameEvent"]] = relationship(back_populates="room", cascade="all, delete-orphan")

# app/models/agent.py
class Agent(Base):
    __tablename__ = "agents"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    api_key: Mapped[str] = mapped_column(String(64), unique=True)
    owner: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, default=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

# app/models/player.py
class Player(Base):
    __tablename__ = "players"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"))
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id"))
    seat_number: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(30))
    is_alive: Mapped[bool] = mapped_column(Boolean, default=True)
    eliminated_at_round: Mapped[Optional[int]] = mapped_column(Integer)
    elimination_reason: Mapped[Optional[str]] = mapped_column(String(30))
    
    room: Mapped["Room"] = relationship(back_populates="players")
    agent: Mapped["Agent"] = relationship()

# app/models/game_event.py
class GameEvent(Base):
    __tablename__ = "game_events"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"))
    round_number: Mapped[int] = mapped_column(Integer)
    phase: Mapped[str] = mapped_column(String(30))
    event_type: Mapped[str] = mapped_column(String(50))
    actor_player_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("players.id"))
    target_player_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("players.id"))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, default=func.now())
    
    room: Mapped["Room"] = relationship(back_populates="events")
```

### 4.3 Pydantic Schemas

```python
# app/schemas/room.py
class RoomConfig(BaseModel):
    player_count: int = Field(ge=6, le=12, default=8)
    roles: dict[str, int]  # {"werewolf": 2, "seer": 1, ...}
    speech_timeout: int = Field(ge=30, le=120, default=60)
    action_timeout: int = Field(ge=30, le=120, default=45)
    vote_timeout: int = Field(ge=30, le=120, default=30)
    
    @model_validator(mode="after")
    def validate_roles(self) -> "RoomConfig":
        total = sum(self.roles.values())
        if total != self.player_count:
            raise ValueError(f"角色总数 {total} != 玩家数 {self.player_count}")
        if self.roles.get("werewolf", 0) < 1:
            raise ValueError("至少需要1名狼人")
        villager_side = total - self.roles.get("werewolf", 0)
        if self.roles.get("werewolf", 0) >= villager_side:
            raise ValueError("狼人数量必须少于好人阵营")
        return self

class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    config: RoomConfig

class RoomResponse(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    config: RoomConfig
    created_at: datetime
    player_count: int
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    winner: Optional[str] = None

class RoomListResponse(BaseModel):
    rooms: list[RoomResponse]
    total: int

# app/schemas/agent.py
class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    owner: Optional[str] = None

class AgentResponse(BaseModel):
    id: uuid.UUID
    name: str
    api_key: str  # 只在创建时返回完整 key
    created_at: datetime

# app/schemas/action.py
class NightAction(BaseModel):
    action_type: str  # kill/investigate/heal/poison/skip
    target_seat: Optional[int] = None
    chain_of_thought: Optional[str] = None

class SpeechAction(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    chain_of_thought: Optional[str] = None

class VoteAction(BaseModel):
    target_seat: int  # 0 = 弃票
    chain_of_thought: Optional[str] = None

class ActionSubmit(BaseModel):
    """统一行动提交 Schema"""
    action: str  # night_action / speech / vote
    data: Union[NightAction, SpeechAction, VoteAction]

# app/schemas/event.py
class GameEventSchema(BaseModel):
    event: str  # game.start / phase.night / phase.day.speech / phase.day.vote / game.end
    data: dict
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    room_id: uuid.UUID
```

### 4.4 Redis 数据结构

```
# 房间实时状态 (Hash)
room:{room_id}:state
  phase: "waiting" | "night" | "result" | "day_speech" | "day_vote" | "execution" | "check_win" | "finished"
  round: int
  current_speaker_seat: int | null
  speaker_index: int
  alive_seats: "[1,2,3,5,7]"  # JSON array
  night_kill_target: int | null
  night_actions_received: "{\"seer\": true, \"witch\": false}"

# 女巫药水状态 (Hash)
room:{room_id}:witch_state
  heal_remaining: 1
  poison_remaining: 1

# Agent 连接状态 (Hash)
room:{room_id}:connections
  {agent_id}: "connected" | "disconnected"
  {agent_id}:last_seen: timestamp (epoch seconds)

# 超时定时器 (Sorted Set)
room:timeouts  →  member="{room_id}:{player_id}:{action_type}", score=expiry_epoch

# 事件 Pub/Sub 频道
channel:room:{room_id}:events              # 广播（观战者订阅）
channel:room:{room_id}:agent:{agent_id}    # 私有频道（仅特定 Agent）

# 狼人团队夜间投票 (List, TTL=action_timeout)
room:{room_id}:werewolf_votes  →  "{player_id}:{target_seat}"

# 白天投票收集 (Hash, TTL=vote_timeout)
room:{room_id}:day_votes
  {player_id}: target_seat

# 断线 Agent 上下文缓存 (String, TTL=300s)
room:{room_id}:agent:{agent_id}:context  →  JSON
```

---

## 5. 核心模块设计

### 5.1 应用入口 & 生命周期

```python
# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动
    app.state.db_engine = create_async_engine(settings.database_url, pool_size=20)
    app.state.redis = await aioredis.from_url(settings.redis_url, decode_responses=True)
    app.state.event_bus = EventBus(app.state.redis)
    app.state.scheduler = AgentScheduler(app.state.redis, app.state.event_bus)
    
    # 启动后台超时检查器
    app.state.timeout_task = asyncio.create_task(app.state.scheduler.run_timeout_checker())
    
    # 加载角色配置
    RoleRegistry.load_from_config("roles_config/")
    
    yield
    
    # 关闭
    app.state.timeout_task.cancel()
    await app.state.redis.close()
    await app.state.db_engine.dispose()

app = FastAPI(
    title="Werewolf Arena",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# 注册路由
from app.api.router import api_router
from app.ws.agent_handler import agent_ws_endpoint
from app.ws.spectator_handler import spectator_ws_endpoint

app.include_router(api_router, prefix="/api/v1")
app.add_api_websocket_route("/ws/agent/{room_id}", agent_ws_endpoint)
app.add_api_websocket_route("/ws/spectate/{room_id}", spectator_ws_endpoint)

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/ready")
async def ready(redis: Redis = Depends(get_redis), db: AsyncSession = Depends(get_db)):
    await redis.ping()
    await db.execute(text("SELECT 1"))
    return {"status": "ready"}
```

### 5.2 配置管理

```python
# app/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # 数据库
    database_url: str = "postgresql+asyncpg://werewolf:werewolf@localhost:5432/werewolf"
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"
    
    # 认证
    api_key_header: str = "X-API-Key"
    
    # 游戏默认配置
    default_speech_timeout: int = 60
    default_action_timeout: int = 45
    default_vote_timeout: int = 30
    
    # 超时检查间隔
    timeout_check_interval: float = 1.0
    
    # 断线重连窗口（秒）
    reconnect_window: int = 120
    
    # Bot 托管启用
    bot_takeover_enabled: bool = True
    
    # CORS
    cors_origins: list[str] = ["*"]
    
    # 日志
    log_level: str = "INFO"
    
    model_config = {"env_prefix": "WEREWOLF_", "env_file": ".env"}
```

### 5.3 游戏引擎 (GameEngine)

#### 5.3.1 GameState 数据类

```python
# app/engine/game_state.py
from dataclasses import dataclass, field
from typing import Optional
import json

@dataclass
class PlayerState:
    player_id: str
    agent_id: str
    seat_number: int
    role: str
    is_alive: bool = True
    eliminated_at_round: Optional[int] = None
    elimination_reason: Optional[str] = None

@dataclass
class GameState:
    """游戏状态 - 内存中维护，与 Redis 同步"""
    room_id: str
    phase: str = "waiting"
    round_number: int = 0
    players: dict[int, PlayerState] = field(default_factory=dict)  # seat -> PlayerState
    current_speaker_seat: Optional[int] = None
    speaker_order: list[int] = field(default_factory=list)
    speaker_index: int = 0
    night_kill_target: Optional[int] = None
    night_actions_received: dict[str, bool] = field(default_factory=dict)  # role -> done
    witch_heal_remaining: int = 1
    witch_poison_remaining: int = 1
    day_votes: dict[str, int] = field(default_factory=dict)  # player_id -> target_seat
    speeches_this_round: list[dict] = field(default_factory=list)
    
    @property
    def alive_players(self) -> list[PlayerState]:
        return [p for p in self.players.values() if p.is_alive]
    
    @property
    def alive_seats(self) -> list[int]:
        return sorted([p.seat_number for p in self.alive_players])
    
    def get_player_by_seat(self, seat: int) -> Optional[PlayerState]:
        return self.players.get(seat)
    
    def get_player_by_id(self, player_id: str) -> Optional[PlayerState]:
        for p in self.players.values():
            if p.player_id == player_id:
                return p
        return None
    
    def get_players_by_role(self, role: str) -> list[PlayerState]:
        return [p for p in self.players.values() if p.role == role and p.is_alive]
    
    async def sync_to_redis(self, redis) -> None:
        """同步关键状态到 Redis（供断线重连恢复）"""
        await redis.hset(f"room:{self.room_id}:state", mapping={
            "phase": self.phase,
            "round": str(self.round_number),
            "alive_seats": json.dumps(self.alive_seats),
            "current_speaker_seat": str(self.current_speaker_seat or ""),
            "night_kill_target": str(self.night_kill_target or ""),
        })
    
    @classmethod
    async def restore_from_redis(cls, redis, room_id: str, db) -> "GameState":
        """从 Redis + DB 恢复状态（用于断线重连、服务重启）"""
        state_data = await redis.hgetall(f"room:{room_id}:state")
        # ... 从 DB 加载 players，从 Redis 恢复阶段状态
        ...
```

#### 5.3.2 阶段状态机

```
  [WAITING] ──(满员)──► [NIGHT] ──(所有行动完成)──► [RESULT]
                          ▲                           │
                          │                           ▼
                    [CHECK_WIN] ◄── [EXECUTION] ◄── [DAY_VOTE] ◄── [DAY_SPEECH]
                          │                                            ▲
                          │                                            │
                     (无胜者)────────────────────────────────────── [RESULT]
                          │
                     (有胜者)
                          ▼
                      [FINISHED]
```

#### 5.3.3 PhaseHandler 接口

```python
# app/engine/phases/base.py
from abc import ABC, abstractmethod
from typing import Optional

class PhaseHandler(ABC):
    """每个阶段的处理器接口"""
    
    def __init__(self, engine: "GameEngine"):
        self.engine = engine
        self.event_bus = engine.event_bus
        self.redis = engine.redis
    
    @abstractmethod
    async def enter(self, game_state: "GameState") -> None:
        """进入该阶段时调用：推送事件给相关玩家，设置超时"""
        ...
    
    @abstractmethod
    async def handle_action(self, game_state: "GameState", player_id: str, action: dict) -> None:
        """处理玩家在该阶段提交的行动"""
        ...
    
    @abstractmethod
    async def on_timeout(self, game_state: "GameState", player_id: str) -> None:
        """处理玩家超时"""
        ...
    
    @abstractmethod
    async def check_complete(self, game_state: "GameState") -> bool:
        """检查该阶段是否所有行动已完成"""
        ...
    
    async def exit(self, game_state: "GameState") -> Optional[str]:
        """退出该阶段，返回下一阶段名称"""
        ...
```

#### 5.3.4 NightPhaseHandler 细化

```python
# app/engine/phases/night.py
class NightPhaseHandler(PhaseHandler):
    """夜晚阶段：所有有夜间行动的角色同时收到请求，各自独立响应"""
    
    async def enter(self, game_state: "GameState") -> None:
        game_state.round_number += 1
        game_state.phase = "night"
        game_state.night_kill_target = None
        game_state.night_actions_received = {}
        
        # 确定需要行动的角色
        for player in game_state.alive_players:
            strategy = RoleRegistry.get(player.role)
            action_type = strategy.get_night_action_type()
            
            if action_type is None:
                # 村民等无夜间行动角色，直接标记完成
                continue
            
            game_state.night_actions_received[player.role] = False
            
            # 构建事件数据
            event_data = {
                "round": game_state.round_number,
                "your_role": player.role,
                "action_type": action_type,
                "available_targets": strategy.get_available_targets(player, game_state.alive_players),
                "timeout": self.engine.settings.default_action_timeout,
                "context": {"alive_players": game_state.alive_seats},
            }
            
            # 女巫特殊信息
            if player.role == "witch":
                event_data["heal_remaining"] = game_state.witch_heal_remaining
                event_data["poison_remaining"] = game_state.witch_poison_remaining
                # 注意：第一轮狼人还没行动，witch 需要等狼人行动后才知道击杀目标
                # 通过 on_werewolf_action_complete 回调通知
            
            await self.event_bus.publish_to_agent(
                game_state.room_id, player.agent_id,
                GameEvent(event="phase.night", room_id=game_state.room_id, data=event_data)
            )
            
            # 设置超时
            await self.engine.scheduler.request_action(
                game_state.room_id, player.player_id,
                f"night_{player.role}", self.engine.settings.default_action_timeout
            )
        
        # 通知观战者
        await self.event_bus.publish_to_spectators(
            game_state.room_id,
            GameEvent(event="phase.night", room_id=game_state.room_id, data={
                "round": game_state.round_number,
                "awaiting_roles": list(game_state.night_actions_received.keys()),
            })
        )
        
        await game_state.sync_to_redis(self.redis)
        
        # 如果没有角色需要行动（理论上不应发生），直接完成
        if not game_state.night_actions_received:
            await self.engine.transition_to("result", game_state)
    
    async def handle_action(self, game_state: "GameState", player_id: str, action: dict) -> None:
        player = game_state.get_player_by_id(player_id)
        if not player:
            return
        
        strategy = RoleRegistry.get(player.role)
        
        # 执行角色行动
        result = await strategy.execute_night_action(player, action, game_state)
        
        # 标记完成
        game_state.night_actions_received[player.role] = True
        
        # 处理行动结果
        if result.type == "kill":
            game_state.night_kill_target = result.target_seat
            # 通知女巫狼人的击杀目标（如果女巫还没行动）
            witch_players = game_state.get_players_by_role("witch")
            for witch in witch_players:
                if not game_state.night_actions_received.get("witch", True):
                    await self.event_bus.publish_to_agent(
                        game_state.room_id, witch.agent_id,
                        GameEvent(event="phase.night.update", room_id=game_state.room_id, data={
                            "werewolf_kill_target": result.target_seat,
                        })
                    )
        
        elif result.type == "investigate":
            # 查验结果只推送给预言家
            await self.event_bus.publish_to_agent(
                game_state.room_id, player.agent_id,
                GameEvent(event="phase.night.result", room_id=game_state.room_id, data={
                    "investigation": result.result,
                })
            )
        
        elif result.type == "heal":
            if game_state.witch_heal_remaining > 0:
                game_state.night_kill_target = None  # 解药救人
                game_state.witch_heal_remaining -= 1
        
        elif result.type == "poison":
            game_state.witch_poison_remaining -= 1
            # 毒药效果在 ResultPhaseHandler 中处理
        
        # 取消超时
        await self.engine.scheduler.cancel_timeout(
            game_state.room_id, player_id, f"night_{player.role}"
        )
        
        # 持久化事件
        await self.event_bus.persist_event(
            self.engine.db, 
            GameEvent(event=f"night.{result.type}", room_id=game_state.room_id, data={
                "actor_seat": player.seat_number,
                "target_seat": result.target_seat,
                "chain_of_thought": action.get("chain_of_thought"),
            }),
            game_state.round_number, "night",
            actor_id=player_id
        )
        
        # 通知观战者（含完整信息）
        await self.event_bus.publish_to_spectators(
            game_state.room_id,
            GameEvent(event=f"night.action", room_id=game_state.room_id, data={
                "role": player.role,
                "seat": player.seat_number,
                "action_type": result.type,
                "target_seat": result.target_seat,
                "chain_of_thought": action.get("chain_of_thought"),
            })
        )
        
        # 检查是否全部完成
        if await self.check_complete(game_state):
            await self.engine.transition_to("result", game_state)
    
    async def on_timeout(self, game_state: "GameState", player_id: str) -> None:
        player = game_state.get_player_by_id(player_id)
        if player:
            game_state.night_actions_received[player.role] = True  # 标记弃权
            if await self.check_complete(game_state):
                await self.engine.transition_to("result", game_state)
    
    async def check_complete(self, game_state: "GameState") -> bool:
        return all(game_state.night_actions_received.values())
```

#### 5.3.5 DaySpeechPhaseHandler 细化

```python
# app/engine/phases/day_speech.py
class DaySpeechPhaseHandler(PhaseHandler):
    """白天发言阶段：按座位轮流发言"""
    
    async def enter(self, game_state: "GameState") -> None:
        game_state.phase = "day_speech"
        game_state.speeches_this_round = []
        
        # 发言顺序：存活玩家按座位号升序
        game_state.speaker_order = game_state.alive_seats
        game_state.speaker_index = 0
        
        if not game_state.speaker_order:
            await self.engine.transition_to("day_vote", game_state)
            return
        
        await self._notify_next_speaker(game_state)
        await game_state.sync_to_redis(self.redis)
    
    async def _notify_next_speaker(self, game_state: "GameState") -> None:
        seat = game_state.speaker_order[game_state.speaker_index]
        player = game_state.get_player_by_seat(seat)
        game_state.current_speaker_seat = seat
        
        event_data = {
            "round": game_state.round_number,
            "your_seat": seat,
            "current_speaker": seat,
            "timeout": self.engine.settings.default_speech_timeout,
            "previous_speeches": game_state.speeches_this_round.copy(),
            "context": {
                "alive_players": game_state.alive_seats,
                "eliminated_last_night": [],  # 从 result phase 传递
                "speaker_order": game_state.speaker_order,
                "speakers_remaining": game_state.speaker_order[game_state.speaker_index + 1:],
            },
        }
        
        # 通知当前发言者
        await self.event_bus.publish_to_agent(
            game_state.room_id, player.agent_id,
            GameEvent(event="phase.day.speech", room_id=game_state.room_id, data=event_data)
        )
        
        # 通知其他 Agent 谁在发言
        for p in game_state.alive_players:
            if p.seat_number != seat:
                await self.event_bus.publish_to_agent(
                    game_state.room_id, p.agent_id,
                    GameEvent(event="phase.day.speech.waiting", room_id=game_state.room_id, data={
                        "current_speaker": seat,
                        "your_turn_in": game_state.speaker_order.index(p.seat_number) - game_state.speaker_index
                        if p.seat_number in game_state.speaker_order[game_state.speaker_index:]
                        else -1,
                    })
                )
        
        # 观战者
        await self.event_bus.publish_to_spectators(
            game_state.room_id,
            GameEvent(event="phase.day.speech", room_id=game_state.room_id, data={
                "round": game_state.round_number,
                "current_speaker": seat,
                "speaker_index": game_state.speaker_index,
                "total_speakers": len(game_state.speaker_order),
            })
        )
        
        # 超时
        await self.engine.scheduler.request_action(
            game_state.room_id, player.player_id,
            "speech", self.engine.settings.default_speech_timeout
        )
    
    async def handle_action(self, game_state: "GameState", player_id: str, action: dict) -> None:
        player = game_state.get_player_by_id(player_id)
        if not player or player.seat_number != game_state.current_speaker_seat:
            return  # 不是当前发言者，忽略
        
        speech_record = {
            "seat": player.seat_number,
            "content": action["content"],
            "chain_of_thought": action.get("chain_of_thought"),
        }
        game_state.speeches_this_round.append(speech_record)
        
        # 取消超时
        await self.engine.scheduler.cancel_timeout(
            game_state.room_id, player_id, "speech"
        )
        
        # 持久化
        await self.event_bus.persist_event(
            self.engine.db,
            GameEvent(event="day.speech", room_id=game_state.room_id, data=speech_record),
            game_state.round_number, "day_speech", actor_id=player_id
        )
        
        # 广播发言给所有人
        public_speech = {"seat": player.seat_number, "content": action["content"]}
        spectator_speech = {**public_speech, "chain_of_thought": action.get("chain_of_thought")}
        
        for p in game_state.alive_players:
            if p.player_id != player_id:
                await self.event_bus.publish_to_agent(
                    game_state.room_id, p.agent_id,
                    GameEvent(event="day.speech.broadcast", room_id=game_state.room_id, data=public_speech)
                )
        
        await self.event_bus.publish_to_spectators(
            game_state.room_id,
            GameEvent(event="day.speech.broadcast", room_id=game_state.room_id, data=spectator_speech)
        )
        
        # 下一位发言者
        game_state.speaker_index += 1
        if game_state.speaker_index < len(game_state.speaker_order):
            await self._notify_next_speaker(game_state)
        else:
            await self.engine.transition_to("day_vote", game_state)
    
    async def on_timeout(self, game_state: "GameState", player_id: str) -> None:
        player = game_state.get_player_by_id(player_id)
        if player:
            game_state.speeches_this_round.append({
                "seat": player.seat_number,
                "content": "（沉默）",
                "chain_of_thought": None,
            })
            game_state.speaker_index += 1
            if game_state.speaker_index < len(game_state.speaker_order):
                await self._notify_next_speaker(game_state)
            else:
                await self.engine.transition_to("day_vote", game_state)
    
    async def check_complete(self, game_state: "GameState") -> bool:
        return game_state.speaker_index >= len(game_state.speaker_order)
```

#### 5.3.6 DayVotePhaseHandler 细化

```python
# app/engine/phases/day_vote.py
class DayVotePhaseHandler(PhaseHandler):
    """投票阶段：所有存活玩家同时投票"""
    
    async def enter(self, game_state: "GameState") -> None:
        game_state.phase = "day_vote"
        game_state.day_votes = {}
        
        event_data = {
            "round": game_state.round_number,
            "candidates": game_state.alive_seats,
            "timeout": self.engine.settings.default_vote_timeout,
            "speeches": [{"seat": s["seat"], "content": s["content"]} 
                        for s in game_state.speeches_this_round],
            "context": {"alive_players": game_state.alive_seats},
        }
        
        # 通知所有存活 Agent
        for player in game_state.alive_players:
            await self.event_bus.publish_to_agent(
                game_state.room_id, player.agent_id,
                GameEvent(event="phase.day.vote", room_id=game_state.room_id, data={
                    **event_data, "your_seat": player.seat_number
                })
            )
            await self.engine.scheduler.request_action(
                game_state.room_id, player.player_id,
                "vote", self.engine.settings.default_vote_timeout
            )
        
        # 观战者
        await self.event_bus.publish_to_spectators(
            game_state.room_id,
            GameEvent(event="phase.day.vote", room_id=game_state.room_id, data=event_data)
        )
        
        await game_state.sync_to_redis(self.redis)
    
    async def handle_action(self, game_state: "GameState", player_id: str, action: dict) -> None:
        if player_id in game_state.day_votes:
            return  # 已投票，忽略重复
        
        player = game_state.get_player_by_id(player_id)
        target_seat = action["target_seat"]
        game_state.day_votes[player_id] = target_seat
        
        # 取消超时
        await self.engine.scheduler.cancel_timeout(game_state.room_id, player_id, "vote")
        
        # 持久化
        await self.event_bus.persist_event(
            self.engine.db,
            GameEvent(event="day.vote", room_id=game_state.room_id, data={
                "seat": player.seat_number,
                "target_seat": target_seat,
                "chain_of_thought": action.get("chain_of_thought"),
            }),
            game_state.round_number, "day_vote", actor_id=player_id
        )
        
        # 观战者实时看到投票
        await self.event_bus.publish_to_spectators(
            game_state.room_id,
            GameEvent(event="day.vote.cast", room_id=game_state.room_id, data={
                "seat": player.seat_number,
                "target_seat": target_seat,
                "chain_of_thought": action.get("chain_of_thought"),
                "votes_received": len(game_state.day_votes),
                "votes_total": len(game_state.alive_players),
            })
        )
        
        if await self.check_complete(game_state):
            await self.engine.transition_to("execution", game_state)
    
    async def on_timeout(self, game_state: "GameState", player_id: str) -> None:
        if player_id not in game_state.day_votes:
            game_state.day_votes[player_id] = 0  # 弃票
            if await self.check_complete(game_state):
                await self.engine.transition_to("execution", game_state)
    
    async def check_complete(self, game_state: "GameState") -> bool:
        alive_ids = {p.player_id for p in game_state.alive_players}
        return alive_ids.issubset(set(game_state.day_votes.keys()))
```

#### 5.3.7 ExecutionPhaseHandler 细化

```python
# app/engine/phases/execution.py
class ExecutionPhaseHandler(PhaseHandler):
    """处决阶段：统计投票结果，执行处决"""
    
    async def enter(self, game_state: "GameState") -> None:
        game_state.phase = "execution"
        
        # 统计投票
        vote_counts: dict[int, int] = {}  # seat -> count
        vote_details: list[dict] = []
        
        for player_id, target_seat in game_state.day_votes.items():
            player = game_state.get_player_by_id(player_id)
            vote_details.append({"from_seat": player.seat_number, "to_seat": target_seat})
            if target_seat != 0:  # 0 = 弃票
                vote_counts[target_seat] = vote_counts.get(target_seat, 0) + 1
        
        # 找出票数最多的玩家
        eliminated_seat = None
        eliminated_reason = "voted_out"
        
        if vote_counts:
            max_votes = max(vote_counts.values())
            candidates = [seat for seat, count in vote_counts.items() if count == max_votes]
            
            if len(candidates) == 1:
                eliminated_seat = candidates[0]
            else:
                # 平票：无人被处决
                eliminated_seat = None
        
        # 执行处决
        hunter_death_pending = False
        if eliminated_seat:
            target_player = game_state.get_player_by_seat(eliminated_seat)
            target_player.is_alive = False
            target_player.eliminated_at_round = game_state.round_number
            target_player.elimination_reason = eliminated_reason
            
            # 持久化到 DB
            await self._update_player_db(target_player)
            
            # 检查猎人被处决
            if target_player.role == "hunter":
                hunter_death_pending = True
        
        # 公布投票结果
        result_data = {
            "round": game_state.round_number,
            "votes": vote_details,
            "vote_counts": {str(k): v for k, v in vote_counts.items()},
            "eliminated": {"seat": eliminated_seat, "reason": eliminated_reason} if eliminated_seat else None,
            "is_tie": len([s for s, c in vote_counts.items() if c == max(vote_counts.values())]) > 1 if vote_counts else False,
        }
        
        # 广播给所有 Agent
        for player in game_state.alive_players:
            await self.event_bus.publish_to_agent(
                game_state.room_id, player.agent_id,
                GameEvent(event="phase.execution", room_id=game_state.room_id, data=result_data)
            )
        
        # 观战者看到完整投票流向
        await self.event_bus.publish_to_spectators(
            game_state.room_id,
            GameEvent(event="phase.execution", room_id=game_state.room_id, data={
                **result_data,
                "eliminated_role": target_player.role if eliminated_seat else None,
            })
        )
        
        # 猎人技能处理
        if hunter_death_pending:
            await self._handle_hunter_death(game_state, target_player)
            return  # 等待猎人选择后再进入 check_win
        
        await self.engine.transition_to("check_win", game_state)
    
    async def _handle_hunter_death(self, game_state: "GameState", hunter: "PlayerState") -> None:
        """猎人死亡时触发射杀选择"""
        await self.event_bus.publish_to_agent(
            game_state.room_id, hunter.agent_id,
            GameEvent(event="phase.hunter.shoot", room_id=game_state.room_id, data={
                "your_seat": hunter.seat_number,
                "available_targets": [s for s in game_state.alive_seats if s != hunter.seat_number],
                "timeout": self.engine.settings.default_action_timeout,
            })
        )
        await self.engine.scheduler.request_action(
            game_state.room_id, hunter.player_id,
            "hunter_shoot", self.engine.settings.default_action_timeout
        )
    
    async def handle_action(self, game_state: "GameState", player_id: str, action: dict) -> None:
        # 猎人射杀行动
        player = game_state.get_player_by_id(player_id)
        if player and player.role == "hunter":
            target_seat = action.get("target_seat")
            if target_seat and target_seat in game_state.alive_seats:
                target = game_state.get_player_by_seat(target_seat)
                target.is_alive = False
                target.eliminated_at_round = game_state.round_number
                target.elimination_reason = "hunter_shot"
                await self._update_player_db(target)
            
            await self.engine.scheduler.cancel_timeout(
                game_state.room_id, player_id, "hunter_shoot"
            )
            await self.engine.transition_to("check_win", game_state)
    
    async def on_timeout(self, game_state: "GameState", player_id: str) -> None:
        # 猎人超时不射杀
        await self.engine.transition_to("check_win", game_state)
    
    async def check_complete(self, game_state: "GameState") -> bool:
        return True  # 自动流转

    async def _update_player_db(self, player_state: "PlayerState") -> None:
        """更新 DB 中玩家状态"""
        result = await self.engine.db.execute(
            update(Player).where(Player.id == player_state.player_id).values(
                is_alive=player_state.is_alive,
                eliminated_at_round=player_state.eliminated_at_round,
                elimination_reason=player_state.elimination_reason,
            )
        )
        await self.engine.db.commit()
```

#### 5.3.8 ResultPhaseHandler 细化

```python
# app/engine/phases/result.py
class ResultPhaseHandler(PhaseHandler):
    """结算阶段：公布夜晚结果"""
    
    async def enter(self, game_state: "GameState") -> None:
        game_state.phase = "result"
        eliminated = []
        
        # 处理狼人击杀
        if game_state.night_kill_target:
            target = game_state.get_player_by_seat(game_state.night_kill_target)
            if target and target.is_alive:
                target.is_alive = False
                target.eliminated_at_round = game_state.round_number
                target.elimination_reason = "killed"
                eliminated.append({"seat": target.seat_number, "reason": "killed"})
                await self._update_player_db(target)
                
                # 猎人被杀：触发射杀
                if target.role == "hunter":
                    # 暂存，等结果公布后处理
                    pass
        
        # 处理女巫毒药
        # (毒药目标在 night phase 中已记录到 game_state)
        
        # 公布结果
        result_data = {
            "round": game_state.round_number,
            "phase": "night",
            "eliminated": eliminated,
            "message": self._build_result_message(eliminated),
        }
        
        # 广播
        for player in game_state.alive_players:
            await self.event_bus.publish_to_agent(
                game_state.room_id, player.agent_id,
                GameEvent(event="phase.result", room_id=game_state.room_id, data=result_data)
            )
        
        await self.event_bus.publish_to_spectators(
            game_state.room_id,
            GameEvent(event="phase.result", room_id=game_state.room_id, data={
                **result_data,
                "eliminated_roles": {e["seat"]: game_state.get_player_by_seat(e["seat"]).role 
                                     for e in eliminated},
            })
        )
        
        # 自动转入胜负判定
        await self.engine.transition_to("check_win", game_state)
    
    def _build_result_message(self, eliminated: list) -> str:
        if not eliminated:
            return "昨晚是平安夜，无人遇害"
        seats = ", ".join(str(e["seat"]) for e in eliminated)
        return f"昨晚 {seats} 号被杀害"
    
    async def handle_action(self, game_state, player_id, action):
        pass  # 结算阶段无玩家行动
    
    async def on_timeout(self, game_state, player_id):
        pass
    
    async def check_complete(self, game_state) -> bool:
        return True
    
    async def _update_player_db(self, player_state):
        result = await self.engine.db.execute(
            update(Player).where(Player.id == player_state.player_id).values(
                is_alive=player_state.is_alive,
                eliminated_at_round=player_state.eliminated_at_round,
                elimination_reason=player_state.elimination_reason,
            )
        )
        await self.engine.db.commit()
```

#### 5.3.9 CheckWinPhaseHandler

```python
# app/engine/phases/check_win.py
class CheckWinPhaseHandler(PhaseHandler):
    async def enter(self, game_state: "GameState") -> None:
        game_state.phase = "check_win"
        winner = self._check_winner(game_state)
        
        if winner:
            await self.engine.end_game(game_state, winner)
        else:
            await self.engine.transition_to("night", game_state)
    
    def _check_winner(self, game_state: "GameState") -> Optional[str]:
        alive = game_state.alive_players
        werewolves = [p for p in alive if p.role == "werewolf"]
        villagers = [p for p in alive if p.role != "werewolf"]
        
        if len(werewolves) == 0:
            return "villager"
        if len(werewolves) >= len(villagers):
            return "werewolf"
        return None
    
    async def handle_action(self, game_state, player_id, action):
        pass
    async def on_timeout(self, game_state, player_id):
        pass
    async def check_complete(self, game_state) -> bool:
        return True
```

#### 5.3.10 GameEngine 主控制器

```python
# app/engine/game_engine.py
class GameEngine:
    """游戏引擎主控制器 - 每个活跃房间一个实例"""
    
    # 类级别：活跃引擎注册表
    _active_engines: dict[str, "GameEngine"] = {}
    
    def __init__(self, db: AsyncSession, redis: Redis, event_bus: EventBus,
                 scheduler: AgentScheduler, settings: Settings):
        self.db = db
        self.redis = redis
        self.event_bus = event_bus
        self.scheduler = scheduler
        self.settings = settings
        self.phase_handlers: dict[str, PhaseHandler] = {
            "night": NightPhaseHandler(self),
            "result": ResultPhaseHandler(self),
            "day_speech": DaySpeechPhaseHandler(self),
            "day_vote": DayVotePhaseHandler(self),
            "execution": ExecutionPhaseHandler(self),
            "check_win": CheckWinPhaseHandler(self),
        }
    
    @classmethod
    def get_engine(cls, room_id: str) -> Optional["GameEngine"]:
        return cls._active_engines.get(room_id)
    
    async def start_game(self, room_id: str, players: list[Player]) -> GameState:
        """游戏开始"""
        game_state = GameState(room_id=room_id)
        
        for player in players:
            game_state.players[player.seat_number] = PlayerState(
                player_id=str(player.id),
                agent_id=str(player.agent_id),
                seat_number=player.seat_number,
                role=player.role,
            )
        
        # 注册引擎
        self._active_engines[room_id] = self
        
        # 向每个 Agent 推送 game.start（只含自己的角色）
        for ps in game_state.players.values():
            await self.event_bus.publish_to_agent(
                room_id, ps.agent_id,
                GameEvent(event="game.start", room_id=room_id, data={
                    "room_id": room_id,
                    "your_role": ps.role,
                    "your_seat": ps.seat_number,
                    "player_count": len(game_state.players),
                    "players": [{"seat": p.seat_number, "is_alive": True} 
                               for p in game_state.players.values()],
                    "config": {
                        "speech_timeout": self.settings.default_speech_timeout,
                        "action_timeout": self.settings.default_action_timeout,
                        "vote_timeout": self.settings.default_vote_timeout,
                    },
                })
            )
        
        # 观战者看到所有角色
        await self.event_bus.publish_to_spectators(
            room_id,
            GameEvent(event="game.start", room_id=room_id, data={
                "room_id": room_id,
                "player_count": len(game_state.players),
                "players": [{"seat": p.seat_number, "role": p.role, "is_alive": True}
                           for p in game_state.players.values()],
            })
        )
        
        # 进入第一个夜晚
        await self.transition_to("night", game_state)
        return game_state
    
    async def transition_to(self, phase: str, game_state: GameState, **kwargs) -> None:
        """阶段流转"""
        game_state.phase = phase
        await game_state.sync_to_redis(self.redis)
        
        handler = self.phase_handlers.get(phase)
        if handler:
            await handler.enter(game_state)
    
    async def handle_action(self, room_id: str, player_id: str, action: ActionSubmit) -> None:
        """处理 Agent 提交的行动"""
        # 从 Redis 获取当前阶段
        state_data = await self.redis.hgetall(f"room:{room_id}:state")
        current_phase = state_data.get("phase")
        
        handler = self.phase_handlers.get(current_phase)
        if not handler:
            raise GameError(f"Invalid phase: {current_phase}")
        
        # 从活跃引擎获取 game_state
        # (实际实现中 game_state 需要持久化或从 Redis 恢复)
        await handler.handle_action(self._game_states[room_id], player_id, action.data.model_dump())
    
    async def end_game(self, game_state: GameState, winner: str) -> None:
        """游戏结束"""
        room_id = game_state.room_id
        
        # 更新 DB
        await self.db.execute(
            update(Room).where(Room.id == room_id).values(
                status="finished",
                winner=winner,
                finished_at=datetime.utcnow(),
            )
        )
        await self.db.commit()
        
        # 广播 game.end
        all_roles = {str(p.seat_number): p.role for p in game_state.players.values()}
        
        for ps in game_state.players.values():
            await self.event_bus.publish_to_agent(
                room_id, ps.agent_id,
                GameEvent(event="game.end", room_id=room_id, data={
                    "winner": winner,
                    "your_role": ps.role,
                    "all_roles": all_roles,
                    "rounds_played": game_state.round_number,
                    "replay_url": f"/api/v1/rooms/{room_id}/replay",
                })
            )
        
        await self.event_bus.publish_to_spectators(
            room_id,
            GameEvent(event="game.end", room_id=room_id, data={
                "winner": winner,
                "all_roles": all_roles,
                "rounds_played": game_state.round_number,
            })
        )
        
        # 清理
        self._active_engines.pop(room_id, None)
        # 保留 Redis 事件数据用于回放，清理临时状态
        for key in await self.redis.keys(f"room:{room_id}:*"):
            if ":state" in key or ":connections" in key or ":votes" in key:
                await self.redis.delete(key)
```

### 5.4 角色系统 (Role Strategy)

```python
# app/engine/roles/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

@dataclass
class ActionResult:
    type: str           # kill / investigate / heal / poison / shoot / skip
    target_seat: Optional[int] = None
    result: Optional[dict] = None
    private_to: Optional[str] = None
    cancel_kill: bool = False
    requires_response: bool = False

class RoleStrategy(ABC):
    """角色策略基类"""
    role_id: str
    role_name: str
    faction: str  # "werewolf" | "villager"
    night_action_priority: int
    
    @abstractmethod
    def get_night_action_type(self) -> Optional[str]:
        ...
    
    @abstractmethod
    def get_available_targets(self, player, alive_players) -> list[int]:
        ...
    
    @abstractmethod
    async def execute_night_action(self, player, action, game_state) -> ActionResult:
        ...
    
    def validate_action(self, action, player, game_state) -> bool:
        if action.target_seat is not None:
            available = self.get_available_targets(player, game_state.alive_players)
            return action.target_seat in available
        return True
```

具体角色实现：

| 角色 | role_id | faction | 夜间行动 | 特殊机制 |
|------|---------|---------|---------|---------|
| 狼人 | `werewolf` | werewolf | `kill` - 选择击杀目标 | 多狼人取多数投票 |
| 预言家 | `seer` | villager | `investigate` - 查验身份 | 结果私有推送 |
| 女巫 | `witch` | villager | `heal_or_poison` - 解药/毒药 | 各限1次，需等狼人行动 |
| 猎人 | `hunter` | villager | 无主动行动 | 被动：死亡时射杀 |
| 村民 | `villager` | villager | 无 | 无特殊能力 |

```python
# app/engine/roles/registry.py
class RoleRegistry:
    _strategies: dict[str, RoleStrategy] = {}
    
    @classmethod
    def register(cls, strategy: RoleStrategy) -> None:
        cls._strategies[strategy.role_id] = strategy
    
    @classmethod
    def get(cls, role_id: str) -> RoleStrategy:
        if role_id not in cls._strategies:
            raise ValueError(f"Unknown role: {role_id}")
        return cls._strategies[role_id]
    
    @classmethod
    def load_from_config(cls, config_dir: str) -> None:
        """从 YAML 配置目录注册所有内置角色"""
        cls.register(WerewolfStrategy())
        cls.register(SeerStrategy())
        cls.register(WitchStrategy())
        cls.register(HunterStrategy())
        cls.register(VillagerStrategy())
```

### 5.5 角色 YAML 配置

```yaml
# roles_config/werewolf.yaml
id: werewolf
name: 狼人
name_en: Werewolf
faction: werewolf
night_action_priority: 1
night_action_type: kill
description: "夜晚选择一名玩家击杀。多个狼人需要统一目标。"
abilities:
  - type: active
    phase: night
    name: 击杀
    target: non_werewolf_alive

# roles_config/seer.yaml
id: seer
name: 预言家
name_en: Seer
faction: villager
night_action_priority: 2
night_action_type: investigate
description: "夜晚选择一名玩家查验其身份（狼人/好人）。"
abilities:
  - type: active
    phase: night
    name: 查验
    target: other_alive
    result: faction_check

# roles_config/witch.yaml
id: witch
name: 女巫
name_en: Witch
faction: villager
night_action_priority: 3
night_action_type: heal_or_poison
description: "拥有一瓶解药（救人）和一瓶毒药（毒人），各限使用一次。"
abilities:
  - type: active
    phase: night
    name: 解药
    uses: 1
    condition: "night_kill_target exists"
  - type: active
    phase: night
    name: 毒药
    uses: 1
    target: other_alive

# roles_config/hunter.yaml
id: hunter
name: 猎人
name_en: Hunter
faction: villager
night_action_priority: 99
night_action_type: null
description: "死亡时可以选择射杀一名存活玩家。"
abilities:
  - type: passive
    trigger: on_death
    name: 射杀
    target: other_alive

# roles_config/villager.yaml
id: villager
name: 村民
name_en: Villager
faction: villager
night_action_priority: 99
night_action_type: null
description: "没有特殊能力。通过推理和投票帮助好人阵营获胜。"
abilities: []
```

### 5.6 事件总线 (EventBus)

```python
# app/services/event_bus.py
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from redis.asyncio import Redis

@dataclass
class GameEvent:
    event: str
    room_id: str
    data: dict
    timestamp: datetime = None
    private_to: Optional[str] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
    
    def to_json(self) -> str:
        return json.dumps({
            "event": self.event,
            "room_id": self.room_id,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        })

class EventBus:
    def __init__(self, redis: Redis):
        self.redis = redis
    
    async def publish_to_agent(self, room_id: str, agent_id: str, event: GameEvent) -> None:
        await self.redis.publish(f"channel:room:{room_id}:agent:{agent_id}", event.to_json())
    
    async def publish_to_spectators(self, room_id: str, event: GameEvent) -> None:
        await self.redis.publish(f"channel:room:{room_id}:events", event.to_json())
    
    async def publish_public(self, room_id: str, event: GameEvent, agent_ids: list[str]) -> None:
        await self.publish_to_spectators(room_id, event)
        for agent_id in agent_ids:
            await self.publish_to_agent(room_id, agent_id, event)
    
    async def persist_event(self, db, event: GameEvent, round_num: int, phase: str,
                            actor_id: str = None, target_id: str = None) -> None:
        from app.models.game_event import GameEvent as GameEventModel
        game_event = GameEventModel(
            room_id=event.room_id,
            round_number=round_num,
            phase=phase,
            event_type=event.event,
            actor_player_id=actor_id,
            target_player_id=target_id,
            payload=event.data,
        )
        db.add(game_event)
        await db.commit()
```

### 5.7 房间服务 (RoomService)

```python
# app/services/room_service.py
class RoomService:
    def __init__(self, db: AsyncSession, redis: Redis, event_bus: EventBus):
        self.db = db
        self.redis = redis
        self.event_bus = event_bus
    
    async def create_room(self, data: RoomCreate) -> Room:
        room = Room(name=data.name, config=data.config.model_dump(), status="waiting")
        self.db.add(room)
        await self.db.commit()
        await self.db.refresh(room)
        
        await self.redis.hset(f"room:{room.id}:state", mapping={
            "phase": "waiting", "round": "0", "alive_seats": "[]",
        })
        return room
    
    async def join_room(self, room_id: str, agent_id: str) -> Player:
        room = await self._get_room(room_id)
        if room.status != "waiting":
            raise GameError("房间不在等待状态")
        
        existing = await self._get_room_players(room_id)
        if len(existing) >= room.config["player_count"]:
            raise GameError("房间已满")
        if any(str(p.agent_id) == agent_id for p in existing):
            raise GameError("已在房间中")
        
        seat = len(existing) + 1
        player = Player(room_id=room_id, agent_id=agent_id, seat_number=seat, role="unassigned")
        self.db.add(player)
        await self.db.commit()
        
        if len(existing) + 1 >= room.config["player_count"]:
            await self._start_game(room)
        
        return player
    
    async def _start_game(self, room: Room) -> None:
        players = await self._get_room_players(str(room.id))
        roles = self._distribute_roles(room.config["roles"], len(players))
        
        import random
        random.shuffle(roles)
        for player, role in zip(players, roles):
            player.role = role
        
        room.status = "playing"
        room.started_at = datetime.utcnow()
        await self.db.commit()
        
        engine = GameEngine(self.db, self.redis, self.event_bus, 
                           self.scheduler, self.settings)
        await engine.start_game(str(room.id), players)
    
    def _distribute_roles(self, roles_config: dict, total: int) -> list[str]:
        roles = []
        for role, count in roles_config.items():
            roles.extend([role] * count)
        return roles
    
    async def list_rooms(self, status: Optional[str] = None, limit: int = 20, offset: int = 0):
        query = select(Room).order_by(Room.created_at.desc())
        if status:
            query = query.where(Room.status == status)
        count_q = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(count_q)
        result = await self.db.execute(query.offset(offset).limit(limit))
        return result.scalars().all(), total
    
    async def get_room_state(self, room_id: str, requester_agent_id: Optional[str] = None) -> dict:
        room = await self._get_room(room_id)
        players = await self._get_room_players(room_id)
        redis_state = await self.redis.hgetall(f"room:{room_id}:state")
        
        state = {
            "room": RoomResponse.model_validate(room).model_dump(),
            "phase": redis_state.get("phase", room.status),
            "round": int(redis_state.get("round", 0)),
            "players": [],
        }
        
        for p in players:
            player_info = {"seat": p.seat_number, "is_alive": p.is_alive, "agent_id": str(p.agent_id)}
            if requester_agent_id and str(p.agent_id) == requester_agent_id:
                player_info["role"] = p.role
            elif requester_agent_id is None:
                player_info["role"] = p.role  # 观战者
            state["players"].append(player_info)
        
        return state
```

### 5.8 Agent 调度器 (AgentScheduler)

```python
# app/services/agent_scheduler.py
class AgentScheduler:
    def __init__(self, redis: Redis, event_bus: EventBus):
        self.redis = redis
        self.event_bus = event_bus
    
    async def request_action(self, room_id: str, player_id: str,
                              action_type: str, timeout: int) -> None:
        import time
        expiry = time.time() + timeout
        await self.redis.zadd("room:timeouts", {
            f"{room_id}:{player_id}:{action_type}": expiry
        })
    
    async def cancel_timeout(self, room_id: str, player_id: str, action_type: str) -> None:
        await self.redis.zrem("room:timeouts", f"{room_id}:{player_id}:{action_type}")
    
    async def run_timeout_checker(self) -> None:
        """后台 asyncio task：每秒检查超时"""
        import time
        while True:
            now = time.time()
            expired = await self.redis.zrangebyscore("room:timeouts", 0, now)
            for key in expired:
                await self.redis.zrem("room:timeouts", key)
                parts = key.split(":")
                if len(parts) >= 3:
                    room_id, player_id, action_type = parts[0], parts[1], ":".join(parts[2:])
                    await self._handle_timeout(room_id, player_id, action_type)
            await asyncio.sleep(1)
    
    async def _handle_timeout(self, room_id: str, player_id: str, action_type: str) -> None:
        engine = GameEngine.get_engine(room_id)
        if engine:
            state_data = await self.redis.hgetall(f"room:{room_id}:state")
            current_phase = state_data.get("phase")
            handler = engine.phase_handlers.get(current_phase)
            if handler:
                await handler.on_timeout(engine._game_states.get(room_id), player_id)
    
    async def track_connection(self, room_id: str, agent_id: str, connected: bool) -> None:
        import time
        await self.redis.hset(f"room:{room_id}:connections", mapping={
            agent_id: "connected" if connected else "disconnected",
            f"{agent_id}:last_seen": str(time.time()),
        })
```

### 5.9 WebSocket Hub

```python
# app/ws/hub.py
class ConnectionManager:
    def __init__(self):
        self.agent_connections: dict[str, WebSocket] = {}
        self.spectator_connections: dict[str, list[WebSocket]] = {}
    
    async def connect_agent(self, ws: WebSocket, agent_id: str, room_id: str) -> None:
        await ws.accept()
        self.agent_connections[agent_id] = ws
    
    async def disconnect_agent(self, agent_id: str) -> None:
        self.agent_connections.pop(agent_id, None)
    
    async def connect_spectator(self, ws: WebSocket, room_id: str) -> None:
        await ws.accept()
        self.spectator_connections.setdefault(room_id, []).append(ws)
    
    async def disconnect_spectator(self, ws: WebSocket, room_id: str) -> None:
        if room_id in self.spectator_connections:
            self.spectator_connections[room_id] = [
                c for c in self.spectator_connections[room_id] if c != ws
            ]

manager = ConnectionManager()

# app/ws/agent_handler.py
async def agent_ws_endpoint(ws: WebSocket, room_id: str):
    """Agent WebSocket 端点"""
    redis = ws.app.state.redis
    
    # 认证
    api_key = ws.query_params.get("api_key")
    if not api_key:
        await ws.close(code=4001, reason="Missing API key")
        return
    
    agent = await authenticate_agent(api_key)
    if not agent:
        await ws.close(code=4003, reason="Invalid API key")
        return
    
    agent_id = str(agent.id)
    await manager.connect_agent(ws, agent_id, room_id)
    await ws.app.state.scheduler.track_connection(room_id, agent_id, connected=True)
    
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"channel:room:{room_id}:agent:{agent_id}")
    
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(_forward_redis_to_ws(pubsub, ws))
            tg.create_task(_receive_agent_actions(ws, room_id, agent_id))
    except* WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect_agent(agent_id)
        await ws.app.state.scheduler.track_connection(room_id, agent_id, connected=False)
        await pubsub.unsubscribe()

async def _forward_redis_to_ws(pubsub, ws: WebSocket):
    async for message in pubsub.listen():
        if message["type"] == "message":
            await ws.send_text(message["data"])

async def _receive_agent_actions(ws: WebSocket, room_id: str, agent_id: str):
    async for data in ws.iter_json():
        action = ActionSubmit.model_validate(data)
        engine = GameEngine.get_engine(room_id)
        if engine:
            player = await get_player_by_agent(room_id, agent_id)
            await engine.handle_action(room_id, str(player.id), action)

# app/ws/spectator_handler.py
async def spectator_ws_endpoint(ws: WebSocket, room_id: str):
    redis = ws.app.state.redis
    await manager.connect_spectator(ws, room_id)
    
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"channel:room:{room_id}:events")
    
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                await ws.send_text(message["data"])
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect_spectator(ws, room_id)
        await pubsub.unsubscribe()
```

### 5.10 行动校验器 (ActionValidator)

```python
# app/engine/action_validator.py
class ActionValidator:
    def __init__(self, role_registry: RoleRegistry):
        self.role_registry = role_registry
    
    async def validate(self, player: Player, action: ActionSubmit,
                        current_phase: str, game_state: GameState) -> tuple[bool, Optional[str]]:
        if not player.is_alive:
            return False, "你已被淘汰"
        
        phase_action_map = {"night": "night_action", "day_speech": "speech", "day_vote": "vote"}
        expected = phase_action_map.get(current_phase)
        if action.action != expected:
            return False, f"当前阶段 {current_phase} 不接受 {action.action}"
        
        if action.action == "night_action":
            strategy = self.role_registry.get(player.role)
            if not strategy.validate_action(action.data, player, game_state):
                return False, "无效的夜间行动目标"
        elif action.action == "speech":
            if len(action.data.content) > 2000:
                return False, "发言超过字数限制"
        elif action.action == "vote":
            if action.data.target_seat != 0 and action.data.target_seat not in game_state.alive_seats:
                return False, "投票目标不存在或已被淘汰"
        
        return True, None
```

### 5.11 回放服务 (ReplayService)

```python
# app/services/replay_service.py
class ReplayService:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_full_replay(self, room_id: str) -> dict:
        room = await self.db.get(Room, room_id)
        if not room or room.status != "finished":
            raise GameError("游戏尚未结束")
        
        events = await self.db.execute(
            select(GameEventModel).where(GameEventModel.room_id == room_id).order_by(GameEventModel.id)
        )
        events = events.scalars().all()
        
        players = await self.db.execute(
            select(Player).where(Player.room_id == room_id).options(joinedload(Player.agent))
        )
        players = players.scalars().all()
        
        return {
            "room": {
                "id": str(room.id), "name": room.name, "config": room.config,
                "winner": room.winner,
                "started_at": room.started_at.isoformat(),
                "finished_at": room.finished_at.isoformat(),
            },
            "players": [{
                "seat": p.seat_number, "role": p.role, "agent_name": p.agent.name,
                "eliminated_at_round": p.eliminated_at_round,
                "elimination_reason": p.elimination_reason,
            } for p in players],
            "events": [{
                "id": e.id, "round": e.round_number, "phase": e.phase,
                "event_type": e.event_type, "payload": e.payload,
                "timestamp": e.created_at.isoformat(),
            } for e in events],
            "total_rounds": max((e.round_number for e in events), default=0),
        }
    
    async def get_round_replay(self, room_id: str, round_num: int) -> dict:
        events = await self.db.execute(
            select(GameEventModel)
            .where(GameEventModel.room_id == room_id, GameEventModel.round_number == round_num)
            .order_by(GameEventModel.id)
        )
        return {"round": round_num, "events": [e.payload for e in events.scalars().all()]}
```

### 5.12 断线重连 & Bot 托管

```python
# 断线重连流程（集成在 agent_handler.py）
async def handle_reconnect(ws: WebSocket, room_id: str, agent_id: str, redis: Redis):
    """Agent 断线重连"""
    # 1. 检查房间是否仍在进行
    state = await redis.hgetall(f"room:{room_id}:state")
    if state.get("phase") == "finished":
        await ws.send_json({"event": "error", "data": {"message": "游戏已结束"}})
        return
    
    # 2. 恢复上下文：推送当前游戏状态
    cached_context = await redis.get(f"room:{room_id}:agent:{agent_id}:context")
    if cached_context:
        await ws.send_json({"event": "reconnect.state", "data": json.loads(cached_context)})
    
    # 3. 如果当前正等待该 Agent 行动，重新推送请求
    engine = GameEngine.get_engine(room_id)
    if engine:
        # 检查是否有该 Agent 的待处理超时
        pending = await redis.zscore("room:timeouts", f"{room_id}:{agent_id}:*")
        if pending:
            # 重新发送行动请求事件
            ...
    
    # 4. 更新连接状态
    await redis.hset(f"room:{room_id}:connections", agent_id, "connected")

# Bot 托管（在 AgentScheduler 中）
class BotFallback:
    """断线超时后的 Bot 自动接管"""
    
    @staticmethod
    async def generate_action(role: str, phase: str, game_state: GameState) -> dict:
        """为断线 Agent 生成随机合法行动"""
        if phase == "night":
            strategy = RoleRegistry.get(role)
            action_type = strategy.get_night_action_type()
            if action_type:
                targets = strategy.get_available_targets(...)
                target = random.choice(targets) if targets else None
                return {"action": "night_action", "data": {"action_type": action_type, "target_seat": target}}
        
        elif phase == "day_speech":
            return {"action": "speech", "data": {"content": "（托管中，暂无发言）"}}
        
        elif phase == "day_vote":
            return {"action": "vote", "data": {"target_seat": 0}}  # 弃票
        
        return {}
```

---

## 6. API 设计

### 6.1 REST API 路由

#### 房间管理

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/api/v1/rooms` | 创建房间 | 可选 |
| GET | `/api/v1/rooms` | 列出房间（?status=waiting&limit=20&offset=0） | 无 |
| GET | `/api/v1/rooms/{room_id}` | 获取房间详情 | 无 |
| POST | `/api/v1/rooms/{room_id}/join` | Agent 加入房间 | API Key |
| GET | `/api/v1/rooms/{room_id}/state` | 获取房间状态（按权限过滤） | 可选 API Key |

#### Agent 行动

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/api/v1/rooms/{room_id}/actions` | 提交行动 | API Key |
| GET | `/api/v1/rooms/{room_id}/history` | 获取公开历史 | 无 |

#### Agent 管理

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/api/v1/agents` | 注册 Agent | 无 |
| GET | `/api/v1/agents/{agent_id}` | Agent 信息 | 无 |

#### 回放

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | `/api/v1/rooms/{room_id}/replay` | 完整回放 | 无 |
| GET | `/api/v1/rooms/{room_id}/replay/rounds/{round}` | 回合回放 | 无 |

#### 系统

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/ready` | 就绪检查（含 DB + Redis ping） |

### 6.2 WebSocket 端点

| 端点 | 说明 | 认证 |
|------|------|------|
| `ws://.../ws/agent/{room_id}?api_key=xxx` | Agent 实时通道 | API Key |
| `ws://.../ws/spectate/{room_id}` | 观战通道 | 无 |

### 6.3 API 路由实现

```python
# app/api/rooms.py
from fastapi import APIRouter, Depends, HTTPException, Query

router = APIRouter(prefix="/rooms", tags=["rooms"])

@router.post("", response_model=RoomResponse, status_code=201)
async def create_room(data: RoomCreate, room_service: RoomService = Depends(get_room_service)):
    room = await room_service.create_room(data)
    return RoomResponse.model_validate(room)

@router.get("", response_model=RoomListResponse)
async def list_rooms(
    status: Optional[str] = Query(None, regex="^(waiting|playing|finished)$"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    room_service: RoomService = Depends(get_room_service),
):
    rooms, total = await room_service.list_rooms(status, limit, offset)
    return RoomListResponse(rooms=[RoomResponse.model_validate(r) for r in rooms], total=total)

@router.get("/{room_id}", response_model=RoomResponse)
async def get_room(room_id: uuid.UUID, room_service: RoomService = Depends(get_room_service)):
    room = await room_service.get_room(str(room_id))
    if not room:
        raise HTTPException(404, "Room not found")
    return RoomResponse.model_validate(room)

@router.post("/{room_id}/join")
async def join_room(
    room_id: uuid.UUID,
    agent: Agent = Depends(get_current_agent),
    room_service: RoomService = Depends(get_room_service),
):
    player = await room_service.join_room(str(room_id), str(agent.id))
    return {"seat": player.seat_number, "player_id": str(player.id)}

@router.get("/{room_id}/state")
async def get_room_state(
    room_id: uuid.UUID,
    agent: Optional[Agent] = Depends(get_optional_agent),
    room_service: RoomService = Depends(get_room_service),
):
    agent_id = str(agent.id) if agent else None
    return await room_service.get_room_state(str(room_id), agent_id)

# app/api/actions.py
router = APIRouter(prefix="/rooms/{room_id}/actions", tags=["actions"])

@router.post("")
async def submit_action(
    room_id: uuid.UUID,
    action: ActionSubmit,
    agent: Agent = Depends(get_current_agent),
):
    engine = GameEngine.get_engine(str(room_id))
    if not engine:
        raise HTTPException(400, "Game not active")
    player = await get_player_by_agent(str(room_id), str(agent.id))
    await engine.handle_action(str(room_id), str(player.id), action)
    return {"status": "accepted"}

# app/api/agents.py
router = APIRouter(prefix="/agents", tags=["agents"])

@router.post("", response_model=AgentResponse, status_code=201)
async def register_agent(data: AgentCreate, agent_service: AgentService = Depends(get_agent_service)):
    agent = await agent_service.register(data)
    return AgentResponse.model_validate(agent)

# app/api/replay.py
router = APIRouter(prefix="/rooms/{room_id}/replay", tags=["replay"])

@router.get("")
async def get_replay(room_id: uuid.UUID, replay_service: ReplayService = Depends(get_replay_service)):
    return await replay_service.get_full_replay(str(room_id))

@router.get("/rounds/{round_num}")
async def get_round_replay(
    room_id: uuid.UUID, round_num: int,
    replay_service: ReplayService = Depends(get_replay_service),
):
    return await replay_service.get_round_replay(str(room_id), round_num)

# app/api/router.py
from fastapi import APIRouter
from app.api import rooms, agents, actions, replay

api_router = APIRouter()
api_router.include_router(rooms.router)
api_router.include_router(agents.router)
api_router.include_router(actions.router)
api_router.include_router(replay.router)
```

### 6.4 认证中间件

```python
# app/middleware/auth.py
from fastapi import Depends, HTTPException, Header
from typing import Optional

async def get_current_agent(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> Agent:
    agent = await db.execute(
        select(Agent).where(Agent.api_key == x_api_key, Agent.is_active == True)
    )
    agent = agent.scalar_one_or_none()
    if not agent:
        raise HTTPException(401, "Invalid or inactive API key")
    return agent

async def get_optional_agent(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> Optional[Agent]:
    if not x_api_key:
        return None
    return await get_current_agent(x_api_key, db)
```

### 6.5 事件消息 Schema

#### 服务端 → Agent

```jsonc
// game.start
{
  "event": "game.start",
  "data": {
    "room_id": "uuid",
    "your_role": "seer",
    "your_seat": 3,
    "player_count": 8,
    "players": [{"seat": 1, "is_alive": true}, ...],
    "config": {"speech_timeout": 60, "action_timeout": 45, "vote_timeout": 30}
  }
}

// phase.night
{
  "event": "phase.night",
  "data": {
    "round": 1,
    "your_role": "seer",
    "action_type": "investigate",
    "available_targets": [1, 2, 4, 5, 6, 7, 8],
    "timeout": 45,
    "context": {"alive_players": [1, 2, 3, 4, 5, 6, 7, 8]}
  }
}

// phase.night (witch)
{
  "event": "phase.night",
  "data": {
    "round": 1,
    "your_role": "witch",
    "action_type": "heal_or_poison",
    "werewolf_kill_target": 5,
    "heal_remaining": 1,
    "poison_remaining": 1,
    "available_poison_targets": [1, 2, 3, 4, 6, 7, 8],
    "timeout": 45
  }
}

// phase.day.speech
{
  "event": "phase.day.speech",
  "data": {
    "round": 1,
    "your_seat": 3,
    "current_speaker": 3,
    "timeout": 60,
    "previous_speeches": [
      {"seat": 1, "content": "我觉得3号很可疑..."},
      {"seat": 2, "content": "我昨晚被查了..."}
    ],
    "context": {
      "alive_players": [1, 2, 3, 4, 5, 6, 7, 8],
      "eliminated_last_night": [],
      "speaker_order": [1, 2, 3, 4, 5, 6, 7, 8],
      "speakers_remaining": [4, 5, 6, 7, 8]
    }
  }
}

// phase.day.vote
{
  "event": "phase.day.vote",
  "data": {
    "round": 1,
    "your_seat": 3,
    "candidates": [1, 2, 3, 4, 5, 6, 7, 8],
    "timeout": 30,
    "speeches": [{"seat": 1, "content": "..."}, ...],
    "context": {"alive_players": [1, 2, 3, 4, 5, 6, 7, 8]}
  }
}

// phase.result
{
  "event": "phase.result",
  "data": {
    "round": 1,
    "phase": "night",
    "eliminated": [{"seat": 5, "reason": "killed"}],
    "message": "昨晚5号被狼人杀害"
  }
}

// game.end
{
  "event": "game.end",
  "data": {
    "winner": "villager",
    "your_role": "seer",
    "all_roles": {"1": "werewolf", "2": "villager", "3": "seer", ...},
    "rounds_played": 3,
    "replay_url": "/api/v1/rooms/{room_id}/replay"
  }
}
```

#### Agent → 服务端

```jsonc
// 夜晚行动
{"action": "night_action", "data": {"action_type": "investigate", "target_seat": 5, "chain_of_thought": "..."}}

// 发言
{"action": "speech", "data": {"content": "我是预言家...", "chain_of_thought": "..."}}

// 投票
{"action": "vote", "data": {"target_seat": 5, "chain_of_thought": "..."}}
```

---

## 7. 前端设计

### 7.1 路由结构

```
/                        → 首页（房间大厅 + 创建入口）
/rooms                   → 房间列表（支持 ?status 过滤）
/rooms/create            → 创建房间页面
/rooms/:roomId/spectate  → 观战实时界面
/rooms/:roomId/replay    → 历史回放
```

```tsx
// App.tsx
import { BrowserRouter, Routes, Route } from "react-router-dom";

function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/rooms" element={<Home />} />
          <Route path="/rooms/create" element={<CreateRoom />} />
          <Route path="/rooms/:roomId/spectate" element={<Spectate />} />
          <Route path="/rooms/:roomId/replay" element={<Replay />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
```

### 7.2 核心组件设计

#### SeatCircle - 环形座位布局

```tsx
// src/components/game/SeatCircle.tsx
interface SeatCircleProps {
  players: PlayerInfo[];
  currentPhase: string;
  currentSpeaker?: number;
  highlightSeat?: number;
}

/**
 * 环形布局：玩家卡片围成一圈。
 * - 使用 CSS transform: rotate + translate 实现圆形排列
 * - 每个座位显示: 座位号、角色图标(观战者可见)、存活/淘汰状态
 * - 当前发言者高亮动画（脉冲边框）
 * - 被淘汰的座位灰色半透明
 * - 点击座位可查看该 Agent 的详细信息（CoT、历史发言）
 */
```

#### EventStream - 事件/发言流

```tsx
// src/components/game/EventStream.tsx
interface EventStreamProps {
  events: GameEvent[];
  showCoT: boolean;
}

/**
 * 类似聊天界面的事件流：
 * - 发言：头像(座位号) + 角色标签 + 发言内容
 * - 系统事件：居中灰色文字（"天黑了"、"5号被淘汰"）
 * - CoT 折叠面板：点击展开 Agent 的思维过程（Chain-of-Thought）
 * - 投票事件：投票流向可视化小卡片
 * - 自动滚动到最新事件
 * - 时间戳标记
 */
```

#### PhaseIndicator - 阶段指示器

```tsx
// src/components/game/PhaseIndicator.tsx
interface PhaseIndicatorProps {
  phase: string;
  round: number;
  timeout?: number;      // 剩余秒数
  currentSpeaker?: number;
}

/**
 * 顶部阶段条：
 * - 进度条：NIGHT → RESULT → SPEECH → VOTE → EXECUTION
 * - 当前阶段高亮 + 倒计时
 * - 回合数显示
 * - 夜晚阶段：深色主题 + 月亮图标
 * - 白天阶段：亮色主题 + 太阳图标
 */
```

#### 统计面板

```tsx
// src/components/stats/VoteFlowChart.tsx
/**
 * D3.js 桑基图/弦图：展示投票流向
 * - 每个节点 = 一个座位
 * - 连线 = 投票方向，粗细 = 投票轮次
 * - 颜色编码阵营（观战者视角）
 */

// src/components/stats/IdentityHeatmap.tsx
/**
 * D3.js 热力图：CoT 中提取的身份概率估计
 * - X 轴 = 被估计的玩家座位
 * - Y 轴 = 估计者（各 Agent）
 * - 颜色 = 被估计为狼人的概率（红 = 高, 蓝 = 低）
 * - 仅在 Agent 提供 CoT 数据时可用
 */

// src/components/stats/StatsPanel.tsx
/**
 * 统计汇总：
 * - 存活追踪：好人 vs 狼人存活数量条形图
 * - 发言字数统计
 * - 投票被投次数排行
 * - 获胜概率估计（基于存活比）
 */
```

### 7.3 状态管理 (Zustand)

```typescript
// src/stores/gameStore.ts
import { create } from "zustand";

interface GameState {
  roomId: string | null;
  phase: string;
  round: number;
  players: PlayerInfo[];
  events: GameEvent[];
  speeches: Speech[];
  votes: VoteRecord[];
  timeout: number;
  currentSpeaker: number | null;
  connected: boolean;
  
  // Actions
  setRoom: (roomId: string) => void;
  updatePhase: (phase: string, round: number) => void;
  addEvent: (event: GameEvent) => void;
  updatePlayer: (seat: number, update: Partial<PlayerInfo>) => void;
  addSpeech: (speech: Speech) => void;
  addVote: (vote: VoteRecord) => void;
  setTimer: (seconds: number) => void;
  reset: () => void;
}

export const useGameStore = create<GameState>((set, get) => ({
  // ... initial state and actions
}));

// src/stores/roomStore.ts
interface RoomListState {
  rooms: RoomInfo[];
  total: number;
  loading: boolean;
  filter: { status?: string };
  
  fetchRooms: (params?: { status?: string; limit?: number; offset?: number }) => Promise<void>;
  setFilter: (filter: { status?: string }) => void;
}

// src/stores/replayStore.ts
interface ReplayState {
  replayData: ReplayData | null;
  currentEventIndex: number;
  playing: boolean;
  speed: number;  // 1x, 2x, 4x
  
  loadReplay: (roomId: string) => Promise<void>;
  play: () => void;
  pause: () => void;
  stepForward: () => void;
  stepBackward: () => void;
  seekTo: (index: number) => void;
  setSpeed: (speed: number) => void;
}
```

### 7.4 WebSocket Hook

```typescript
// src/hooks/useWebSocket.ts
import { useEffect, useRef, useCallback } from "react";
import { useGameStore } from "../stores/gameStore";

export function useSpectatorWS(roomId: string) {
  const ws = useRef<WebSocket | null>(null);
  const addEvent = useGameStore(s => s.addEvent);
  const updatePhase = useGameStore(s => s.updatePhase);
  
  const connect = useCallback(() => {
    const url = `${import.meta.env.VITE_WS_URL}/ws/spectate/${roomId}`;
    ws.current = new WebSocket(url);
    
    ws.current.onmessage = (e) => {
      const event = JSON.parse(e.data);
      addEvent(event);
      
      // 根据事件类型更新对应 store
      switch (event.event) {
        case "game.start":
          // 初始化玩家列表
          break;
        case "phase.night":
        case "phase.day.speech":
        case "phase.day.vote":
          updatePhase(event.event, event.data.round);
          break;
        case "day.speech.broadcast":
          useGameStore.getState().addSpeech(event.data);
          break;
        case "day.vote.cast":
          useGameStore.getState().addVote(event.data);
          break;
        case "game.end":
          // 游戏结束处理
          break;
      }
    };
    
    ws.current.onclose = () => {
      // 自动重连（指数退避）
      setTimeout(connect, 3000);
    };
  }, [roomId]);
  
  useEffect(() => {
    connect();
    return () => ws.current?.close();
  }, [connect]);
  
  return { connected: ws.current?.readyState === WebSocket.OPEN };
}
```

### 7.5 TypeScript 类型定义

```typescript
// src/types/game.ts
export interface PlayerInfo {
  seat: number;
  role?: string;        // 观战者可见
  isAlive: boolean;
  agentId: string;
  agentName?: string;
  eliminatedAtRound?: number;
  eliminationReason?: string;
}

export interface Speech {
  seat: number;
  content: string;
  chainOfThought?: string;
  timestamp?: string;
}

export interface VoteRecord {
  fromSeat: number;
  toSeat: number;
  round: number;
}

export interface GameEvent {
  event: string;
  roomId: string;
  data: Record<string, any>;
  timestamp: string;
}

export interface RoomInfo {
  id: string;
  name: string;
  status: "waiting" | "playing" | "finished";
  config: RoomConfig;
  playerCount: number;
  createdAt: string;
  winner?: string;
}

export interface RoomConfig {
  playerCount: number;
  roles: Record<string, number>;
  speechTimeout: number;
  actionTimeout: number;
  voteTimeout: number;
}

export interface ReplayData {
  room: RoomInfo;
  players: PlayerInfo[];
  events: GameEvent[];
  totalRounds: number;
}
```

### 7.6 回放控制器

```tsx
// src/components/replay/ReplayTimeline.tsx
interface ReplayTimelineProps {
  totalEvents: number;
  currentIndex: number;
  rounds: { round: number; startIndex: number; endIndex: number }[];
  onSeek: (index: number) => void;
}

/**
 * 时间轴控制器：
 * - 底部时间轴滑块，刻度按回合分段
 * - 每回合用颜色段区分（夜=深蓝, 白天=浅黄）
 * - 播放/暂停按钮 + 速度控制（1x/2x/4x）
 * - 单步前进/后退
 * - 回合跳转下拉框
 * - 当前事件描述文字
 */

// src/hooks/useReplay.ts
export function useReplay(roomId: string) {
  const store = useReplayStore();
  
  useEffect(() => {
    store.loadReplay(roomId);
  }, [roomId]);
  
  // 播放定时器
  useEffect(() => {
    if (!store.playing) return;
    
    const interval = setInterval(() => {
      const next = store.currentEventIndex + 1;
      if (next >= (store.replayData?.events.length ?? 0)) {
        store.pause();
        return;
      }
      store.seekTo(next);
    }, 1000 / store.speed);
    
    return () => clearInterval(interval);
  }, [store.playing, store.speed]);
  
  return store;
}
```

### 7.7 UI 主题 & 动画

- **夜晚阶段**：深色覆盖层 + 星空粒子背景，月亮图标，座位卡片发暗光
- **白天阶段**：明亮暖色调，太阳图标
- **淘汰动画**：座位卡片翻转 + 灰度化 + 淡出
- **发言动画**：打字机效果逐字显示
- **投票动画**：从投票者座位到目标座位的弧形连线动画
- **CoT 面板**：抽屉式展开，类似 IDE 的折叠区域
- **使用 Framer Motion** 实现流畅过渡动画

---

## 8. Agent SDK 设计

### 8.1 Python SDK

```python
# sdk/python/werewolf_sdk/agent.py
from abc import ABC, abstractmethod
from typing import Optional
from .models import *
from .client import WerewolfClient

class WerewolfAgent(ABC):
    """Agent 基类 - 开发者需继承并实现各回调方法"""
    
    def __init__(self, name: str, server_url: str, api_key: Optional[str] = None):
        self.name = name
        self.client = WerewolfClient(server_url)
        self.api_key = api_key
        self.agent_id: Optional[str] = None
        self.room_id: Optional[str] = None
        self.my_role: Optional[str] = None
        self.my_seat: Optional[int] = None
    
    async def register(self) -> str:
        """注册 Agent 并获取 API Key"""
        result = await self.client.register_agent(self.name)
        self.agent_id = result["id"]
        self.api_key = result["api_key"]
        return self.api_key
    
    async def join_game(self, room_id: str) -> None:
        """加入房间"""
        self.room_id = room_id
        result = await self.client.join_room(room_id, self.api_key)
        self.my_seat = result["seat"]
    
    async def run(self) -> None:
        """主循环：连接 WebSocket 并处理事件"""
        async with self.client.connect_ws(self.room_id, self.api_key) as ws:
            async for message in ws:
                event = GameEvent.model_validate_json(message)
                await self._dispatch(event, ws)
    
    async def _dispatch(self, event: GameEvent, ws) -> None:
        match event.event:
            case "game.start":
                self.my_role = event.data["your_role"]
                self.my_seat = event.data["your_seat"]
                await self.on_game_start(event.data)
            
            case "phase.night":
                action = await self.on_night_action(event.data)
                if action:
                    await ws.send_json({"action": "night_action", "data": action.model_dump()})
            
            case "phase.day.speech":
                if event.data.get("current_speaker") == self.my_seat:
                    speech = await self.on_speech_turn(event.data)
                    await ws.send_json({"action": "speech", "data": speech.model_dump()})
            
            case "day.speech.broadcast":
                await self.on_speech_heard(event.data)
            
            case "phase.day.vote":
                vote = await self.on_vote(event.data)
                await ws.send_json({"action": "vote", "data": vote.model_dump()})
            
            case "phase.result":
                await self.on_phase_result(event.data)
            
            case "game.end":
                await self.on_game_end(event.data)
    
    # === 需要开发者实现的回调 ===
    
    @abstractmethod
    async def on_game_start(self, data: dict) -> None:
        """游戏开始，收到角色分配"""
        ...
    
    @abstractmethod
    async def on_night_action(self, data: dict) -> Optional[NightAction]:
        """夜晚行动请求 → 返回行动（或 None 跳过）"""
        ...
    
    @abstractmethod
    async def on_speech_turn(self, data: dict) -> SpeechAction:
        """轮到你发言 → 返回发言内容"""
        ...
    
    async def on_speech_heard(self, data: dict) -> None:
        """听到其他玩家发言（可选覆盖）"""
        pass
    
    @abstractmethod
    async def on_vote(self, data: dict) -> VoteAction:
        """投票请求 → 返回投票目标"""
        ...
    
    async def on_phase_result(self, data: dict) -> None:
        """阶段结算结果（可选覆盖）"""
        pass
    
    async def on_game_end(self, data: dict) -> None:
        """游戏结束（可选覆盖）"""
        pass


# sdk/python/werewolf_sdk/client.py
import httpx
from contextlib import asynccontextmanager
import websockets

class WerewolfClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.http = httpx.AsyncClient(base_url=f"{self.base_url}/api/v1")
    
    async def register_agent(self, name: str) -> dict:
        r = await self.http.post("/agents", json={"name": name})
        r.raise_for_status()
        return r.json()
    
    async def list_rooms(self, status: str = None) -> dict:
        params = {}
        if status:
            params["status"] = status
        r = await self.http.get("/rooms", params=params)
        r.raise_for_status()
        return r.json()
    
    async def join_room(self, room_id: str, api_key: str) -> dict:
        r = await self.http.post(
            f"/rooms/{room_id}/join",
            headers={"X-API-Key": api_key}
        )
        r.raise_for_status()
        return r.json()
    
    @asynccontextmanager
    async def connect_ws(self, room_id: str, api_key: str):
        ws_url = self.base_url.replace("http", "ws")
        async with websockets.connect(
            f"{ws_url}/ws/agent/{room_id}?api_key={api_key}"
        ) as ws:
            yield ws
```

### 8.2 TypeScript SDK

```typescript
// sdk/typescript/src/agent.ts
export abstract class WerewolfAgent {
  protected client: WerewolfClient;
  protected roomId?: string;
  protected myRole?: string;
  protected mySeat?: number;
  protected apiKey?: string;
  
  constructor(public name: string, serverUrl: string, apiKey?: string) {
    this.client = new WerewolfClient(serverUrl);
    this.apiKey = apiKey;
  }
  
  async register(): Promise<string> {
    const result = await this.client.registerAgent(this.name);
    this.apiKey = result.api_key;
    return this.apiKey;
  }
  
  async joinGame(roomId: string): Promise<void> {
    this.roomId = roomId;
    const result = await this.client.joinRoom(roomId, this.apiKey!);
    this.mySeat = result.seat;
  }
  
  async run(): Promise<void> {
    const ws = this.client.connectWS(this.roomId!, this.apiKey!);
    ws.on("message", async (data: string) => {
      const event = JSON.parse(data) as GameEvent;
      await this.dispatch(event, ws);
    });
  }
  
  // Abstract methods for subclass implementation
  abstract onGameStart(data: GameStartData): Promise<void>;
  abstract onNightAction(data: NightPhaseData): Promise<NightAction | null>;
  abstract onSpeechTurn(data: SpeechPhaseData): Promise<SpeechAction>;
  abstract onVote(data: VotePhaseData): Promise<VoteAction>;
  onSpeechHeard?(data: SpeechBroadcastData): Promise<void>;
  onPhaseResult?(data: PhaseResultData): Promise<void>;
  onGameEnd?(data: GameEndData): Promise<void>;
}
```

### 8.3 示例 Agent：LLM 驱动

```python
# sdk/python/examples/llm_agent.py
import os
from anthropic import AsyncAnthropic
from werewolf_sdk import WerewolfAgent, NightAction, SpeechAction, VoteAction

class LLMAgent(WerewolfAgent):
    """基于 Claude 的狼人杀 Agent"""
    
    def __init__(self, name: str, server_url: str, api_key: str = None):
        super().__init__(name, server_url, api_key)
        self.llm = AsyncAnthropic()
        self.memory: list[dict] = []
    
    async def _ask_llm(self, system: str, user: str) -> str:
        response = await self.llm.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text
    
    async def on_game_start(self, data: dict) -> None:
        self.memory.append({"type": "game_start", "role": data["your_role"], "seat": data["your_seat"]})
    
    async def on_night_action(self, data: dict) -> NightAction:
        system = f"你是狼人杀游戏中的{data['your_role']}（{self.my_seat}号位）。请根据你的角色和局势做出行动。"
        user = f"当前是第{data['round']}轮夜晚。可选目标：{data['available_targets']}。你的记忆：{self.memory[-10:]}"
        
        response = await self._ask_llm(system, user)
        # 解析 LLM 输出为结构化行动
        target = self._parse_target(response, data["available_targets"])
        
        return NightAction(
            action_type=data["action_type"],
            target_seat=target,
            chain_of_thought=response,
        )
    
    async def on_speech_turn(self, data: dict) -> SpeechAction:
        system = f"你是{self.my_role}（{self.my_seat}号位）。请根据之前的发言和你的推理进行发言。"
        user = f"之前的发言：{data['previous_speeches']}\n你的记忆：{self.memory[-10:]}"
        
        content = await self._ask_llm(system, user)
        return SpeechAction(content=content, chain_of_thought=content)
    
    async def on_vote(self, data: dict) -> VoteAction:
        system = f"你是{self.my_role}。根据所有发言和推理，选择要投票处决的玩家。"
        user = f"候选人：{data['candidates']}\n发言记录：{data.get('speeches', [])}\n记忆：{self.memory[-10:]}"
        
        response = await self._ask_llm(system, user)
        target = self._parse_target(response, data["candidates"])
        return VoteAction(target_seat=target, chain_of_thought=response)

# 运行示例
if __name__ == "__main__":
    import asyncio
    
    agent = LLMAgent("Claude-Seer", "http://localhost:8000")
    
    async def main():
        await agent.register()
        rooms = await agent.client.list_rooms(status="waiting")
        if rooms["rooms"]:
            await agent.join_game(rooms["rooms"][0]["id"])
            await agent.run()
    
    asyncio.run(main())
```

---

## 9. 异常处理

```python
# app/exceptions.py
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

class GameError(Exception):
    def __init__(self, message: str, code: str = "GAME_ERROR"):
        self.message = message
        self.code = code

class RoomFullError(GameError):
    def __init__(self):
        super().__init__("房间已满", "ROOM_FULL")

class InvalidPhaseError(GameError):
    def __init__(self, phase: str):
        super().__init__(f"当前阶段 {phase} 不允许此操作", "INVALID_PHASE")

class NotYourTurnError(GameError):
    def __init__(self):
        super().__init__("还没轮到你", "NOT_YOUR_TURN")

class InvalidTargetError(GameError):
    def __init__(self):
        super().__init__("无效的行动目标", "INVALID_TARGET")

# 全局异常处理器
async def game_error_handler(request: Request, exc: GameError):
    return JSONResponse(
        status_code=400,
        content={"error": exc.code, "message": exc.message},
    )

async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": "INTERNAL_ERROR", "message": "服务器内部错误"},
    )
```

---

## 10. 测试策略

### 10.1 单元测试

| 测试模块 | 覆盖范围 |
|----------|---------|
| `test_phase_fsm.py` | 阶段流转正确性、非法跳转拒绝 |
| `test_roles.py` | 每个角色的 `validate_action()`, `execute_night_action()` |
| `test_win_checker.py` | 各种存活组合下的胜负判定 |
| `test_action_validator.py` | 非法行动拒绝、阶段不匹配、死亡玩家行动 |
| `test_room_service.py` | 创建/加入/满员/状态过滤 |

### 10.2 API 测试

```python
# tests/test_api/test_rooms.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_create_room(client: AsyncClient):
    response = await client.post("/api/v1/rooms", json={
        "name": "测试房间",
        "config": {
            "player_count": 8,
            "roles": {"werewolf": 2, "seer": 1, "witch": 1, "hunter": 1, "villager": 3},
            "speech_timeout": 60,
            "action_timeout": 45,
            "vote_timeout": 30,
        }
    })
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "waiting"
    assert data["name"] == "测试房间"

@pytest.mark.asyncio
async def test_invalid_role_config(client: AsyncClient):
    response = await client.post("/api/v1/rooms", json={
        "name": "bad room",
        "config": {"player_count": 8, "roles": {"werewolf": 5, "villager": 3}}
    })
    assert response.status_code == 422  # 狼人 >= 好人
```

### 10.3 集成测试

```python
# tests/test_integration/test_full_game.py
@pytest.mark.asyncio
async def test_full_game_flow():
    """完整游戏流程：8个 Agent 从创建到结束"""
    # 1. 创建房间
    # 2. 注册 8 个 Agent
    # 3. 所有 Agent 加入
    # 4. 验证自动开始
    # 5. 模拟夜晚行动
    # 6. 验证结算
    # 7. 模拟白天发言 + 投票
    # 8. 重复直到游戏结束
    # 9. 验证回放数据
    ...
```

### 10.4 测试工具

- **pytest + pytest-asyncio**：异步测试
- **httpx**：API 测试客户端
- **fakeredis**：Redis Mock
- **factory-boy**：测试数据工厂
- **testcontainers**：集成测试用 PostgreSQL/Redis 容器

---

## 11. 部署方案

### 11.1 Docker Compose

```yaml
# docker-compose.yml
version: "3.9"

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      WEREWOLF_DATABASE_URL: postgresql+asyncpg://werewolf:werewolf@postgres:5432/werewolf
      WEREWOLF_REDIS_URL: redis://redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000
  
  frontend:
    build: ./frontend
    ports:
      - "3000:80"
    environment:
      VITE_API_URL: http://localhost:8000
      VITE_WS_URL: ws://localhost:8000
  
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: werewolf
      POSTGRES_PASSWORD: werewolf
      POSTGRES_DB: werewolf
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U werewolf"]
      interval: 5s
      timeout: 5s
      retries: 5
  
  redis:
    image: redis:7-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
```

### 11.2 Dockerfile

```dockerfile
# backend/Dockerfile
FROM python:3.12-slim
WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[prod]"

COPY . .
RUN alembic upgrade head || true

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# frontend/Dockerfile
FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

### 11.3 开发环境

```yaml
# docker-compose.dev.yml
version: "3.9"
services:
  postgres:
    image: postgres:16-alpine
    ports: ["5432:5432"]
    environment:
      POSTGRES_USER: werewolf
      POSTGRES_PASSWORD: werewolf
      POSTGRES_DB: werewolf
  
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
```

开发工作流：
```bash
# 启动基础设施
docker compose -f docker-compose.dev.yml up -d

# 后端开发
cd backend && uvicorn app.main:app --reload --port 8000

# 前端开发
cd frontend && pnpm dev
```

### 11.4 Makefile

```makefile
.PHONY: dev test deploy

dev:
	docker compose -f docker-compose.dev.yml up -d

dev-backend:
	cd backend && uvicorn app.main:app --reload --port 8000

dev-frontend:
	cd frontend && pnpm dev

test:
	cd backend && pytest -v

test-cov:
	cd backend && pytest --cov=app --cov-report=html

migrate:
	cd backend && alembic upgrade head

migrate-new:
	cd backend && alembic revision --autogenerate -m "$(MSG)"

deploy:
	docker compose up -d --build

lint:
	cd backend && ruff check . && ruff format --check .
	cd frontend && pnpm lint

clean:
	docker compose down -v
```

---

## 12. 非功能性需求

| 需求 | 指标 | 实现方式 |
|------|------|---------|
| 并发房间 | 支持 50+ 同时进行的房间 | Redis 状态分片，asyncio 非阻塞 |
| WebSocket 延迟 | 事件推送 < 100ms | Redis Pub/Sub 直推 |
| 断线恢复 | 120s 内重连恢复上下文 | Redis 状态缓存 + 重连协议 |
| API 响应时间 | P95 < 200ms | 连接池、异步 IO |
| 数据持久化 | 所有游戏事件可回放 | PostgreSQL game_events 表 |
| 安全 | API Key 认证，速率限制 | 中间件 + Redis 计数器 |

---

## 13. 关键设计决策 & 权衡

| 决策 | 选择 | 理由 | 替代方案 |
|------|------|------|---------|
| WebSocket vs SSE | WebSocket | Agent 需双向通信 | SSE 仅单向 |
| Redis Pub/Sub vs Kafka | Redis Pub/Sub | 轻量，延迟低，适合实时游戏 | Kafka 过重 |
| 内存状态 + Redis 同步 | 混合方案 | 性能 + 可恢复性 | 纯 Redis 状态 |
| 角色策略模式 | Strategy Pattern | 新角色易扩展 | if/else 链 |
| 前端状态管理 | Zustand | 比 Redux 轻量，适合 WS 场景 | Redux Toolkit |
| UUID 主键 | UUID v4 | 无序 ID 安全性好 | 自增 ID 有信息泄露风险 |
| CoT 透传 | 完整存储+选择性展示 | Agent 开发调试需要 | 不存储 CoT |