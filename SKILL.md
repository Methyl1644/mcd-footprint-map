---
name: mcd-footprint-map
description: 麦麦足迹地图。用麦当劳 MCP 的真实消费记录点亮走过的城市：按地级市粒度在中国大陆地图上点亮足迹，统计已点亮城市数与覆盖省份占比，高亮新点亮的城市；按日期时间轴回溯"当天在哪里吃了什么"，展示门店、地址、菜品与时间；对 21:00 之后的深夜记录追加一句轻松克制的回忆追问。当用户想回顾自己的麦当劳消费足迹、查看去过哪些城市、回忆某天吃了什么、生成足迹地图或年度回顾时使用。
---

# 麦麦足迹地图（mcd-footprint-map）

用吃麦当劳的记录点亮走过的城市，丈量走遍全国的脚步。

## 何时使用

- 「我吃过麦当劳的哪些城市？」「点亮我的麦麦足迹地图」
- 「某年某月某日我在哪里吃了麦当劳？」/「回忆一下那天吃了什么」
- 生成足迹地图、年度/月度回顾、城市覆盖率统计

## 前置条件

1. 已申请麦当劳 MCP Token，并在 WorkBuddy 中配置了 `mcd-mcp` 连接器
   （配置见 `mcp-config.example.json`，Token 通过环境变量注入）。
2. 项目依赖：Python 3.9+，仅用标准库（可选 `requests`）。

## 执行流程

### 第 1 步：取数（优先使用 MCP 工具）

优先通过 WorkBuddy 内置的 MCP 工具取数，并落盘为 JSON：

1. 调用 `order-list` → 得到历史订单列表
   （`orderId` / `storeName` / `createTime` / `orderProductList`）。
2. 对每条订单调用 `query-order` → 补齐 `storeAddress`（门店地址）。
   部分历史订单会返回 `610303 订单号不存在！`，属正常情况，跳过即可。
3. 调用 `now-time-info` → 取服务器当前日期，确定「今天」。

将结果存为 `orders.json`（结构与 `data/sample-orders.mock.json` 一致），再执行：

```bash
python -m mcd_footprint --source file --input orders.json --out out/footprint.html
```

也可以让脚本直连 MCP（需 `MCD_MCP_TOKEN`）：

```bash
python -m mcd_footprint --save-token                  # 交互式输入（不回显），保存到本机
python -m mcd_footprint --save-token 你的Token        # 或直接传入（一次保存，之后默认生效）
python -m mcd_footprint --source mcp --out out/footprint.html --state out/state.json
```

无 Token / 无网络时，用内置示例数据演示（**结构真实、内容为合成**）：

```bash
python -m mcd_footprint --source mock --out out/footprint.html
```

**优先推荐本地服务模式**：用户可在页面里直接填写自己的 Token 并立即生效。

```bash
python -m mcd_footprint --serve --port 8765
# 打开 http://127.0.0.1:8765 → 右上角「⚙ 设置 Token」
```

### 第 2 步：产出与展示

生成 `out/footprint.html`（单文件、离线可用），用 `present_files` 打开给用户查看。

默认视图只展示城市；点开城市后才展示这座城市的订单、门店与日期。

## 硬约束（不得违反）

1. **统计范围仅限中国大陆**，粒度为地级市；**港澳台及海外一律不计入**统计。
   港澳台仅作为国家版图的组成部分绘于底图，不点亮、不计数。
2. **不臆造事实**：只展示 MCP 真实返回的门店名、地址、下单时间、订单内容。
   「深夜追问」只是**开放式问句**（如「那天那么晚在想什么呢？」），
   不得替用户编造原因、心情、同行人等任何未记录的信息。
3. **不编造 MCP 能力**：`order-list` 无城市/地址/坐标字段；
   `query-nearby-stores` 的经纬度实测恒为 `0.0`，故坐标取地级行政中心查表。
   缺失能力一律走降级方案并在文档中标注。
4. 使用 mock 数据时，必须在输出中明确标注「数据为合成示例，非真实消费记录」。

## 参数速查

| 参数 | 说明 |
| --- | --- |
| `--serve` | 启动本地服务（可在页面里设置 Token 并刷新数据） |
| `--save-token [TOKEN]` | 把 Token 保存到本机，之后默认生效；不带参数则交互式输入（不回显） |
| `--show-token` / `--clear-token` | 查看（脱敏）/ 清除本机 Token |
| `--source mcp\|file\|mock\|auto` | 数据来源，默认 `auto`（有 Token 走 MCP，否则示例数据） |
| `--input` | `file` 模式的输入 JSON |
| `--state PATH` | 已知城市状态文件，用于识别「新点亮」城市 |
| `--new-city-days N` | 无历史状态时，N 天内首次点亮视为新增（默认 30） |
| `--no-enrich` | 跳过 `query-order` 补齐（更快，但会缺门店地址） |
| `--probe-mcp` | 门店名/地址都判不出城市时，用 `query-nearby-stores` 反查 |
| `--json-out PATH` | 同时导出聚合 JSON，便于二次加工 |

## 排错

- `缺少 MCP Token` → 用 `--save-token` 保存，或设置环境变量 `MCD_MCP_TOKEN`。
- 页面里保存后没变化 → 确认是通过 `python -m mcd_footprint --serve` 打开的；
  双击打开的静态 HTML 无法直连 MCP。
- `MCP HTTP 401` → Token 无效或过期，重新申请。
- `MCP HTTP 429` → 触发 600 次/分钟限流，客户端已自动退避重试，仍失败请稍后再试。
- 城市判定错误 → 在 `data/city-overrides.json` 中按 `storeCode` 或门店全名人工纠偏。
- 无法判定城市的记录 → 会写入 JSON 的 `unresolved` 字段，不计入点亮。
