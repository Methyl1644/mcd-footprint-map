# 交付自检、交付清单与运行说明

> 对照《麦当劳程序员节创意开发大赛活动规则》与活动 README 的提交规范逐项自检。

## 一、提交规范自检

| # | 规则要求 | 状态 | 本项目 |
| --- | --- | --- | --- |
| 1 | `README.md`（项目介绍、安装方法、使用示例、目标用户） | ✅ | `README.md`，四项齐全 |
| 2 | `CONTEST_DECLARATION.md`（文件名与内容均不可改动） | ✅ | 与官方文件逐字一致，未做任何修改 |
| 3 | `MCP_INTEGRATION.md`（使用的 MCP Server、Tool、调用流程、业务价值） | ✅ | `MCP_INTEGRATION.md` |
| 4 | `mcp-config.example.json`（脱敏配置，只允许环境变量占位符） | ✅ | 使用 `${MCD_MCP_TOKEN}`，无任何真实凭证 |
| 5 | `workbuddy.md`（WorkBuddy 专项奖励需提交） | ✅ | `workbuddy.md` |
| 6 | 源代码（项目主体代码或可运行内容） | ✅ | `src/mcd_footprint/` + `assets/viewer.html` |
| 7 | 项目真实使用麦当劳 MCP 能力 | ✅ | `order-list` / `query-order` / `now-time-info`（已用真实 Token 联调通过） |
| 8 | 仓库为 GitHub 公开仓库 | ⬜ | 待参赛者创建并设为 Public |
| 9 | 项目创建时间在 2025-12-25 ~ 2026-10-25 | ⬜ | 待参赛者创建仓库时满足 |
| 10 | 内容合规：无违法违规/敏感内容、无恶意代码、无违规外链 | ✅ | 无外部链接、无网络请求（含页面本身） |

### 信息安全自检（规则明确要求）

- [x] 仓库内**不含任何真实 Token / 密钥 / 密码 / 账号凭证**
  （已扫描确认；Token 仅通过环境变量 `MCD_MCP_TOKEN` 注入）
- [x] 配置文件仅使用环境变量占位符（`mcp-config.example.json`）
- [x] 不含他人个人信息（示例数据为合成数据，不含任何真实姓名、手机号、地址门牌之外的个人信息）

## 二、需求实现自检

| # | 需求 | 状态 | 实现位置 / 验证 |
| --- | --- | --- | --- |
| 1 | 地图范围限定中国大陆，地级市粒度点亮 | ✅ | `data/city-centroids.json`（367 个统计单元）；`aggregate.py` |
| 2 | 新增城市高亮提示 | ✅ | `aggregate.FootprintState` 状态差分 + 页面金色脉冲 + 顶部提示条 |
| 3 | 展示已点亮城市数、覆盖省份与占比 | ✅ | 顶部 5 张统计卡：城市数/367、覆盖率%、省份数/31、覆盖率% |
| 4 | 数据以 MCP 消费记录为准（门店名、地址、城市、下单时间、订单内容） | ✅ | `order-list` + `query-order`；`normalize.py` |
| 5 | 接口无法提供时用符合结构的 mock 数据并标注 | ✅ | `data/sample-orders.mock.json`，页面与 README 均显著标注 |
| 6 | 按日期时间轴回溯，打开即回忆「当天在哪里吃了什么」 | ✅ | 打开默认定位到今天（无记录则最近一次）；`narrative.build_timeline` |
| 7 | 展示门店、菜品与时间 | ✅ | 当日详情含 时间 / 门店名 / 地址 / 菜品（含套餐子项）/ 金额 |
| 8 | 深夜（≥21:00）追加一句轻松克制的追问，不臆造事实 | ✅ | `narrative.LATE_NIGHT_PROMPTS`，均为开放式问句，结果稳定可复现 |
| 9 | 地图与当日详情联动，点击城市或门店查看对应记录 | ✅ | 点城市 → 时间轴/当日详情/门店列表联动；点门店 → 再收窄 |

## 三、代码可运行性验证（实际执行记录）

```bash
# 环境：Python 3.13（仅标准库）
$ python -m mcd_footprint --source mock --out out/footprint.html --json-out out/footprint.json
[1/5] 取到 58 条原始订单（source=mock）
[2/5] 归一化 58 条；无法判定城市 0 条
[3/5] 点亮 20 座城市 / 367 (5.45%)，覆盖 16 个省份 (51.61%)，新增 20 座
[4/5] 生成时间轴 47 天；深夜记录 18 条
[5/5] 写出 JSON -> out/footprint.json
[5/5] 写出 HTML -> out/footprint.html（476 KB）

$ python -m unittest discover -s tests
Ran 12 tests ... OK

# 真实 MCP（已用真实 Token 联调）
$ MCD_MCP_TOKEN=*** python -m mcd_footprint --source mcp --out out/footprint-real.html
[1/5] 取到 10 条原始订单（source=mcp）
[2/5] 归一化 10 条；无法判定城市 0 条
[3/5] 点亮 1 座城市 / 367 (0.27%)，覆盖 1 个省份 (3.23%)
[5/5] 写出 HTML -> out/footprint-real.html（440 KB）
```

补充校验（均已通过）：

- 内联 JSON 可被 `JSON.parse` 正确解析（DATA / OUTLINE 两处）
- 页面 JS 语法编译通过（`new Function` 校验），关键 DOM 节点齐全
- 全部城市点位落在 viewBox 内（0 越界）
- 港澳台 `in_stats=false`，不参与统计

## 四、交付清单

```
mcd-footprint-map/
├── README.md                     ← 必需
├── CONTEST_DECLARATION.md        ← 必需（内容不可改动）
├── MCP_INTEGRATION.md            ← 必需
├── mcp-config.example.json       ← 必需（脱敏）
├── workbuddy.md                  ← WorkBuddy 专项奖励
├── SKILL.md                      ← Skill 入口
├── requirements.txt / .gitignore
├── src/mcd_footprint/            ← 源码（8 个模块）
├── assets/viewer.html            ← 页面模板
├── data/                         ← 地理数据 + 纠偏表 + 示例数据
├── tools/                        ← 数据构建脚本
├── tests/test_pipeline.py        ← 12 项验证
└── docs/
    ├── CAPABILITY_MATRIX.md      ← 能力清单与字段映射（实测）
    └── SELF_CHECK.md             ← 本文件
```

## 五、运行说明

```bash
# 1) 准备（Python 3.9+，无第三方依赖）
cd mcd-footprint-map

# 2) 最快体验（无需 Token）
python -m mcd_footprint --source mock --out out/footprint.html
#    打开 out/footprint.html

# 3) 真实数据
python -m mcd_footprint --save-token              # 交互式输入，或直接 --save-token 你的Token
python -m mcd_footprint --source mcp --out out/footprint.html --state out/state.json

# 4) 本地服务（页面内设置 Token 并即时生效）
python -m mcd_footprint --serve --port 8765

# 5) 定位链路体检
python tools/audit_geolocation.py --source mcp

# 6) 作为 Skill 使用：把 SKILL.md 放到 ~/.workbuddy/skills/mcd-footprint-map/SKILL.md
```

## 五·补、本轮改动的验证记录

| 验证项 | 方式 | 结果 |
| --- | --- | --- |
| 定位链路完整性（示例数据） | `python tools/audit_geolocation.py --source mock` | 58/58 = 100%，退出码 0 |
| 定位链路完整性（真实 MCP） | `python tools/audit_geolocation.py --source mcp` | 10/10 = 100%（门店名 70% / 人工纠偏 30%） |
| 默认只展示城市 | `node tests/ui_smoke.js out/footprint.html` | 城市列表 17 行；订单区/时间轴均为空态 |
| 点城市后才出订单 | 同上 | 南京市 → 11 天订单；时间轴门店全部属于该城市 |
| Token 保存（服务模式） | 接口 + 冒烟 | `token_saved:true` → `✓ 保存成功` → 自动重载 |
| Token 保存（错误 Token） | `POST /api/token` | `token_saved:true` + `ok:false` + `MCP HTTP 401`，保留上次数据 |
| Token 不入库 | 全仓扫描 | 产物与源码中均无明文 Token |
| Python 单测 | `python -m unittest discover -s tests` | 17 项 OK |
| 页面 JS | `new Function(script)` + jsdom 运行 | 语法通过，无控制台异常 |

## 六、已知边界

1. **港澳台及海外不计入统计**（MCP 服务面向中国大陆地区）。港澳台仅作为国家版图组成部分绘于底图（灰色），
   不点亮、不计数。
2. **坐标精度**：MCP 不提供真实经纬度（`query-nearby-stores` 的 `longitude/latitude` 实测恒为 `0.0`），
   城市点位采用**地级行政中心坐标**，因此点位代表"这座城市"，不代表具体门店位置。
3. **历史深度**：`order-list` 无分页参数，返回条数由服务端决定（实测 10 条）。
   如需更完整的历史，可导出后使用 `--source file`。
4. **深夜口径**：以 `createTime` 的小时 ≥ 21 判定，与下单所在城市的时区无关（统一按北京时间）。
5. **底图用途**：行政区域边界示意图，非导航地图；正式出版/商业用途请改用有审图号的标准地图数据。
