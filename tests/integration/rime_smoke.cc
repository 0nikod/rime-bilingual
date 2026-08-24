#include <rime_api.h>

#include <cstring>
#include <iostream>
#include <string>
#include <vector>

extern void rime_require_module_lua();

namespace {

struct CandidateView {
  std::string text;
  std::string comment;
};

bool expect(bool condition, const std::string& message) {
  if (!condition) {
    std::cerr << "FAIL: " << message << "\n";
  }
  return condition;
}

std::vector<CandidateView> query(RimeApi* rime,
                                 RimeSessionId session,
                                 const char* input) {
  rime->clear_composition(session);
  if (!rime->simulate_key_sequence(session, input)) {
    std::cerr << "FAIL: cannot simulate input " << input << "\n";
    return {};
  }

  RIME_STRUCT(RimeContext, context);
  if (!rime->get_context(session, &context)) {
    std::cerr << "FAIL: cannot read context for " << input << "\n";
    return {};
  }

  std::vector<CandidateView> result;
  for (int index = 0; index < context.menu.num_candidates; ++index) {
    const auto& candidate = context.menu.candidates[index];
    result.push_back({candidate.text ? candidate.text : "",
                      candidate.comment ? candidate.comment : ""});
  }
  rime->free_context(&context);
  return result;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc != 3) {
    std::cerr << "usage: rime_smoke USER_DATA_DIR SHARED_DATA_DIR\n";
    return 64;
  }

  rime_require_module_lua();
  RimeApi* rime = rime_get_api();
  RIME_STRUCT(RimeTraits, traits);
  traits.shared_data_dir = argv[2];
  traits.user_data_dir = argv[1];
  traits.prebuilt_data_dir = argv[1];
  traits.staging_dir = argv[1];
  traits.distribution_name = "rime-bilingual-smoke";
  traits.distribution_code_name = "rime-bilingual-smoke";
  traits.distribution_version = "1";
  traits.app_name = "rime.bilingual-smoke";
  traits.min_log_level = 2;
  traits.log_dir = "";

  rime->setup(&traits);
  rime->initialize(&traits);
  if (rime->start_maintenance(True)) {
    rime->join_maintenance_thread();
  }

  RimeSessionId session = rime->create_session();
  if (!expect(session != 0, "cannot create Rime session")) {
    rime->finalize();
    return 1;
  }
  if (!expect(rime->select_schema(session, "bilingual_smoke"),
              "cannot select bilingual_smoke schema")) {
    rime->destroy_session(session);
    rime->finalize();
    return 1;
  }

  bool ok = true;
  rime->set_option(session, "bilingual_hint", True);
  auto chinese = query(rime, session, "nihao");
  ok &= expect(chinese.size() == 1, "nihao should produce one candidate");
  if (chinese.size() == 1) {
    ok &= expect(chinese[0].text == "你好", "Chinese candidate text changed");
    ok &= expect(chinese[0].comment == "原注释 · hello",
                 "Chinese hint/comment merge failed: " + chinese[0].comment);
  }

  if (!expect(rime->select_schema(session, "bilingual_smoke_all"),
              "cannot select bilingual_smoke_all schema")) {
    ok = false;
  }
  rime->set_option(session, "bilingual_hint", True);
  auto all_mode = query(rime, session, "study");
  ok &= expect(all_mode.size() == 1, "all mode should produce one candidate");
  if (all_mode.size() == 1) {
    ok &= expect(all_mode[0].comment == "study / learn / to learn",
                 "all translation mode failed: " + all_mode[0].comment);
  }

  if (!expect(rime->select_schema(session, "bilingual_smoke"),
              "cannot reselect bilingual_smoke schema")) {
    ok = false;
  }
  rime->set_option(session, "bilingual_hint", True);
  RimeConfig schema_config = {};
  if (expect(rime->schema_open("bilingual_smoke", &schema_config),
             "cannot open bilingual_smoke config")) {
    rime->config_set_string(
        &schema_config, "bilingual_hint/translation_mode", "random");
    auto random_mode = query(rime, session, "hello");
    ok &= expect(random_mode.size() == 1,
                 "random mode should produce one candidate");
    if (random_mode.size() == 1) {
      ok &= expect(random_mode[0].comment == "hello" ||
                       random_mode[0].comment == "hi",
                   "random translation mode returned an unavailable form: " +
                       random_mode[0].comment);
    }
    rime->config_set_string(
        &schema_config, "bilingual_hint/translation_mode", "first");
    rime->config_close(&schema_config);
  } else {
    ok = false;
  }

  auto english = query(rime, session, "computer");
  ok &= expect(english.size() == 1, "computer should produce one candidate");
  if (english.size() == 1) {
    ok &= expect(english[0].text == "computer", "English candidate text changed");
    ok &= expect(english[0].comment == "计算机",
                 "English hint failed: " + english[0].comment);
  }

  auto miss = query(rime, session, "zzzzznotaword");
  ok &= expect(miss.size() == 1,
               "zzzzznotaword should produce one candidate");
  if (miss.size() == 1) {
    ok &= expect(miss[0].text == "zzzzznotaword", "miss candidate text changed");
    ok &= expect(miss[0].comment == "未命中",
                 "miss candidate comment changed: " + miss[0].comment);
  }

  rime->set_option(session, "bilingual_hint", False);
  auto disabled = query(rime, session, "nihao");
  ok &= expect(disabled.size() == 1,
               "disabled filter should preserve candidate count");
  if (disabled.size() == 1) {
    ok &= expect(disabled[0].text == "你好", "disabled filter changed text");
    ok &= expect(disabled[0].comment == "原注释",
                 "disabled filter was not a pure pass-through");
  }

  rime->destroy_session(session);
  rime->finalize();
  if (ok) {
    std::cout << "Rime bilingual candidate smoke test passed\n";
    return 0;
  }
  return 1;
}
