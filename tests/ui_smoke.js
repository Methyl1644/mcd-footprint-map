/* 「麦麦足迹地图」前端交互冒烟测试（jsdom）
   验证三件事：
   1) 默认只显示城市，订单区/时间轴都是空态引导
   2) 点击城市后才显示该城市的订单，且只显示该城市的
   3) 设置面板可填写并保存 Token，并给出成功反馈
*/
const fs = require("fs");
const { JSDOM, VirtualConsole } = require("jsdom");

const HTML = process.argv[2];
const MODE = process.argv[3] || "offline"; // offline(file://) | server(http://)
const html = fs.readFileSync(HTML, "utf8");

const calls = [];
// jsdom 不实现页面跳转，改用 jsdomError 捕获 location.reload() 的触发
const vc = new VirtualConsole();
vc.on("jsdomError", e => { if (/navigation/i.test(e.message)) calls.push({ path: "RELOAD" }); });
vc.on("error", () => {});
const dom = new JSDOM(html, {
  runScripts: "dangerously",
  virtualConsole: vc,
  url: MODE === "server" ? "http://127.0.0.1:8792/" : "file:///C:/tmp/footprint.html",
  pretendToBeVisual: true,
  beforeParse(window) {
    // jsdom 在 file:// 下没有 localStorage，补一个内存实现以便测通离线保存分支
    try { void window.localStorage; } catch (e) {
      const mem = {};
      Object.defineProperty(window, "localStorage", {
        configurable: true,
        value: {
          getItem: k => (k in mem ? mem[k] : null),
          setItem: (k, v) => { mem[k] = String(v); },
          removeItem: k => { delete mem[k]; },
        },
      });
      window.__memStore = mem;
    }
    window.fetch = async (path, opts) => {
      const body = opts && opts.body ? JSON.parse(opts.body) : {};
      calls.push({ path, method: (opts && opts.method) || "GET", body });
      if (path === "/api/state") {
        return { ok: true, status: 200, json: async () => ({ token_set: false, server: true }) };
      }
      if (path === "/api/token" && (opts && opts.method === "POST")) {
        return {
          ok: true, status: 200,
          json: async () => ({
            ok: true, token_saved: true, token_masked: "abcd****2345",
            source_label: "麦当劳 MCP（真实接口）", order_count: 10, lit_cities: 1,
          }),
        };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    };
    window.location.reload = () => { calls.push({ path: "RELOAD" }); };
  },
});

const { window } = dom;
const doc = window.document;
const $ = id => doc.getElementById(id);
const txt = id => ($(id) ? $(id).textContent.replace(/\s+/g, " ").trim() : "<missing>");

let fail = 0;
function check(name, cond, extra) {
  console.log((cond ? "  PASS  " : "  FAIL  ") + name + (extra ? "  | " + extra : ""));
  if (!cond) fail++;
}

setTimeout(() => {
  console.log("=== 模式：" + MODE + " ===");

  // ---- 1. 默认视图：只有城市 ----
  const rows = doc.querySelectorAll("#cityBox .city-row");
  check("默认渲染城市列表", rows.length > 0, rows.length + " 行");
  check("默认不渲染门店/订单明细", doc.querySelectorAll("#cityBox .store-row").length === 0);
  check("订单区为空态引导", /先选一座城市|订单按城市查看/.test($("dayDetail").textContent),
    txt("dayDetail").slice(0, 40));
  check("时间轴为空态引导", /先选一座城市/.test($("days").textContent), txt("days").slice(0, 30));
  check("筛选条默认隐藏", !$("filterBar").classList.contains("on"));
  check("订单区提示为未选择城市", txt("orderHint") === "未选择城市", txt("orderHint"));

  // ---- 2. 点击城市 ----
  const city = rows[0].getAttribute("data-city");
  rows[0].dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  const mems = doc.querySelectorAll("#dayDetail .memory");
  const dayRows = doc.querySelectorAll("#days .day");
  check("点击城市后订单区出现订单", mems.length > 0, city + " → " + mems.length + " 单");
  check("点击城市后时间轴出现日期", dayRows.length > 0, dayRows.length + " 天");
  check("筛选条出现", $("filterBar").classList.contains("on"), txt("filterText"));
  check("订单区提示切换为该城市", txt("orderHint").indexOf(city) === 0, txt("orderHint"));
  const stores = doc.querySelectorAll("#cityBox .store-row");
  check("城市详情显示门店列表", stores.length > 0, stores.length + " 家店");

  // 时间轴是日期索引：只显示「N 单」计数与深夜追问预览，不重复展示门店/菜品
  const dayTexts = [...doc.querySelectorAll("#days .day")].map(n => n.textContent);
  const dayHasCount = dayTexts.every(t => /\d+ 单/.test(t));
  check("时间轴只做日期索引（N 单）", dayHasCount, dayTexts[0].replace(/\s+/g, " ").slice(0, 40));
  const askRows = doc.querySelectorAll("#days .day .q");
  check("深夜日期在时间轴显示追问预览", askRows.length > 0, askRows.length + " 条预览");
  const detailAsks = doc.querySelectorAll("#dayDetail .ask");
  const oneAsk = [...askRows].find(n => n.textContent.length > 0);
  if (oneAsk) {
    oneAsk.closest(".day").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    check("点开深夜日期后详情出现追问", doc.querySelectorAll("#dayDetail .ask").length > 0,
      (doc.querySelector("#dayDetail .ask") || {}).textContent || "");
  }

  // ---- 3. 再点一次取消 ----
  const back = $("backBtn");
  check("有返回全部城市的入口", !!back);
  if (back) {
    back.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    check("返回后订单区回到空态", /先选一座城市|订单按城市查看/.test($("dayDetail").textContent));
    check("返回后城市列表恢复", doc.querySelectorAll("#cityBox .city-row").length > 0);
  }

  // ---- 4. 设置面板 ----
  $("btnSettings").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  check("弹窗打开", $("modal").classList.contains("on"));
  $("tokenInput").value = "my-secret-token-1234567890";
  $("btnSave").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));

  setTimeout(() => {
    const msg = $("tokenMsg");
    check("给出保存成功反馈", /保存成功|已保存|已暂存/.test(msg.textContent), msg.textContent.slice(0, 60));
    check("反馈样式为成功态", msg.className.indexOf("ok") >= 0, msg.className);
    if (MODE === "server") {
      const post = calls.find(c => c.path === "/api/token" && c.method === "POST");
      check("向服务端提交 Token", !!post && post.body.token === "my-secret-token-1234567890");
      check("提交后触发刷新/重载", calls.some(c => c.path === "RELOAD"));
      check("提示为保存成功文案", /✓/.test(msg.textContent), msg.textContent.slice(0, 40));
    } else {
      // file:// 下浏览器可能禁用 localStorage，此时必须给出可理解的提示而不是崩溃
      let stored = null;
      try { stored = window.localStorage.getItem("mcd_mcp_token"); } catch (e) { stored = "<unavailable>"; }
      check("离线模式暂存到本机", stored === "my-secret-token-1234567890", "localStorage=" + stored);
    }
    console.log(fail === 0 ? "\n>>> 全部通过" : `\n>>> ${fail} 项失败`);
    process.exit(fail === 0 ? 0 : 1);
  }, 1300);   // 需大于保存成功后的重载延时（900ms）
}, 500);
