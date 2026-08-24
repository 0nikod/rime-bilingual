# Rime 中英文候选双语扩展

为 Rime 已生成的中英文候选增加双语释义。

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

## 快速安装

### Plum

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
integrations/generic/integration.yaml.example
```

复制为 `<schema_id>.custom.yaml`，或把其中 patch 合并到现有文件

## 雾凇拼音

使用：

```text
integrations/rime_frost/integration.yaml
```

## melt_eng

使用：

```text
integrations/melt_eng/integration.yaml
```

## 配置

```yaml
bilingual_hint:
  zh_to_en: true
  en_to_zh: false
  translation_mode: random
  separator: " · "
```

| 配置 | 默认值 | 作用 |
|---|---:|---|
| `zh_to_en` | `true` | 为含 CJK 汉字的候选查询英文释义 |
| `en_to_zh` | `false` | 为英文候选查询中文释义 |
| `translation_mode` | `random` | 释义选择模式：`random`、`first`、`all` |
| `separator` | ` · ` | 原 comment 与双语释义之间的分隔符 |

### translation_mode

`random`：从释义列表中随机选择一项。

```text
你好 → hello
你好 → hi
```

`first`：固定使用词典中的第一项。

```text
你好 → hello
```

`all`：使用 ` / ` 连接全部释义。

```text
你好 → hello / hi / greetings
```

## 文本识别范围

### 中文

对含有 `CJK Unified Ideograph` 的候选进行中文查询。

### 英文

对含有 ASCII letters, apostrophe, hyphen 的候选进行英文查询。

## 开关

集成配置会增加：

```yaml
- name: bilingual_hint
  reset: 1
  states: [译关, 译开]
```

控制功能是否开启

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

## License

项目代码采用 [MIT License](LICENSE)。CC-CEDICT 与 ECDICT 是独立数据源；拉取脚本只负责下载和编译，不执行数据源许可证验证。
