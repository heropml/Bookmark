const SKINS = [
  { id: "auto", name: "自动" },
  { id: "aurora", name: "极光" },
  { id: "cyber", name: "赛博" },
  { id: "ember", name: "余烬" },
  { id: "abyss", name: "深海" },
  { id: "nebula", name: "星海" },
  { id: "prism", name: "幻彩" },
  { id: "obsidian", name: "墨金" },
  { id: "paper", name: "宣纸" },
  { id: "snow", name: "雪" },
  { id: "sakura", name: "樱" },
  { id: "celadon", name: "瓷" },
  { id: "shuimo", name: "水墨" },
  { id: "daiqing", name: "黛青" },
  { id: "zhusha", name: "朱砂" },
  { id: "yemo", name: "夜墨" }
];
const ICONS = [
  { id: "logo", name: "原始" },
  { id: "letter", name: "字母" },
  { id: "glass", name: "玻璃" },
  { id: "neon", name: "霓虹" },
  { id: "gem", name: "晶体" },
  { id: "holo", name: "全息" },
  { id: "mono", name: "单色" },
  { id: "pixel", name: "像素" },
  { id: "outline", name: "描边" },
  { id: "halo", name: "光晕" },
  { id: "frame", name: "边框" },
  { id: "badge", name: "徽章" },
  { id: "ink", name: "墨迹" },
  { id: "grain", name: "颗粒" },
  { id: "mirror", name: "镜面" },
  { id: "circuit", name: "电路" }
];
const FX = [
  { id: "on", name: "开" },
  { id: "off", name: "关" }
];
const LAYOUTS = [
  { id: "classic", name: "标准" },
  { id: "compact", name: "紧凑" },
  { id: "list", name: "列表" },
  { id: "icons", name: "宫格" },
  { id: "board", name: "分组看板" },
  { id: "tree", name: "目录树" },
  { id: "tabs", name: "顶部标签" },
  { id: "start", name: "居中起始页" },
  { id: "accordion", name: "分类折叠" }
];
const MOTIONS = [
  { id: "float", name: "悬浮" },
  { id: "pulse", name: "呼吸" },
  { id: "sweep", name: "流光" },
  { id: "sway", name: "摇摆" },
  { id: "bounce", name: "弹跳" },
  { id: "spin", name: "旋转" },
  { id: "ripple", name: "涟漪" },
  { id: "flip", name: "翻转" },
  { id: "shake", name: "震颤" },
  { id: "zoom", name: "聚焦" },
  { id: "slide", name: "滑行" },
  { id: "twist", name: "扭转" },
  { id: "blink", name: "闪现" },
  { id: "drift", name: "漂移" },
  { id: "heartbeat", name: "心跳" },
  { id: "still", name: "静止" }
];
const TRAILS = [
  { id: "stardust", name: "星尘" },
  { id: "comet", name: "彗星" },
  { id: "bubble", name: "气泡" },
  { id: "petal", name: "花瓣" },
  { id: "firefly", name: "萤火" },
  { id: "rainbow", name: "彩虹" },
  { id: "sparkle", name: "星芒" },
  { id: "sparks", name: "火花" },
  { id: "ribbon", name: "丝带" },
  { id: "notes", name: "音符" },
  { id: "pixels", name: "像素" },
  { id: "crystal", name: "冰晶" },
  { id: "ink", name: "墨迹" },
  { id: "hearts", name: "心愿" },
  { id: "smoke", name: "云烟" },
  { id: "none", name: "关闭" }
];
const SKYS = [
  { id: "auto", name: "跟随天气" },
  { id: "rain", name: "细雨" },
  { id: "snow", name: "落雪" },
  { id: "stars", name: "星空" },
  { id: "meteor", name: "流星" },
  { id: "fireflies", name: "流萤" },
  { id: "blossom", name: "落樱" },
  { id: "aurora", name: "极光" },
  { id: "bubbles", name: "泡泡" },
  { id: "fireworks", name: "烟火" },
  { id: "matrix", name: "数字雨" },
  { id: "nebula", name: "星云" },
  { id: "ripples", name: "波纹" },
  { id: "beams", name: "光束" },
  { id: "confetti", name: "彩纸" },
  { id: "none", name: "关闭" }
];
const PAGE = 36;
let savedFolder = null;
try { savedFolder = localStorage.getItem("bm-folder"); } catch (e) {}
const state = { folder: savedFolder === null ? "常用" : savedFolder, q: "", shown: PAGE };
const motionOk = () => document.documentElement.dataset.fx !== "off";
const autoSkin = () => (matchMedia("(prefers-color-scheme: light)").matches ? "snow" : "aurora");
