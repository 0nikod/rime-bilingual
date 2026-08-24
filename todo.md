## TODO

## Feature

已知问题：
- 只支持中文到英文、英文到中文两个方向；
- 只执行本地词典整词精确查询；
- 不对未知词拆分翻译；
- 英文识别主要覆盖单词、连字符和 apostrophe；
- ASCII Mode 通常没有 Candidate comment；
- `all` 模式可能产生较长 comment；
- 某些 Rime 前端或主题可能不显示 comment；
- 测试 fixture 只含少量样例，完整发布或本地安装应使用真实 CC-CEDICT 与 ECDICT；
- ECDICT 中只保留与运行时英文识别规则一致的单词、连字符和 apostrophe，不载入含空格短语、数字或其他标点 key。
- 对 build 进行拆分