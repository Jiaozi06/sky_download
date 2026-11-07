import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";

const snapshot = new URL("../downloads.json", import.meta.url);
const data = JSON.parse(await readFile(snapshot, "utf8"));
const { channels, international } = data;

const buttons = [
  ["网易官服", channels.official, "https://adl.netease.com/d/g/sky/c/gw?type=android"],
  ["哔哩哔哩", channels.bilibili, "https://www.biligame.com/detail/?id=101661"],
  ["vivo", channels.vivo, "https://h5.appstore.vivo.com.cn/#/details?appId=2902164", true],
  ["应用宝", channels.qq, "https://sj.qq.com/appdetail/com.tencent.tmgp.eyou.eygy"],
  ["4399", channels["4399"], "https://a.4399.cn/mobile/112700.html"],
  ["233 乐园", channels["233"], "https://www.233leyuan.com/game-detail/1433471"],
  ["华为", channels.huawei, "https://appgallery.huawei.com/app/C100685413"],
  ["HMS Core", channels.huawei?.dependencies?.hms_core, "https://appgallery.huawei.com/app/C10132067"],
  ["国际服 · 华为", international?.huawei, "https://appgallery.huawei.com/app/C105091411"],
  ["国际服 · Google Play", { url: international?.google_play, verified: true }],
];

function safeHref(value) {
  if (!URL.canParse(value ?? "")) return null;
  const url = new URL(value);
  if (url.protocol === "https:") {
    return url.href.replaceAll("&", "&amp;").replaceAll('"', "&quot;");
  }
  return null;
}

const markup = buttons.map(([label, release, fallback, needsBrowserUrl]) => {
  const direct = release?.verified && !Object.keys(release.headers ?? {}).length
    ? safeHref(release.browser_url ?? (needsBrowserUrl ? null : release.url))
    : null;
  const href = direct ?? safeHref(fallback);
  if (!href) {
    return `<li><span aria-disabled="true">${label} · 暂不可用</span></li>`;
  }
  const buttonLabel = direct || label === "网易官服" ? label : `${label} · 下载页`;
  return `<li><a href="${href}">${buttonLabel}</a></li>`;
}).join("\n      ");

const dist = new URL("dist/", import.meta.url);
const template = await readFile(new URL("page.html", import.meta.url), "utf8");
await mkdir(dist, { recursive: true });
await Promise.all([
  writeFile(new URL("page.html", dist), template.replace("<!-- Download buttons -->", () => markup)),
  copyFile(snapshot, new URL("downloads.json", dist)),
]);
