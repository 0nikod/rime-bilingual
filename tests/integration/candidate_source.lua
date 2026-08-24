local M = {}

local CANDIDATES = {
  nihao = { text = "你好", comment = "原注释" },
  computer = { text = "computer", comment = "" },
  study = { text = "学习", comment = "" },
  hello = { text = "你好", comment = "" },
  zzzzznotaword = { text = "zzzzznotaword", comment = "未命中" },
}

function M.func(input, segment, env)
  local item = CANDIDATES[input]
  if item then
    yield(Candidate("smoke", segment.start, segment._end, item.text, item.comment))
  end
end

return M
