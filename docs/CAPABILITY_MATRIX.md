# 麦当劳 MCP 能力清单与字段映射（实测版）

> 本文件所有字段名、返回结构均来自 **真实调用麦当劳 MCP Server 的实测结果**，未做任何推测性补充。
> 实测环境：`https://mcp.mcd.cn`，Streamable HTTP，`Authorization: Bearer <Token>`。
> 如与官方文档不一致，以本文件的实测记录为准，并在「能力缺口」一节给出降级方案。

## 1. 接入与鉴权

| 项 | 实测值 |
| --- | --- |
| 接入地址 | `https://mcp.mcd.cn`（路径探测：`/mcp`、`/sse` 均返回 404，根路径 `/` 为有效端点） |
| 传输协议 | Streamable HTTP（JSON-RPC 2.0） |
| 鉴权 | 请求头 `Authorization: Bearer <MCP_TOKEN>` |
| 限流 | 每个 Token 每分钟最多 600 次请求，超限返回 `429` |
| 握手流程 | `initialize` → 取响应头 `Mcp-Session-Id` → `notifications/initialized` → `tools/call` |
| 错误码 | `401` Token 无效/过期；`429` 触发限流；业务错误形如 `code=610303 订单号不存在！` |

## 2. 本 Skill 实际使用的 Tool

| Tool | 入参 | 实测返回关键字段 | 在本项目中的作用 |
| --- | --- | --- | --- |
| `order-list` | 无（**无分页参数**） | `data.list[]`：`orderId`、`orderType`、`createTime`、`beType`、`beCode`、`storeCode`、`storeName`、`orderStatus`、`orderProductList[]`（`productCode`/`productName`/`quantity`/`comboItemList[]`）、`realTotalAmount` | 主数据源：门店名、下单时间、订单内容 |
| `query-order` | `orderId`（必填，string） | `storeName`、**`storeAddress`**、`createTime`、`orderProductList[]`（`productName`/`productImage`/`quantity`/`price`/`comboItemList[{itemName,itemQuantity}]`）、`totalAmount`、`realTotalAmount`、`takeWay`、`orderStatus` | 补齐**门店地址**（`order-list` 不含该字段） |
| `query-nearby-stores` | `beType`(1=到店自提/5=得来速)、`searchType`(1=收藏/2=按位置)、`city`、`keyword` | `storeCode`、`storeName`、`address`、`distance`、`businessStatus`、`businessStartTime/EndTime`、`longitude`、`latitude`、`reservation`、`reservationTimeOptions[]` | 可选的城市反查（默认关闭） |
| `now-time-info` | 无 | `timestamp`、`datetime`、`formatted`、`date`、`year`、`month`、`day`、`dayOfWeek`、`timezone`、`offset`、`utc` | 对齐「今天」的时区口径（`GMT+08:00`） |
| `mall-order-list` | `lastId`、`size`(默认10) | 麦麦商城订单 | **未使用**：商城兑换订单不属于「吃麦当劳」的到店/外送消费，避免口径混淆 |

## 3. 字段映射表（MCP → 足迹记录）

| 足迹记录字段 | 来源 | 备注 |
| --- | --- | --- |
| `order_id` | `order-list.orderId` | 主键 |
| `created_at` / `date` / `time` | `order-list.createTime`（`YYYY-MM-DD HH:MM:SS`） | 解析为 datetime 后拆分 |
| `store_code` | `order-list.storeCode` | 用于人工纠偏表精确匹配 |
| `store_name` | `order-list.storeName` | 如「麦当劳南京广州路餐厅」 |
| `address` | **`query-order.storeAddress`** | `order-list` **不含**此字段 |
| `city` / `province` / `lon` / `lat` | **本地推断**（见第 4 节） | MCP 不直接提供 |
| `status` | `order-list.orderStatus` | 如「订单已完成」「订单已取消」 |
| `take_way` | `query-order.takeWay` | 如「堂食」 |
| `amount` | `realTotalAmount` | 单位：元 |
| `items[].name` | `orderProductList[].productName` | 如「巨无霸」 |
| `items[].subitems` | `comboItemList[]` | **字段名不一致**：`order-list` 用 `name`/`quantity`，`query-order` 用 `itemName`/`itemQuantity`，代码已兼容两者 |
| `is_late_night` | 由 `createTime` 推导（≥ 21:00） | 非 MCP 提供 |

## 4. 能力缺口与降级方案（重要）

| # | 缺口（实测结论） | 影响 | 降级方案 |
| --- | --- | --- | --- |
| 1 | `order-list` **不返回城市、地址、经纬度** | 无法直接定位 | 用 `query-order.storeAddress` 补齐地址；城市由门店名/地址推断 |
| 2 | `query-order` 对部分历史订单返回 `code=610303「订单号不存在！」` | 部分订单缺地址 | 容错跳过，退化为「仅用门店名推断城市」，并在日志中统计 `enrich_failed` |
| 3 | `query-nearby-stores` 的 `longitude` / `latitude` **实测恒为 `0.0`** | **MCP 无法提供真实坐标**，不能用于地图打点 | 地图坐标改用**地级行政中心坐标查表**（`data/city-centroids.json`，源自官方行政区划边界数据的 `center` 字段），并在文档与页面明确标注 |
| 4 | 无「按城市维度查询消费记录」的接口 | 城市聚合无法服务端完成 | 本地聚合（`aggregate.py`） |
| 5 | `order-list` 无分页参数 | 历史深度受服务端限制（实测返回 10 条） | 明确记录 `order_list_count`；支持 `--input` 导入更完整的历史 JSON |
| 6 | 港澳台及海外无 MCP 覆盖（服务限定中国大陆地区） | 无法点亮 | 明确排除，不计入统计；底图仍按国家标准绘制完整版图 |

## 5. 城市推断的多级降级链

| 级别 | 依据 | 置信度 | 说明 |
| --- | --- | --- | --- |
| L1 `override` | `data/city-overrides.json`（按 `storeCode` / 门店全名） | 1.00 | 人工纠偏，优先级最高 |
| L2 `store_name` | 门店名（剥去「麦当劳」后**锚定开头**匹配） | 0.90 | 麦当劳命名惯例「麦当劳\<城市\>\<商圈/路名\>餐厅」 |
| L2' `store_name` | 门店名全文最靠前匹配 | 0.75 | 兜底 |
| L3 `address` | 门店地址中匹配「\<城市名\>+市」 | 0.85 | **必须带「市」字**：否则「广州路」「中山路」「延安路」会被误判为广州市/中山市/延安市（已修复，见 `cities.py`） |
| L4 `mcp_probe` | `query-nearby-stores` 反查 | 0.70 | 默认关闭（`--probe-mcp`） |
| L5 `unknown` | 无法判定 | 0.00 | 计入 `unresolved`，不点亮，可人工纠偏 |

## 6. 统计口径

- 覆盖 **中国大陆地区**，粒度为**地级市**（含地区 / 自治州 / 盟 / 省直辖县级行政区），共 **367** 个统计单元。
- 北京、天津、上海、重庆四个直辖市各计为 **1 个**城市单元，不再细分市辖区。
- **港澳台及海外不计入**统计（麦当劳 MCP 服务面向中国大陆地区提供）；港澳台仅作为国家版图的组成部分绘于底图，不参与点亮。
- 覆盖率 = 已点亮城市数 / 367；省份覆盖率 = 已覆盖省级行政区数 / 31。
