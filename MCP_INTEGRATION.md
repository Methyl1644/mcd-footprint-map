# MCP 集成说明

> 说明本项目实际使用的麦当劳 MCP Server、Tool、调用流程与业务价值。
> 所有接口字段均经真实调用验证，未使用的能力不列入。

## 1. 使用的 MCP Server

| 项 | 值 |
| --- | --- |
| 名称 | 麦当劳中国 MCP Server（`mcd-mcp`） |
| 接入地址 | `https://mcp.mcd.cn` |
| 传输协议 | Streamable HTTP |
| 鉴权 | `Authorization: Bearer ${MCD_MCP_TOKEN}`（Token 由环境变量或本机配置注入，仓库内不含任何真实凭证） |
| 配置示例 | 见 `mcp-config.example.json`（仅含环境变量占位符） |
| 限流 | 600 次/分钟/Token；客户端内置最小调用间隔与 429 退避重试 |

## 2. 使用的 Tool 与调用流程

```
┌──────────────────────────────────────────────────────────────┐
│ 1. now-time-info                                             │
│    → 取服务器当前日期（GMT+08:00），确定"今天"口径             │
├──────────────────────────────────────────────────────────────┤
│ 2. order-list                                                │
│    → 历史订单列表：storeName / createTime / orderProductList   │
├──────────────────────────────────────────────────────────────┤
│ 3. query-order（逐条，orderId 来自上一步）                     │
│    → 补齐 storeAddress（门店地址）；失败则容错降级              │
├──────────────────────────────────────────────────────────────┤
│ 4.（可选）query-nearby-stores                                 │
│    → 仅当门店名/地址都无法判定城市时反查（默认关闭）            │
├──────────────────────────────────────────────────────────────┤
│ 5. 本地处理：归一化 → 城市解析 → 地级市聚合 → 时间轴 → 渲染     │
└──────────────────────────────────────────────────────────────┘
```

对应的代码实现：

| 步骤 | 代码位置 |
| --- | --- |
| MCP 客户端（initialize / tools-call / SSE 解析 / 429 退避） | `src/mcd_footprint/mcp_client.py` |
| 取数与详情补齐 | `src/mcd_footprint/sources.py::load_from_mcp` |
| 归一化（兼容两套 comboItemList 字段名） | `src/mcd_footprint/normalize.py` |
| 城市解析（多级降级） | `src/mcd_footprint/cities.py` |
| 地级市聚合与统计 | `src/mcd_footprint/aggregate.py` |
| 时间轴 / 当日回忆 / 深夜追问 | `src/mcd_footprint/narrative.py` |
| 单文件 HTML 渲染 | `src/mcd_footprint/render.py` + `assets/viewer.html` |

## 3. 各 Tool 的业务价值

| Tool | 业务价值 |
| --- | --- |
| `order-list` | 提供「吃麦当劳」的**权威事实来源**：哪家门店、什么时间、点了什么。这是足迹地图唯一的真实数据源，避免了用户手工记账的成本与主观误差。 |
| `query-order` | 补齐 `storeAddress`，让「当日回忆」不仅能说出店名，还能说出具体地址，显著提升回忆的真实感与地理可信度。 |
| `now-time-info` | 对齐服务端时区，保证「今天你在哪里吃了麦当劳」的口径准确（避免本机时区/日期偏差）。 |
| `query-nearby-stores` | 可选兜底：当门店名与地址都无法判定城市时做反查，提高城市解析覆盖率。 |

## 4. MCP 能力缺口与降级（不编造能力）

以下限制均为**实测结论**，项目通过降级方案处理，而非假设接口具备相应能力：

1. **`order-list` 不含城市/地址/经纬度** → 由 `query-order.storeAddress` 补齐地址，城市走本地多级推断。
2. **部分历史订单 `query-order` 返回 `610303 订单号不存在！`** → 容错跳过，退化为门店名推断，运行日志输出 `enrich_failed` 计数。
3. **`query-nearby-stores` 的 `longitude`/`latitude` 实测恒为 `0.0`，无法用于地图打点** → 地图坐标改用**地级行政中心坐标查表**（`data/city-centroids.json`），并在页面与文档中明确标注该降级。
4. **`order-list` 无分页参数**，历史深度受服务端限制 → 记录 `order_list_count`，并支持 `--source file` 导入更完整的历史数据。
5. **港澳台及海外不在 MCP 服务范围**（服务面向中国大陆地区） → 明确不计入统计；底图仍完整绘制国家版图（含台湾省与九段线）。

## 5. 地图合规说明

- 底图为**行政区域边界示意图**，采用 Albers 等积圆锥投影，由本地数据离线渲染，
  **不接入任何在线地图瓦片服务**，无需任何地图 Key。
- 边界数据来源于阿里云 DataV.GeoAtlas 行政区划数据（源自民政部行政区划数据），
  仅用于绘制统计示意底图。
- 版图绘制遵循国家标准：完整绘制台湾省，并保留九段线要素。
- 「足迹点亮」统计口径仅覆盖中国大陆（不含港澳台及海外），与 MCP 服务范围一致。

> 若需用于正式出版或商业用途，建议改用自然资源部标准地图服务或天地图的审图号数据。

## 6. Token 的三种配置方式

| 方式 | 命令 | 适用场景 |
| --- | --- | --- |
| 页面设置（推荐） | `python -m mcd_footprint --serve` → 右上角「⚙ 设置 Token」 | 换账号、临时试用、不想碰命令行 |
| 命令行保存 | `python -m mcd_footprint --save-token`（不带参数会提示输入、不回显，或直接 `--save-token 你的Token`） | 一次保存，之后所有运行默认生效 |
| 环境变量 | `export MCD_MCP_TOKEN=你的Token` | CI / 脚本化运行 |

读取优先级：`--token` > 环境变量 `MCD_MCP_TOKEN` > 本机配置文件。

**为什么需要本地服务**：产物 HTML 是静态单文件，浏览器无法直连 `https://mcp.mcd.cn`
（跨域 + 需要 Bearer 头）。由本机服务代持 Token 代为调用 MCP，浏览器只与 `127.0.0.1` 通信。

安全边界：

- 仅监听 `127.0.0.1`；
- `GET /api/state` 只返回脱敏串（如 `abcd****2345`），任何接口都不回传明文；
- Token 落盘在 `~/.mcd-footprint-map/token.json`（权限 600），**不写入产物 HTML**，
  因此 `out/footprint.html` 可以放心分享给他人；
- 保存后立刻用新 Token 重新取数，失败时保留上一次的数据并提示原因（401 / 429）。

## 7. 复现调用

```bash
# 一次性生成静态页
python -m mcd_footprint --save-token 你的Token
python -m mcd_footprint --source mcp --out out/footprint.html

# 或本地服务（可在线换 Token）
python -m mcd_footprint --serve --port 8765
```

无 Token 时可使用内置示例数据（`--source mock`），其字段结构与真实 `order-list` 返回完全一致，
但内容为合成数据，仅用于演示。
