---
description: 复用历史 deck 的页面 — 整页拼进新 deck（DOM+素材+视频原样）
---

用户要把旧 deck 的某些页拼进另一份 deck。参数：$ARGUMENTS（描述要拼什么，
比如"立白那 6 张到蓝月亮 deck 第 5 页后"）。

1. 读 `plugin/skills/deck-splice/SKILL.md`。
2. **选材**：用 `python3 plugin/skills/deck-splice/assets/pick.py
   --keywords … --customers …` 在 slides.db 搜候选，列给用户确认。
3. **执行**（二选一）：
   - 命令行一步到位：`echo '{"target_deck_id":…,"after_page":N,"items":[…]}'
     | python3 plugin/skills/deck-splice/assets/insert.py --spec -`
   - 或者提示用户用 admin 购物车（幻灯片页勾选 → 加入 Deck → 选插入位置）
4. 引擎会自动处理：类名隔离 / 素材拷贝 / 视频物化+声音 / 动画库安装 /
   重新入库（标签保留）/ 新页缩略图。完成后跑
   `bash plugin/skills/deck-splice/assets/verify.sh <deck-dir>` 确认。
5. 注意：目标必须是 rolling-deck 壳；声音默认照搬源 deck 行为，slide 打
   `有声视频` / `静音视频` 自由标签可覆盖。
