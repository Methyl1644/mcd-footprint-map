# WorkBuddy 开发上下文

> 本文件用于核验「麦麦足迹地图」项目是否使用腾讯 WorkBuddy 智能体开发（WorkBuddy 专项奖励）。

## 一、项目概况

- **项目名称**：麦麦足迹地图（mcd-footprint-map）
- **一句话简介**：用吃麦当劳的记录点亮走过的城市，丈量走遍全国的脚步。
- **活动**：麦当劳程序员节创意开发大赛
- **开发平台**：腾讯 WorkBuddy（Agent 模式）

## 二、使用 WorkBuddy 完成的工作

本项目在 WorkBuddy 中完成，主要环节如下：

1. **赛事与接口调研**
   - 读取活动仓库 `README.md`、`activityGuidelines.md`、`CONTEST_DECLARATION.md`，
     确认参赛要求、提交规范与评审/排名规则。
   - 读取 `M-China/mcd-mcp-server` 使用指南，列出全部 MCP Tool。
   - **在 WorkBuddy 中直接调用真实 MCP 工具**（`order-list`、`query-order`、
     `query-nearby-stores`、`now-time-info`）取得真实返回，据此确认字段名与结构，
     而非凭文档猜测。

2. **能力清单与降级设计**
   - 产出 `docs/CAPABILITY_MATRIX.md`：逐工具记录入参、返回字段、字段映射、
     能力缺口与降级方案。
   - 关键实测结论：`order-list` 不含城市/地址/经纬度；
     `query-nearby-stores` 的 `longitude`/`latitude` 恒为 `0.0`；
     部分历史订单 `query-order` 返回 `610303 订单号不存在！`。

3. **编码实现**
   - 由 WorkBuddy 编写 `src/mcd_footprint/` 全部模块（MCP 客户端、归一化、
     城市解析、聚合、叙事、渲染）与 `assets/viewer.html`。
   - 使用 WorkBuddy 内置 Shell 运行环境完成依赖安装外的全部构建与验证。

4. **真实数据联调**
   - 通过 WorkBuddy 配置的 `mcd-mcp` 连接器直连 `https://mcp.mcd.cn`，
     用真实订单跑通全链路（10 条订单，10/10 详情补齐成功，正确点亮南京市）。

5. **缺陷发现与修复（由真实数据驱动）**
   - 首版按「地址优先」匹配城市，导致「广州路/中山路/延安路」被误判为
     广州市/中山市/延安市。改为「门店名锚定开头优先 + 地址必须带『市』字」，
     并补充回归测试 `test_road_name_not_misread`。

6. **合规处理**
   - 加载地图合规能力，确认：**不接入任何在线地图瓦片服务**，
     底图由本地行政边界数据离线渲染（Albers 等积圆锥投影）；
     版图完整绘制台湾省并保留九段线；统计口径排除港澳台及海外。

7. **交付文档**
   - 生成 `README.md`、`MCP_INTEGRATION.md`、`CONTEST_DECLARATION.md`、
     `mcp-config.example.json`、`SKILL.md` 及本文件。

## 三、WorkBuddy 会话要点摘录

- 用户诉求：基于真实可用的 MCP 能力设计原创 Skill「麦麦足迹地图」，
  限定中国大陆地级市点亮、新增城市高亮、展示城市数与省份占比、
  按日期时间轴回忆当日消费、深夜记录追加克制追问、地图与详情联动。
- 明确约束：不得编造接口能力，缺失能力需给降级方案；代码可运行并附最小验证步骤；
  说明港澳台及海外不计入。
- 执行方式：按「能力梳理 → 目录结构 → 数据获取与聚合 → 地图联动 → 时间轴与深夜追问 →
  自检交付」六步逐步实现，每步产出可验证结果。

## 四、验证记录（在 WorkBuddy 中执行）

```
# 示例数据全链路
python -m mcd_footprint --source mock --out out/footprint.html --json-out out/footprint.json
# -> [1/5] 取到 58 条原始订单
# -> [2/5] 归一化 58 条；无法判定城市 0 条
# -> [3/5] 点亮 20 座城市 / 367 (5.45%)，覆盖 16 个省份 (51.61%)，新增 20 座
# -> [4/5] 生成时间轴 47 天；深夜记录 18 条
# -> [5/5] 写出 HTML -> out/footprint.html

# 真实 MCP 数据全链路
python -m mcd_footprint --source mcp --out out/footprint-real.html --state out/state-real.json
# -> [1/5] 取到 10 条原始订单（source=mcp）
# -> [2/5] 归一化 10 条；无法判定城市 0 条
# -> [3/5] 点亮 1 座城市 / 367 (0.27%)，覆盖 1 个省份 (3.23%)，新增 1 座
# -> 第二次运行（state 已存在）-> 新增 0 座（新增城市差分生效）

# 单元测试
python -m unittest discover -s tests -v
```

## 五、声明

- 本项目为参赛者独立开发的参赛作品，非麦当劳官方产品。
- 素材与代码均为原创；地理边界数据来源于公开行政区划数据，仅用于绘制统计示意图。
- 仓库中不含任何真实 Token、密钥或个人敏感信息。
