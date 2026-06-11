---
description: 新建一份 deck — 引导选模板、建目录、填内容、入库
---

用户要新建一份 deck。参数（可选）：$ARGUMENTS（deck 主题 / 客户名 / 素材路径）。

按以下流程引导，**不要跳过第 1 步**：

1. **选布局风格**。跑 `python3 plugin/skills/registry.py` 列出 kind=布局风格
   的 pack，用 AskUserQuestion 让用户选（默认推荐 rolling-deck，说明两者
   区别：rolling-deck=对客高质感单文件 H5；feishu-deck-h5=deck.json 结构化
   渲染）。

2. **读选定 pack 的 SKILL.md** 并严格按它操作：
   - rolling-deck: `plugin/skills/rolling-deck/SKILL.md` + `reference.md`
     （29 页版式库）。先梳理用户素材自己的故事线，再挑版式；绝不改模板的
     <style>/<script>；做完跑 check-fill 自检。
   - feishu-deck-h5: `plugin/skills/feishu-deck-h5/SKILL.md`。

3. **目录约定**：成品放 `imports/<deck-id>/render-output-full/index.html`
   （deck-id 用英文短横线）。

4. **要复用历史 slide 吗？** 问用户。要的话用 deck-splice skill
   （`plugin/skills/deck-splice/SKILL.md`）或者提示用户去 admin 购物车勾选。
   可先用 `python3 plugin/skills/deck-splice/assets/pick.py --keywords …`
   帮用户搜素材。

5. **入库三步**（做完 deck 后）：
   ```bash
   python3 plugin/skills/rolling-deck/assets/build-deckjson.py imports/<id>/render-output-full/index.html
   python3 library/db/ingest_deck.py <id> imports/<id>/render-output-full/deck.json
   python3 library/db/gen_thumbnails.py --deck <id>
   ```

6. **自测**：浏览器打开翻一遍 + 试编辑模式 + 试导出 PDF，再交付。
