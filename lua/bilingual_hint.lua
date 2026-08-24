local bilingual_hint = {}
local random_seeded = false
local NBSP = "\194\160"

local function is_chinese_codepoint(codepoint)
  return (codepoint >= 0x3400 and codepoint <= 0x4DBF)
    or (codepoint >= 0x4E00 and codepoint <= 0x9FFF)
    or (codepoint >= 0xF900 and codepoint <= 0xFAFF)
    or (codepoint >= 0x20000 and codepoint <= 0x2FA1F)
    or (codepoint >= 0x30000 and codepoint <= 0x323AF)
end

-- Validate and decode UTF-8 without depending on Lua 5.3's optional utf8 module.
-- The validation also keeps malformed text away from utf8.codes, which throws.
local function decode_utf8(text)
  local found = false
  local index = 1
  local length = #text
  while index <= length do
    local first = string.byte(text, index)
    local codepoint
    local size
    if first <= 0x7F then
      codepoint = first
      size = 1
    elseif first >= 0xC2 and first <= 0xDF then
      local second = string.byte(text, index + 1)
      if not second or second < 0x80 or second > 0xBF then
        return false, false
      end
      codepoint = (first - 0xC0) * 0x40 + (second - 0x80)
      size = 2
    elseif first >= 0xE0 and first <= 0xEF then
      local second, third = string.byte(text, index + 1, index + 2)
      if not second or not third
        or second < 0x80 or second > 0xBF
        or third < 0x80 or third > 0xBF
        or (first == 0xE0 and second < 0xA0)
        or (first == 0xED and second > 0x9F) then
        return false, false
      end
      codepoint = (first - 0xE0) * 0x1000
        + (second - 0x80) * 0x40 + (third - 0x80)
      size = 3
    elseif first >= 0xF0 and first <= 0xF4 then
      local second, third, fourth = string.byte(text, index + 1, index + 3)
      if not second or not third or not fourth
        or second < 0x80 or second > 0xBF
        or third < 0x80 or third > 0xBF
        or fourth < 0x80 or fourth > 0xBF
        or (first == 0xF0 and second < 0x90)
        or (first == 0xF4 and second > 0x8F) then
        return false, false
      end
      codepoint = (first - 0xF0) * 0x40000
        + (second - 0x80) * 0x1000
        + (third - 0x80) * 0x40 + (fourth - 0x80)
      size = 4
    else
      return false, false
    end
    if is_chinese_codepoint(codepoint) then
      found = true
    end
    index = index + size
  end
  return true, found
end

local has_chinese
if utf8 and utf8.codes then
  has_chinese = function(text)
    local valid = decode_utf8(text)
    if not valid then
      return false
    end
    for _, codepoint in utf8.codes(text) do
      if is_chinese_codepoint(codepoint) then
        return true
      end
    end
    return false
  end
else
  has_chinese = function(text)
    local valid, found = decode_utf8(text)
    return valid and found
  end
end

-- Keep this identical to the keys accepted by scripts/build.py.
local function is_english(text)
  return string.match(text, "^[A-Za-z][A-Za-z'%-]*$") ~= nil
end

local function configured_bool(config, path)
  local value = config:get_bool(path)
  if value == nil then
    return true
  end
  return value
end

local function select_translation(forms, mode)
  if not forms or #forms == 0 then
    return nil
  end
  if mode == "first" then
    return forms[1]
  elseif mode == "all" then
    return table.concat(forms, " / ")
  end
  return forms[math.random(#forms)]
end

local function make_converter(config_name)
  if not Opencc then
    return nil, "Opencc is unavailable"
  end
  local ok, converter = pcall(Opencc, config_name)
  if not ok then
    return nil, tostring(converter)
  end
  if not converter then
    return nil, "Opencc returned nil"
  end
  return converter, nil
end

function bilingual_hint.init(env)
  local config = env.engine.schema.config
  env.zh_to_en = configured_bool(config, "bilingual_hint/zh_to_en")
  env.en_to_zh = configured_bool(config, "bilingual_hint/en_to_zh")
  env.translation_mode = config:get_string("bilingual_hint/translation_mode")
  if env.translation_mode ~= "first"
    and env.translation_mode ~= "all"
    and env.translation_mode ~= "random" then
    env.translation_mode = "random"
  end
  env.separator = config:get_string("bilingual_hint/separator") or " · "

  local failures = {}
  if env.zh_to_en then
    local reason
    env.zh_converter, reason = make_converter("bilingual_zh_en.json")
    if not env.zh_converter then
      env.zh_to_en = false
      failures[#failures + 1] = "zh_to_en: " .. reason
    end
  end
  if env.en_to_zh then
    local reason
    env.en_converter, reason = make_converter("bilingual_en_zh.json")
    if not env.en_converter then
      env.en_to_zh = false
      failures[#failures + 1] = "en_to_zh: " .. reason
    end
  end
  if #failures > 0 and log and log.error then
    log.error("bilingual_hint initialization failure; disabled "
      .. table.concat(failures, "; "))
  end

  if env.translation_mode == "random" and not random_seeded then
    math.randomseed(os.time())
    random_seeded = true
  end
end

function bilingual_hint.func(input, env)
  -- Disabled means a pure pass-through: no lookup, replacement, or reordering.
  if not env.engine.context:get_option("bilingual_hint") then
    for candidate in input:iter() do
      yield(candidate)
    end
    return
  end

  for candidate in input:iter() do
    local forms
    if env.zh_to_en and has_chinese(candidate.text) then
      forms = env.zh_converter:convert_word(candidate.text)
    elseif env.en_to_zh and is_english(candidate.text) then
      forms = env.en_converter:convert_word(string.lower(candidate.text))
    end

    local hint = select_translation(forms, env.translation_mode)
    if hint then
      hint = string.gsub(hint, NBSP, " ")
      local comment = candidate.comment or ""
      if comment ~= "" then
        comment = comment .. env.separator .. hint
      else
        comment = hint
      end
      -- ShadowCandidate inherits the original candidate's range and quality.
      yield(ShadowCandidate(candidate, candidate.type, candidate.text, comment, false))
    else
      yield(candidate)
    end
  end
end

function bilingual_hint.fini(env)
  env.zh_converter = nil
  env.en_converter = nil
end

return bilingual_hint
