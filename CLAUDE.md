# RollingAI DeckBuilder

做 deck（演示 / PPT / pitch / 汇报）的工作台。**所有 deck 相关请求必须走
skill 体系，不要裸写 HTML。**

## 自然语言 → 能力路由（用户不一定知道命令，听到这些话就走对应路径）

| 用户说的话（举例） | 走哪条路径 |
|---|---|
| 做个 PPT / deck / 演示 / 路演材料 | `/new-deck` 流程：先让用户选模板 |
| 把这个 Keynote 转成网页 / .key 文件 | `/keynote`（keynote-to-html skill）|
| 把 XX deck 的那几页拿过来 / 复用立白案例 | `/splice`（deck-splice skill）|
| 让它动起来 / 数字滚动 / 加动画 | `/animate`（slide-anim；rolling-deck 已内置勿重装）|
| 入库 / 进管理平台 / 出缩略图 / 打标签 | `/ingest`（ingest→tags→thumbs 三连）|
| 这页改一下 / 重新设计这页 | slide-redesign skill |
| 系统都能干啥 | `/deck-help` |

用户的说法对不上表里的任何一条、但明显和 deck 有关 → 先跑
`python3 plugin/skills/registry.py` 看全部 skill 再决定，不要自己发明流程。

## 🛑 做 deck 前必读（最重要的一条规则）

用户要做新 deck / 演示 / PPT / H5 时，**第一步永远是**：

1. 跑 `python3 plugin/skills/registry.py` 看可用的布局风格（kind=布局风格）
2. **向用户列出选项让用户选**（不要默默选一个），目前是：
   - **rolling-deck**（默认推荐）— RollingAI 风格单文件 H5：粒子地球封面、
     磨砂玻璃、29 页版式库、内置 GSAP 动画。对客 pitch / 高质感交付用这个。
   - **feishu-deck-h5** — deck.json 结构化渲染，Keynote 导入产物用这个。
3. 选定后**严格按该 skill 的 SKILL.md 操作**：
   - rolling-deck → 读 `plugin/skills/rolling-deck/SKILL.md`（复制
     `template.html`，按 `reference.md` 组件库填内容，**绝不动 <style> 和
     <script>**，做完跑 check-fill 自检）
   - feishu-deck-h5 → 读 `plugin/skills/feishu-deck-h5/SKILL.md`

用户没指明风格时，**默认 rolling-deck**，但要说一句"我用 rolling-deck
模板（粒子地球那套），要换风格告诉我"。

## 复用旧 slide / 拼 deck

要把历史 deck 的页面拼进新 deck（"立白那 6 张搬过来"这类需求）→ 用
`deck-splice` skill（`plugin/skills/deck-splice/SKILL.md`）。它处理类名
隔离、素材拷贝、视频物化/声音、动画引擎自动安装——**不要手工拷 HTML**。
也可以走 admin UI 的购物车（勾选 slides → 加入 Deck）。

## Deck 完成后的固定三步（入库）

```bash
python3 library/db/ingest_deck.py <deck-id> imports/<deck-id>/render-output-full/deck.json
python3 library/db/gen_thumbnails.py --deck <deck-id>
# admin UI 自动发现 imports/ 下的 deck，无需注册
```

rolling-deck 的 deck.json 用 `plugin/skills/rolling-deck/assets/build-deckjson.py`
从 index.html 生成。

## 目录地图

| 路径 | 是什么 |
|---|---|
| `plugin/skills/<name>/SKILL.md` | 每个 skill 的操作手册（做事前先读对应这份）|
| `plugin/skills/registry.py` | skill 清单 / 校验 |
| `plugin/_player/render.py` | layout pack 渲染调度入口 |
| `imports/<deck-id>/render-output-full/` | 每份 deck 的成品（gitignore，客户内容）|
| `library/db/` | slides.db + ingest / 缩略图工具（data/ gitignore）|
| `platform/admin/` | 管理后台（FastAPI + Alpine），`python3 -m uvicorn server:app` 于 platform/admin |

## 红线

- 不要把 `imports/`、`library/db/data/`、`library/stories/` 的内容提交进 git（客户机密）
- 不要修改 rolling-deck 模板的 `<style>` / `<script>`（模板的全部价值）
- 重新入库不会洗掉人工标签（ingest 默认保留 tags）；想强制重打用 `--retag`
