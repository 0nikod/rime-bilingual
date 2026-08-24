# Release 前人工检查

日常 CI 只运行构建测试和最小 Rime smoke test。发布前再进行以下人工检查。

## 基础功能

- [ ] 中文 Candidate 只增加英文 comment。
- [ ] 英文 Candidate 只增加中文 comment。
- [ ] 候选正文、顺序、权重和上屏文本不变。
- [ ] 原 comment 被保留并按 `separator` 合并。
- [ ] 未命中候选原样透传。
- [ ] `random`、`first`、`all` 均符合配置。
- [ ] 关闭 `bilingual_hint` 后不执行双语查询。
- [ ] `zh_to_en` 与 `en_to_zh` 可分别关闭。
- [ ] 第二页及后续候选仍可显示释义。

## 集成检查

- [ ] 在最小 schema 中加载 Lua、JSON 与 OCD2。
- [ ] 确认发布的两个 OCD2 由真实完整 CC-CEDICT/ECDICT 构建，而不是测试 fixture。
- [ ] 在真实 rime-ice 中检查中文、英文、原 comment、翻页和开关。
- [ ] 在 melt_eng 中确认只执行英文到中文查询。
- [ ] 检查实际 filter 顺序，确认后续 filter 不会覆盖 comment。
- [ ] 检查 ASCII Mode 限制仍写在发布说明中。

## 平台检查

按本次发布目标分别记录版本与结果；没有实际检查的平台标记为“未验证”。

- [ ] Windows x86_64 / Weasel
- [ ] Linux x86_64 / Fcitx5 Rime
- [ ] Android arm64 / 目标 Rime 前端

## 简单性能 A/B

1. 固定设备、前端、schema、词典、页面大小和输入序列。
2. A 组关闭 `bilingual_hint`，B 组开启。
3. 连续输入相同的中文与英文序列并翻页。
4. 记录是否有可感知延迟、内存增量和两个 OCD2 文件大小。
5. 只有发现明显问题后，再细分测量 OpenCC 初始化和 `convert_word()`。
