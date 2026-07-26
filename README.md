# QQ 频道帖子关键字提醒

盯着 QQ 频道的帖子，出现你设定的关键字时**立刻提醒你**——桌面弹窗，或推送到微信。

不用一直手动刷论坛。适合蹲「保研」「调剂」「实习」「二手」这类信息。

## 两个版本，任选其一

| | **Edge 浏览器插件版**（推荐） | **Python 脚本版** |
|---|---|---|
| 安装难度 | 简单，加载文件夹即可 | 需装 Python |
| 登录方式 | 复用浏览器已登录的身份，**免扫码** | 需扫码登录一次 |
| 提醒方式 | 桌面弹窗 +（可选）微信 | 微信 |
| 是否要 token | 不需要（微信推送才需要） | 需要 PushPlus token |
| 适合 | 大多数人，尤其电脑小白 | 想挂在服务器/后台跑 |

---

## 一、Edge 插件版（推荐）

### 安装

**第 1 步：下载**

点这里下载 👉 **[edge-extension-v1.0.zip](https://github.com/liutianyi746-lab/qq-forum-monitor/releases/latest/download/edge-extension-v1.0.zip)**

**第 2 步：解压**

右键下载好的 zip → **「全部解压缩」/「解压到当前文件夹」**，会得到一个文件夹。
记住这个文件夹的位置（里面应该能看到 `manifest.json` 这个文件）。

**第 3 步：装进 Edge**

1. 打开 Edge 浏览器
2. 在地址栏输入 `edge://extensions` 然后按回车
3. 找到页面**左下角的「开发人员模式」开关，把它打开**
4. 页面上方会出现按钮，点**「加载解压缩的扩展」**
5. 在弹出的窗口里，选中**第 2 步解压出来的那个文件夹**，点「选择文件夹」

**第 4 步：把插件固定出来（方便点）**

点 Edge 右上角的**拼图图标 🧩** → 找到「QQ频道帖子关键字提醒」→ 点它右边的**图钉图标**。
这样插件图标就常驻在地址栏旁边了。

### 使用
1. 先在 Edge 里登录一次 QQ 频道网页版（访问 `https://pd.qq.com/g/你的频道`）
2. 点插件图标，填：
   - **关键字**（一行一个）
   - **频道**：频道链接 `pd.qq.com/g/` 后面那一段
   - **检查间隔**：默认 60 秒（浏览器最快约 30 秒）
   - **微信推送 token**（可选，见下）
3. 勾上「开启监控」→ 保存
4. 点「测试弹窗+接口」确认能抓到帖子

之后有新帖命中关键字就自动桌面弹窗，点弹窗直接跳转频道。

> 首次运行会先记录当前帖子（不弹窗），之后只提醒新帖。

---

## 二、Python 脚本版

点这里下载 👉 **[python-version-v1.0.zip](https://github.com/liutianyi746-lab/qq-forum-monitor/releases/latest/download/python-version-v1.0.zip)**，解压后使用。

> **Windows 用户最简单的用法**：解压后按顺序双击这三个文件即可，全程不用碰命令行 ——
> `第1步_安装依赖.bat` → `第2步_扫码登录.bat` → `第3步_开始监控.bat`
>（开始前记得先把 `config.yaml.example` 改名为 `config.yaml`，并填入关键字和 PushPlus token）

以下是手动命令行方式：

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

1. 把 `config.yaml.example` 复制为 `config.yaml`，填入你的关键字和 PushPlus token
2. 扫码登录并抓取接口：

```bash
python monitor.py --setup
```

3. 开始监控：

```bash
python monitor.py
```

其它命令：`--test-push` 测试推送、`--once` 只查一次。

---

## 想收微信提醒？

1. 打开 https://www.pushplus.plus/ ，微信扫码登录
2. 复制你的 **token**
3. 插件版：填进插件窗口的「微信推送 token」框；脚本版：填进 `config.yaml` 的 `pushplus_token`

不填则插件只弹桌面通知。

---

## 工作原理

调用 QQ 频道网页版自己在用的帖子列表接口（`GetGuildFeeds`），以**你自己的登录身份**读取你有权查看的帖子，在本地解析标题/正文/作者并匹配关键字，按帖子 ID 去重避免重复提醒。

插件版直接复用浏览器 Cookie 并自行计算 `bkn` 校验值；脚本版在 `--setup` 阶段用 Playwright 捕获一次请求模板后重放。

## 隐私

- 关键字判断**全部在本地完成**，默认不向任何第三方发送数据
- 登录态只在你本机使用，不上传、不存储、不分享
- 只有你主动填了 PushPlus token，才会把命中的帖子标题/摘要发往 PushPlus 以推送到你的微信
- 完整说明见 [privacy.html](privacy.html)

## 注意

- 本项目仅供**个人学习与自用**，使用你自己的账号读取你自己有权访问的内容
- 请勿高频请求（默认间隔已设保守值），请勿用于批量采集或其他用途
- 使用者需自行遵守腾讯相关服务条款，作者不对使用后果负责

## License

[MIT](LICENSE)
