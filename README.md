# Rime 中英文候选双语扩展

为 Rime 已生成的中英文候选增加双语释义。

## 效果示例

TODO: 真实图片

中文候选:

```text
nihao

1. 你好    hello
2. 好      good
3. 你      you
```

英文候选：

```text
comp

1. compare     比较
2. company     公司
3. complete    完整的
4. computer    计算机
```

如果候选原本已有注释，新释义会追加在后面：

```text
给予    ［jǐ yǔ］ · provide
```

## 工作方式

项目由三部分组成：

```text
Lua 通用核心
+ OpenCC 双语词典
+ schema 集成配置
```

处理流程：

1. schema 原有 translator 生成 Candidate；
2. `bilingual_hint.lua` 检查候选文本；
3. 中文候选查询中英词典，英文候选查询英中词典；
4. 根据 `translation_mode` 选择释义；
5. 通过 `ShadowCandidate` 保留原候选，只合并 comment；
6. 将候选继续交给 Rime。

查询使用 `opencc:convert_word()`，属于**整词精确查询**。例如词典中存在“你好”和“啊”，但不存在“你好啊”时，本项目不会自行组合成 `hello ah`。

Rime 运行时不联网，不调用在线翻译或 LLM，不进行机器翻译、分词翻译或未知词拆分。只有开发者主动运行词典拉取脚本时才会访问数据源。

## 系统要求

运行需要：

- Rime / librime
- librime-lua
- OpenCC 支持
- librime-lua 提供以下接口：
  - `Opencc(...)`
  - `opencc:convert_word(...)`
  - `ShadowCandidate(...)`
  - `yield(...)`

构建词典需要：

- Python 3.11+
- `opencc_dict`

Lua 代码兼容 Lua 5.1 语法。中文判断优先使用可用的 `utf8.codes`，同时带有 UTF-8 解码回退。

## 快速安装

### Plum

安装核心文件：

```bash
bash rime-install 0nikod/rime-bilingual
```

为指定 schema 写入配置：

```bash
bash rime-install 0nikod/rime-bilingual:config:schema=rime_ice
```

将 `rime_ice` 替换为实际的 schema ID 即可。

### 手动安装

仓库中的 `opencc/*.ocd2` 是由真实 CC-CEDICT/ECDICT 编译的发布词典。如果当前检出的源码版本未附带这些二进制文件，或你希望使用自己拉取的数据重新生成，请先按[从真实词典拉取并编译](#从真实词典拉取并编译)执行构建。

1. 将 `lua/bilingual_hint.lua` 复制到：

   ```text
   <Rime user dir>/lua/
   ```

2. 将以下文件复制到：

   ```text
   <Rime user dir>/opencc/
   ```

   文件包括：

   ```text
   bilingual_zh_en.json
   bilingual_zh_en.ocd2
   bilingual_en_zh.json
   bilingual_en_zh.ocd2
   ```

3. 在 `<schema_id>.custom.yaml` 中加入 filter、switch 和配置。
4. 重新部署 Rime。

不同前端的 Rime 用户目录不同，例如 Fcitx5 常见位置为：

```text
~/.local/share/fcitx5/rime/
```

## 通用 schema 配置

仓库提供：

```text
integrations/generic/bilingual_hint.custom.yaml.example
```

复制为 `<schema_id>.custom.yaml`，或把其中 patch 合并到现有文件：

```yaml
patch:
  "engine/filters/+":
    - lua_filter@*bilingual_hint

  "switches/+":
    - name: bilingual_hint
      reset: 1
      states: [译关, 译开]

  bilingual_hint:
    zh_to_en: true
    en_to_zh: true
    translation_mode: random
    separator: " · "
```

默认把 filter 追加到过滤器链末尾。如果目标 schema 后面还有会重建 Candidate 或覆盖 comment 的 filter，需要根据该 schema 的实际过滤器顺序调整位置。

## 雾凇拼音

使用：

```text
integrations/rime_ice/rime_ice.custom.yaml
```

该配置同时开启：

```text
中文候选 → 英文释义
英文候选 → 中文释义
```

雾凇拼音中的英文 Candidate 仍由原有英文 translator 生成，本项目不会读取或修改 `melt_eng` 词典，也不会改变雾凇拼音的 translator。仓库附带的完整释义由真实 CC-CEDICT/ECDICT 编译；如果源码分发未包含二进制词典，可运行 `python3 scripts/fetch_and_build.py` 重新生成。

## melt_eng

使用：

```text
integrations/melt_eng/melt_eng.custom.yaml
```

默认配置为：

```yaml
bilingual_hint:
  zh_to_en: false
  en_to_zh: true
  translation_mode: random
  separator: " · "
```

即只为英文 Candidate 增加中文释义。

## 配置

运行配置只包含四项：

```yaml
bilingual_hint:
  zh_to_en: true
  en_to_zh: true
  translation_mode: random
  separator: " · "
```

| 配置 | 默认值 | 作用 |
|---|---:|---|
| `zh_to_en` | `true` | 为含 CJK 汉字的候选查询英文释义 |
| `en_to_zh` | `true` | 为英文候选查询中文释义 |
| `translation_mode` | `random` | 释义选择模式：`random`、`first`、`all` |
| `separator` | ` · ` | 原 comment 与双语释义之间的分隔符 |

### translation_mode

`random`：从释义列表中随机选择一项。

```text
你好 → hello
你好 → hi
```

随机结果不会按输入或候选保存，重新生成候选时可能变化。

`first`：固定使用词典中的第一项。

```text
你好 → hello
```

`all`：使用 ` / ` 连接全部释义。

```text
你好 → hello / hi / greetings
```

无效配置会在初始化时回退为 `random`。

## 文本识别范围

### 中文

候选中存在 CJK Unified Ideograph 时进入中文查询，覆盖常用汉字和扩展汉字范围。候选中只要包含汉字，就按完整 `cand.text` 查询，不会截取其中一部分。

### 英文

第一版接受：

```text
ASCII letters
apostrophe
hyphen
```

例如：

```text
computer
don't
well-known
```

查询前会转换为小写。

数字、邮箱、标点、Emoji 等其他文本直接透传。

## 开关

集成配置会增加：

```yaml
- name: bilingual_hint
  reset: 1
  states: [译关, 译开]
```

关闭开关后 filter 直接透传 Candidate，不执行语言判断、OpenCC 查询、释义选择或 `ShadowCandidate` 构造。

## 构建词典

### 从真实词典拉取并编译

仓库提供 `scripts/fetch_and_build.py`，用于**按需手动**拉取并编译真实词典：

- CC-CEDICT：MDBG 发布的 `cedict_1_0_ts_utf-8_mdbg.zip`；
- ECDICT：`skywind3000/ECDICT` 仓库中的 `ecdict.csv`。

首次运行：

```bash
python3 scripts/fetch_and_build.py
```

脚本会：

1. 下载 `https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.zip`；
2. 从 ZIP 中安全提取 `cedict_ts.u8`；
3. 下载 ECDICT 的 `ecdict.csv`；
4. 在临时目录调用 `scripts/build.py` 并完成全部校验；
5. 校验成功后再成组替换 `opencc/` 中的两个方向产物；构建失败时保留原有发布词典。

下载的原始文件放在 `.cache/dictionaries/`，该目录不会提交到 Git。默认情况下，文件已存在就直接复用，**不会检查新版本，也不会自动更新**。需要主动重新下载时才运行：

```bash
python3 scripts/fetch_and_build.py --force-download
```

已经下载好原始文件后，可禁止网络访问并重新构建：

```bash
python3 scripts/fetch_and_build.py --no-download
```

完整 ECDICT CSV 约 63 MB，包含约 77 万行，其中大量条目是带空格的短语、数字或其他不符合本项目英文 Candidate 识别规则的 key。构建器会保留可由 `^[A-Za-z][A-Za-z'-]*$` 命中的单词，并在构建统计中将其他 key 记为跳过，而不是把它们当成文件损坏。

### 使用已有源文件

已有 `cedict_ts.u8` 和 `ecdict.csv` 时，可直接调用底层构建器：

```bash
python3 scripts/build.py \
  --cedict /path/to/cedict_ts.u8 \
  --ecdict /path/to/ecdict.csv \
  --output opencc \
  --max-translation-length 40 \
  --max-translations-per-entry 6
```

查看完整参数：

```bash
python3 scripts/fetch_and_build.py --help
python3 scripts/build.py --help
```

默认构建参数：

```text
max_translation_length = 40
max_translations_per_entry = 6
```

构建过程包括：

- 解析 CC-CEDICT，使用简体词和英文 definition；
- 解析 ECDICT，使用小写 `word` 和 `translation`；
- 清理空白和有限的元数据/词性标记；
- 按源词典顺序稳定去重；
- 过滤过长释义；
- 限制每个 key 的释义数量；
- 将多单词释义的内部空格编码为 NBSP；
- 按 key 排序并生成 OpenCC 文本词典；
- 调用 `opencc_dict` 编译 `.ocd2`；
- 校验文本词典、JSON 结构和非空编译产物。

输出目录包含：

```text
bilingual_zh_en.txt
bilingual_zh_en.json
bilingual_zh_en.ocd2
bilingual_en_zh.txt
bilingual_en_zh.json
bilingual_en_zh.ocd2
```

`.txt` 是构建中间产物，安装 Rime 时只需要 `.json` 和 `.ocd2`。

## NBSP 与多词释义

OpenCC 文本词典使用普通空格分隔一个 key 的多个 value，因此多词释义不能直接保留内部 ASCII 空格。

构建阶段会将：

```text
input method
```

编码为包含 U+00A0 NO-BREAK SPACE 的 value。Lua 在显示前再恢复为：

```text
input method
```

这样既能保存多个释义，也能保存单个释义中的内部空格。

## 测试与 CI

日常测试范围保持为两部分：

### 构建测试

```bash
# opencc_dict 是必需依赖；缺失时 unittest 会直接失败，避免假成功。
python3 -m unittest discover -s tests -v

out="$(mktemp -d)"
python3 scripts/build.py \
  --cedict tests/fixtures/cedict_sample.txt \
  --ecdict tests/fixtures/ecdict_sample.csv \
  --output "$out"
```

构建测试确认：

- 两个方向都能生成 `.ocd2`；
- key 唯一并排序；
- 释义稳定去重；
- 英文 key 转为小写；
- 长度和数量限制生效；
- NBSP 编码正确。

### 最小 Rime smoke test

最小集成测试只覆盖核心运行路径：

- 中文 Candidate 增加英文 comment；
- 英文 Candidate 增加中文 comment；
- 未命中 Candidate 透传；
- 原 comment 得到保留并合并；
- `first`、`all`、`random`；
- `random` 只检查结果属于可用 forms，不检查统计均匀性。

运行：

```bash
python3 tests/integration/run_smoke.py
```

smoke test 会在临时目录中从 fixture 构建隔离词典，不依赖发布 OCD2 的具体释义文本；发布 OCD2 则由真实数据构建和真实雾凇 schema 加载检查单独验证。

真实雾凇拼音、Windows、Android 和性能不进入日常 CI，放在 Release 前人工检查。

## ASCII Mode

ASCII Mode 直接输出字符时通常不会经过普通 Candidate comment 显示流程，因此不属于本项目的英文释义显示路径。

如果需要英文释义，英文文本必须由 schema 的英文 translator 生成 Candidate。

## 兼容性

OpenCC 与 librime/librime-lua 存在 API 和 ABI 兼容边界。不同 Rime 前端可能绑定不同版本，因此最终以实际前端加载结果为准。

建议在发布记录中注明实际测试的：

```text
librime version
librime-lua version / commit
OpenCC version
Rime frontend version
OS
architecture
```

某个 OpenCC converter 初始化失败时，只关闭对应翻译方向；两个方向都失败时，filter 退化为透传。

## 已知限制

- 只支持中文到英文、英文到中文两个方向；
- 只执行本地词典整词精确查询；
- 不执行机器翻译、在线翻译或 LLM 翻译；
- 不对未知词拆分翻译；
- 英文识别主要覆盖单词、连字符和 apostrophe；
- ASCII Mode 通常没有 Candidate comment；
- `random` 不保存上一次选择结果；
- `all` 模式可能产生较长 comment；
- 某些 Rime 前端或主题可能不显示 comment；
- 词汇覆盖与释义质量取决于实际编译使用的 CC-CEDICT/ECDICT 版本和构建限制；
- 测试 fixture 只含少量样例，完整发布或本地安装应使用真实 CC-CEDICT 与 ECDICT；
- ECDICT 中只保留与运行时英文识别规则一致的单词、连字符和 apostrophe，不载入含空格短语、数字或其他标点 key。

## Release 前人工检查

建议至少检查：

- 最小 Rime schema 能加载 Lua 和两个 `.ocd2`；
- 两个 `.ocd2` 均由真实完整 CC-CEDICT/ECDICT 构建，而不是测试 fixture；
- 雾凇拼音中中文候选显示英文释义；
- 雾凇拼音或 melt_eng 中英文候选显示中文释义；
- 原 comment 保留；
- 第二页候选仍可显示释义；
- 关闭开关后不增加双语 comment；
- Windows、Linux、Android 目标前端能加载 Lua 与 OpenCC 文件；
- 开启和关闭 `bilingual_hint` 做一次简单输入延迟与内存 A/B 检查。

未实际检查的平台应明确标记为“未验证”。

## 项目结构

```text
rime-bilingual/
├── lua/
│   └── bilingual_hint.lua
├── opencc/
│   ├── bilingual_zh_en.json
│   ├── bilingual_zh_en.ocd2
│   ├── bilingual_en_zh.json
│   └── bilingual_en_zh.ocd2
├── integrations/
│   ├── generic/
│   ├── rime_ice/
│   └── melt_eng/
├── scripts/
│   ├── build.py
│   └── fetch_and_build.py
├── tests/
│   ├── fixtures/
│   └── integration/
├── recipe.yaml
├── config.recipe.yaml
└── LICENSE
```

## License

项目代码采用 [MIT License](LICENSE)。CC-CEDICT 与 ECDICT 是独立数据源；拉取脚本只负责下载和编译，不执行数据源许可证验证。
