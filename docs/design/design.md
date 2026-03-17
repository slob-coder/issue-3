# 技术设计文档：在线狼人杀平台

> 项目：issue-3  
> 版本：v2.0  
> 日期：2026-03-18  
> 状态：细化设计  

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

**依赖注入 (DI)**：所有服务通过 FastAPI `Depends()` 注入，在 `app/dependencies.py` 集中管理工厂函数。

**事件驱动架构 (EDA)**：游戏状态变更通过 `GameEvent` 发布到 `EventBus`。WebSocket Hub、回放服务各自独立消费。

**策略模式 (Strategy)**：每个角色实现 `RoleStrategy` 接口，引擎通过 `RoleRegistry` 查找。新增角色只需添加策略类 + YAML 配置。

**状态模式 (State)**：每个阶段实现 `PhaseHandler` 接口，FSM 委托当前阶段 handler 处理行动、超时、完成判定。

---

## 3. 数据模型

### 3.1 PostgreSQL Schema

```sql
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

CREATE TABLE agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    api_key VARCHAR(64) UNIQUE NOT NULL,
    owner VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

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

### 3.2 SQLAlchemy 模型概要

每个表对应一个 SQLAlchemy 2.0 Mapped 模型文件：

- `app/models/room.py` — Room 模型，含 `players` 和 `events` relationship
- `app/models/agent.py` — Agent 模型
- `app/models/player.py` — Player 模型，含 `room` relationship
- `app/models/game_event.py` — GameEvent 模型

### 3.3 Pydantic Schemas 概要

- `app/schemas/room.py` — `RoomConfig`(含 model_validator 校验角色总数)、`RoomCreate`、`RoomResponse`、`RoomListResponse`
- `app/schemas/agent.py` — `AgentCreate`、`AgentResponse`
- `app/schemas/action.py` — `NightAction`、`SpeechAction`、`VoteAction`、`ActionSubmit`（Union discriminator）
- `app/schemas/event.py` — `GameEventSchema`

### 3.4 Redis 数据结构

| Key | 类型 | 说明 |
|-----|------|------|
| `room:{id}:state` | Hash | phase, round, alive_seats(JSON), current_speaker_seat, night_kill_target, night_actions_received(JSON) |
| `room:{id}:connections` | Hash | {agent_id}: connected/disconnected, {agent_id}:last_seen |
| `room:timeouts` | Sorted Set | member=`{room_id}:{player_id}:{action}`, score=expiry_epoch |
| `room:{id}:werewolf_votes` | List | 狼人击杀投票临时记录 |
| `channel:room:{id}:events` | Pub/Sub | 观战者广播频道 |
| `channel:room:{id}:agent:{aid}` | Pub/Sub | Agent 私有频道 |

---

## 4. 核心模块设计

### 4.1 游戏引擎 (GameEngine)

#### 阶段状态机流转

```
[WAITING] ──(满员)──► [NIGHT] ──(行动完成)──► [RESULT] ──► [CHECK_WIN]
                        ▲                                       │
                        │                                  (无胜者)
                        │                                       ▼
                   [CHECK_WIN] ◄── [EXECUTION] ◄── [DAY_VOTE] ◄── [DAY_SPEECH]
                        │
                   (有胜者) ──► [FINISHED]
```

#### PhaseHandler 接口

每个阶段实现以下方法：

```python
class PhaseHandler(ABC):
    async def enter(self, room_id, round_num) -> None     # 进入阶段：推送事件、设超时
    async def handle_action(self, room_id, player_id, action) -> None  # 处理行动
    async def on_timeout(self, room_id, player_id) -> None  # 超时处理
    async def check_complete(self, room_id) -> bool        # 完成判定
    async def exit(self, room_id) -> Optional[str]         # 返回下一阶段
```

#### 阶段处理器细节

**NightPhaseHandler** (`app/engine/phases/night.py`):
- `enter`: 向各角色推送各自的 action_type（werewolf→kill, seer→investigate, witch→heal_or_poison），设置超时，村民自动跳过
- `handle_action`: 校验行动合法性 → 执行角色策略 → 记录事件 → 向观战者推送（含真实信息）→ check_complete
- 狼人：记录击杀目标到 Redis `night_kill_target`
- 预言家：查验结果仅推送给预言家私有频道
- 女巫：使用解药时清除 `night_kill_target`

**ResultPhaseHandler** (`app/engine/phases/result.py`):
- `enter`: 读取 `night_kill_target` → 更新 Player 死亡状态 → 猎人被杀触发射杀选择 → 广播结果 → 自动 transition 到 CHECK_WIN

**DaySpeechPhaseHandler** (`app/engine/phases/day_speech.py`):
- `enter`: 按座位号确定发言顺序 → 向第一个发言者推送事件 → 设超时
- `handle_action`: 校验轮到该玩家 → 记录发言 → 广播 → 推进到下一发言者，全部完成转 DAY_VOTE
- `on_timeout`: 记录"沉默"→ 推进下一位

**DayVotePhaseHandler** (`app/engine/phases/day_vote.py`):
- `enter`: 向所有存活 Agent 推送投票事件 → 设超时
- `handle_action`: 记录投票 → check_complete
- `check_complete`: 全部完成 → 统计票数 → transition 到 EXECUTION

**ExecutionPhaseHandler** (`app/engine/phases/execution.py`):
- `enter`: 统计投票结果 → 最高票处决（平票无人被处决） → 猎人被处决触发技能 → 广播 → transition 到 CHECK_WIN

**CheckWinPhaseHandler** (`app/engine/phases/check_win.py`):
- `enter`: 狼人全灭→好人胜；狼人≥好人→狼人胜；否则下一轮 NIGHT

#### GameEngine 核心类

```python
# app/engine/game_engine.py
class GameEngine:
    def __init__(self, db, redis, event_bus):
        self.phase_handlers = {
            "night": NightPhaseHandler(self),
            "result": ResultPhaseHandler(self),
            "day_speech": DaySpeechPhaseHandler(self),
            "day_vote": DayVotePhaseHandler(self),
            "execution": ExecutionPhaseHandler(self),
            "check_win": CheckWinPhaseHandler(self),
        }
    
    async def start_game(self, room_id): ...       # 分配角色 → 推送 game.start → transition("night")
    async def transition_to(self, phase, **kw): ... # 更新 Redis → 调用 handler.enter()
    async def handle_action(self, room_id, player_id, action): ... # 委托给当前 handler
    async def end_game(self, room_id, winner): ...  # 推送 game.end → 清理 Redis → 更新 Room
```

### 4.2 角色系统

#### RoleStrategy 接口

```python
class RoleStrategy(ABC):
    role_id: str
    role_name: str
    faction: str  # "werewolf" | "villager"
    night_action_priority: int
    
    def get_night_action_type(self) -> Optional[str]: ...
    def get_available_targets(self, player, alive_players) -> list[int]: ...
    async def execute_night_action(self, player, action, game_state) -> ActionResult: ...
    def validate_action(self, action, player, game_state) -> bool: ...
```

#### 具体角色

| 角色 | 文件 | action_type | 夜间逻辑 | 被动技能 |
|------|------|-------------|---------|---------|
| Werewolf | `roles/werewolf.py` | kill | 选择目标击杀，多狼取多数票 | 无 |
| Seer | `roles/seer.py` | investigate | 查验目标阵营，结果私有推送 | 无 |
| Witch | `roles/witch.py` | heal_or_poison | 知道被杀目标，可解药或毒药（各1次） | 无 |
| Hunter | `roles/hunter.py` | 无（被动） | 无主动行动 | 死亡时选择射杀目标 |
| Villager | `roles/villager.py` | 无 | 无夜间行动 | 无 |

#### RoleRegistry

`app/engine/roles/registry.py` — 从 `roles_config/*.yaml` 加载角色定义，注册对应 Strategy。

角色配置 YAML 示例 (`roles_config/seer.yaml`):
```yaml
id: seer
name: 预言家
faction: villager
night_action:
  type: investigate
  target_count: 1
  target_filter: alive_except_self
  result_type: role_reveal
priority: 2
```

### 4.3 事件总线 (EventBus)

`app/services/event_bus.py`

```python
class EventBus:
    async def publish_to_agent(self, room_id, agent_id, event): ...    # 私有频道
    async def publish_to_spectators(self, room_id, event): ...         # 观战频道
    async def publish_public(self, room_id, event, agent_ids): ...     # 全部
    async def persist_event(self, db, event, round_num, phase, ...): ... # 持久化
```

### 4.4 房间服务 (RoomService)

`app/services/room_service.py`

- `create_room(data)` → 创建房间 + 初始化 Redis 状态
- `join_room(room_id, agent_id)` → 加入房间 + 满员触发 `GameEngine.start_game()`
- `list_rooms(status, limit, offset)` → 分页列表
- `get_room_state(room_id, requester_agent_id)` → 按权限过滤状态（Agent 只见自己角色，观战者见全部）

### 4.5 Agent 调度器 (AgentScheduler)

`app/services/agent_scheduler.py`

- `request_action(room_id, player_id, action_type, timeout)` → 注册 Redis 超时
- `cancel_timeout(room_id, player_id, action_type)` → 取消超时
- `run_timeout_checker()` → asyncio 后台任务，每秒扫描过期项
- `track_connection(room_id, agent_id, connected)` → 连接状态追踪

### 4.6 WebSocket Hub

`app/ws/hub.py` — ConnectionManager 管理所有连接

`app/ws/agent_handler.py`:
- 认证 API Key → 连接管理 → 订阅 Redis 私有频道
- 并行任务：Redis→WS（事件推送）、WS→Engine（行动接收）
- 断线处理：通知 scheduler、支持重连恢复上下文

`app/ws/spectator_handler.py`:
- 订阅房间公共频道 → 转发所有事件给观战者

### 4.7 行动校验器 (ActionValidator)

`app/engine/action_validator.py`

校验链：
1. 玩家必须存活
2. 行动类型与当前阶段匹配（night→night_action, day_speech→speech, day_vote→vote）
3. 阶段特定校验（夜间目标合法性、发言字数限制、投票目标存活性）

### 4.8 回放服务 (ReplayService)

`app/services/replay_service.py`

- `get_full_replay(room_id)` → 从 game_events 表聚合完整回放
- `get_round_replay(room_id, round_num)` → 指定回合事件

### 4.9 认证与安全

`app/middleware/auth.py`:
- API Key 从 `X-API-Key` header 或 `api_key` query param 提取
- 校验 Agent 存在且 is_active

`app/middleware/rate_limit.py`:
- Agent：100 req/min per API Key
- WebSocket：50 msg/min per connection
- 行动提交：每阶段每 Agent 仅一次

---

## 5. API 设计

### 5.1 REST API

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/api/v1/rooms` | 创建房间 | 可选 |
| GET | `/api/v1/rooms` | 列出房间（?status&limit&offset） | 无 |
| GET | `/api/v1/rooms/{room_id}` | 房间详情 | 无 |
| POST | `/api/v1/rooms/{room_id}/join` | Agent 加入 | API Key |
| GET | `/api/v1/rooms/{room_id}/state` | 房间状态 | 可选 API Key |
| POST | `/api/v1/rooms/{room_id}/actions` | 提交行动 | API Key |
| GET | `/api/v1/rooms/{room_id}/history` | 公开历史 | 无 |
| POST | `/api/v1/agents` | 注册 Agent | 无 |
| GET | `/api/v1/agents/{agent_id}` | Agent 信息 | 无 |
| GET | `/api/v1/rooms/{room_id}/replay` | 完整回放 | 无 |
| GET | `/api/v1/rooms/{room_id}/replay/rounds/{n}` | 回合回放 | 无 |
| GET | `/health` | 健康检查 | 无 |

### 5.2 WebSocket

| 端点 | 说明 |
|------|------|
| `ws://.../ws/agent/{room_id}?api_key=xxx` | Agent 实时通道 |
| `ws://.../ws/spectate/{room_id}` | 观战通道 |

### 5.3 事件消息格式

**服务端 → Agent**:
- `game.start` — 角色分配、游戏配置
- `phase.night` — 夜间行动请求（含 action_type、available_targets、timeout）
- `phase.day.speech` — 发言轮次（含 previous_speeches、context）
- `phase.day.vote` — 投票请求（含候选人列表）
- `phase.result` — 阶段结算（死亡信息）
- `game.end` — 游戏结束（全部角色揭示）

**Agent → 服务端**:
- `night_action` — {action_type, target_seat, chain_of_thought?}
- `speech` — {content, chain_of_thought?}
- `vote` — {target_seat, chain_of_thought?}

---

## 6. 前端设计

### 6.1 路由

| 路由 | 页面 | 说明 |
|------|------|------|
| `/` | Home | 首页/房间大厅 |
| `/rooms` | RoomList | 房间列表，支持状态筛选 |
| `/rooms/create` | CreateRoom | 创建房间表单 |
| `/rooms/:id/spectate` | Spectate | 上帝视角观战 |
| `/rooms/:id/replay` | Replay | 历史回放 |
| `/docs` | Docs | 嵌入 Swagger UI |

### 6.2 观战界面布局

```
┌─────────────────────────────────────────────────────────┐
│  🐺 房间名  │  回合 3  │  阶段: 白天发言  │  ⏱ 45s      │
├──────────────────────┬──────────────────────────────────┤
│                      │                                  │
│   [座位环形布局]      │   [发言/事件流]                   │
│    显示角色、存活、    │    实时发言 + CoT 折叠展示         │
│    当前行动状态        │                                  │
│                      │                                  │
├──────────────────────┴──────────────────────────────────┤
│  [统计面板] 投票流向图 │ 身份猜测热力图 │ 存活追踪          │
└─────────────────────────────────────────────────────────┘
```

### 6.3 核心组件

| 组件 | 文件 | 说明 |
|------|------|------|
| SeatCircle | `components/SeatCircle.tsx` | 环形座位布局，显示角色/存活/发言中状态 |
| EventStream | `components/EventStream.tsx` | 实时事件流，发言+CoT 折叠 |
| PhaseIndicator | `components/PhaseIndicator.tsx` | 阶段指示器+倒计时 |
| VoteFlowChart | `components/VoteFlowChart.tsx` | D3.js 投票流向 Sankey 图 |
| IdentityHeatmap | `components/IdentityHeatmap.tsx` | D3.js 身份猜测热力图 |
| StatsPanel | `components/StatsPanel.tsx` | 存活追踪、统计 |
| ReplayTimeline | `components/ReplayTimeline.tsx` | 回放时间轴控制 |

### 6.4 状态管理

`stores/gameStore.ts` — Zustand store:
```typescript
interface GameState {
  room: Room | null;
  phase: string;
  round: number;
  players: Player[];
  events: GameEvent[];
  speeches: Speech[];
  votes: Vote[];
  // actions
  connect: (roomId: string) => void;
  handleEvent: (event: GameEvent) => void;
}
```

### 6.5 WebSocket Hook

`hooks/useWebSocket.ts` — 自动重连、心跳、事件分发到 store
`hooks/useGameState.ts` — 从 store 派生的计算状态

---

## 7. Agent SDK 设计

### 7.1 Python SDK (`sdk/python/`)

```python
# 使用方式
from werewolf_sdk import WerewolfAgent, GameContext, Action

class MyAgent(WerewolfAgent):
    async def on_game_start(self, ctx: GameContext): ...
    async def on_night_action(self, ctx: GameContext) -> Action: ...
    async def on_speech(self, ctx: GameContext) -> Action: ...
    async def on_vote(self, ctx: GameContext) -> Action: ...

agent = MyAgent(api_key="xxx", server_url="ws://localhost:8000")
agent.join_room("room-id")
agent.run()
```

模块结构:
- `werewolf_sdk/agent.py` — WerewolfAgent 基类（生命周期回调）
- `werewolf_sdk/client.py` — WebSocket + REST 客户端封装
- `werewolf_sdk/models.py` — GameContext, Action, Player 等数据模型
- `werewolf_sdk/mock_server.py` — Mock 测试服务器（沙箱调试）

### 7.2 TypeScript SDK (`sdk/typescript/`)

```typescript
import { WerewolfAgent, GameContext, Action } from 'werewolf-sdk';

class MyAgent extends WerewolfAgent {
  async onNightAction(ctx: GameContext): Promise<Action> { ... }
  async onSpeech(ctx: GameContext): Promise<Action> { ... }
  async onVote(ctx: GameContext): Promise<Action> { ... }
}
```

### 7.3 示例 Agent

- `examples/random_agent.py` — 随机决策 Agent（测试基准）
- `examples/llm_agent.py` — Claude/GPT 驱动的 Agent（含 prompt 模板、CoT 输出）

---

## 8. 安全设计

### 8.1 信息隔离

- WebSocket 频道隔离：每个 Agent 独立 Redis Pub/Sub 频道
- REST API 权限过滤：`/state` 按 API Key 过滤返回数据
- Agent 间不可获取彼此私有信息

### 8.2 认证

- API Key 认证（`X-API-Key` header 或 query param）
- Agent 注册时生成 64 字符随机 key

### 8.3 速率限制

- REST: 100 req/min per API Key
- WebSocket: 50 msg/min per connection
- 行动提交: 每阶段每 Agent 仅一次

### 8.4 发言审查（可选）

- 基础：正则匹配禁止关键词
- 高级：LLM 审查是否泄露私有信息

---

## 9. 部署方案

### 9.1 Docker Compose

```yaml
services:
  backend:
    build: ./backend
    ports: ["8000:8000"]
    environment:
      DATABASE_URL: postgresql+asyncpg://werewolf:werewolf@db:5432/werewolf
      REDIS_URL: redis://redis:6379/0
    depends_on: [db, redis]
  frontend:
    build: ./frontend
    ports: ["3000:3000"]
    environment:
      VITE_API_URL: http://localhost:8000
      VITE_WS_URL: ws://localhost:8000
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: werewolf
      POSTGRES_PASSWORD: werewolf
      POSTGRES_DB: werewolf
    volumes: [pgdata:/var/lib/postgresql/data]
  redis:
    image: redis:7-alpine
volumes:
  pgdata:
```

### 9.2 项目目录结构

```
issue-3/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                  # FastAPI 入口
│   │   ├── config.py                # Settings (pydantic-settings)
│   │   ├── dependencies.py          # DI 工厂函数
│   │   ├── exceptions.py            # 自定义异常 + handler
│   │   ├── models/                  # SQLAlchemy 模型
│   │   │   ├── __init__.py
│   │   │   ├── base.py              # Base, 公共 mixin
│   │   │   ├── room.py
│   │   │   ├── agent.py
│   │   │   ├── player.py
│   │   │   └── game_event.py
│   │   ├── schemas/                 # Pydantic schemas
│   │   │   ├── __init__.py
│   │   │   ├── room.py
│   │   │   ├── agent.py
│   │   │   ├── action.py
│   │   │   └── event.py
│   │   ├── api/                     # REST 路由
│   │   │   ├── __init__.py
│   │   │   ├── router.py            # 总路由注册
│   │   │   ├── rooms.py
│   │   │   ├── agents.py
│   │   │   ├── actions.py
│   │   │   └── replay.py
│   │   ├── ws/                      # WebSocket
│   │   │   ├── __init__.py
│   │   │   ├── hub.py               # ConnectionManager
│   │   │   ├── agent_handler.py
│   │   │   └── spectator_handler.py
│   │   ├── engine/                  # 游戏引擎
│   │   │   ├── __init__.py
│   │   │   ├── game_engine.py       # 主引擎
│   │   │   ├── action_validator.py  # 行动校验
│   │   │   ├── phases/              # 阶段处理器
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py          # PhaseHandler ABC
│   │   │   │   ├── night.py
│   │   │   │   ├── result.py
│   │   │   │   ├── day_speech.py
│   │   │   │   ├── day_vote.py
│   │   │   │   ├── execution.py
│   │   │   │   └── check_win.py
│   │   │   └── roles/               # 角色策略
│   │   │       ├── __init__.py
│   │   │       ├── base.py          # RoleStrategy ABC
│   │   │       ├── registry.py      # RoleRegistry
│   │   │       ├── werewolf.py
│   │   │       ├── seer.py
│   │   │       ├── witch.py
│   │   │       ├── hunter.py
│   │   │       └── villager.py
│   │   ├── services/                # 业务服务
│   │   │   ├── __init__.py
│   │   │   ├── room_service.py
│   │   │   ├── event_bus.py
│   │   │   ├── agent_scheduler.py
│   │   │   └── replay_service.py
│   │   ├── middleware/              # 中间件
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   └── rate_limit.py
│   │   └── db/                      # 数据库
│   │       ├── __init__.py
│   │       ├── session.py           # async engine + session
│   │       └── migrations/          # Alembic
│   ├── roles_config/                # 角色 YAML 配置
│   │   ├── werewolf.yaml
│   │   ├── seer.yaml
│   │   ├── witch.yaml
│   │   ├── hunter.yaml
│   │   └── villager.yaml
│   ├── tests/
│   │   ├── conftest.py              # pytest fixtures
│   │   ├── test_engine/
│   │   │   ├── test_phase_fsm.py
│   │   │   ├── test_roles.py
│   │   │   └── test_win_checker.py
│   │   ├── test_api/
│   │   │   ├── test_rooms.py
│   │   │   └── test_agents.py
│   │   └── test_ws/
│   │       └── test_connections.py
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
│   │   ├── lib/
│   │   │   └── api.ts               # REST API 客户端
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
│   │   │   ├── agent.py
│   │   │   ├── client.py
│   │   │   ├── models.py
│   │   │   └── mock_server.py
│   │   ├── examples/
│   │   │   ├── random_agent.py
│   │   │   └── llm_agent.py
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
│   ├── openapi.yaml
│   ├── agent-guide.md
│   └── deployment.md
├── docker-compose.yml
├── README.md
└── LICENSE
```

---

## 10. 非功能需求

| 指标 | 目标 |
|------|------|
| WebSocket 端到端延迟 | < 500ms |
| REST API p95 | < 200ms |
| 并发房间 | ≥ 50 |
| 单房间观战者 | ≥ 100 |
| Agent 重连恢复 | < 5s |

可观测性：structlog 结构化日志、`/health` `/ready` 端点。

---

## 11. 开发阶段

| 阶段 | 范围 | 优先级 |
|------|------|--------|
| P0 | 项目脚手架、数据模型、Redis 集成、游戏引擎 FSM、角色系统、房间服务 | 最高 |
| P1 | Agent 调度器、认证中间件、REST API、WebSocket Hub、断线重连 | 高 |
| P2 | 前端脚手架、房间大厅、观战界面、统计面板 | 高 |
| P3 | 回放系统、Agent SDK (Python/TS) | 中 |
| P4 | 示例 Agent、OpenAPI 文档、部署指南 | 中 |
| P5 | 集成测试、Docker 部署验证 | 低 |
