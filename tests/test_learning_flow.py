import json

from conftest import DAY, OUTLINE, choice, correct_label, wrong_label


def test_topic_lifecycle_and_active_resolution(dt):
    out = dt.run("status", expect_ok=False)
    assert out["error"] == "no_active_topic"
    created = dt.run("topic", "new", "Sample Subject", "--goal", "Use it")
    assert created["slug"] == "sample-subject"
    assert dt.run("status")["next"]["action"] == "design_outline"
    assert dt.run("status")["intake_needed"] is True
    dt.run("topic", "new", "Sample Subject")
    assert dt.run("topic", "list")["active"] == "sample-subject-2"
    dt.run("topic", "use", "sample-subject")
    assert dt.run("topic", "list")["active"] == "sample-subject"
    dt.run("topic", "leave")
    assert dt.run("topic", "list")["active"] is None


def test_profile_merges_and_clears_intake(dt):
    dt.run("topic", "new", "S")
    dt.run("profile", "set", "--json", '{"prior_knowledge": "none"}')
    dt.run("profile", "set", "--json", '{"time": "20 min a day"}')
    status = dt.run("status")
    assert status["intake_needed"] is False
    assert status["profile"] == {"prior_knowledge": "none", "time": "20 min a day"}
    assert dt.run("profile", "set", "--json", '{"shoe_size": 9}', expect_ok=False)["error"] == "unknown_profile_field"


def test_profile_decline_clears_intake(dt):
    dt.run("topic", "new", "S")
    dt.run("profile", "decline")
    assert dt.run("status")["intake_needed"] is False


def test_outline_validation(dt):
    dt.run("topic", "new", "S")
    bad = {"modules": [{"name": "M", "knowledge_points": [{"name": "K", "type": "memory"}]}]}
    assert dt.run("outline", "set", stdin=json.dumps(bad), expect_ok=False)["error"] == "module_objective_required"
    bad = {"modules": [{"name": "M", "objective": "x", "knowledge_points": [{"name": "K", "type": "vibes"}]}]}
    assert dt.run("outline", "set", stdin=json.dumps(bad), expect_ok=False)["error"] == "invalid_knowledge_type"
    assert dt.run("outline", "set", stdin="not json", expect_ok=False)["error"] == "invalid_json"


def test_outline_must_account_for_every_material(dt, tmp_path):
    doc = tmp_path / "chapter.md"
    doc.write_text("# Heading\nbody text\n")
    sid = dt.run("source", "add", doc)["id"]
    dt.run("topic", "new", "S")
    dt.run("topic", "materials", sid)
    out = dt.run("outline", "set", stdin=json.dumps(OUTLINE), expect_ok=False)
    assert out["error"] == "materials_unaccounted" and out["missing"] == [sid]
    with_material = json.loads(json.dumps(OUTLINE))
    with_material["modules"][0]["materials"] = [sid]
    dt.run("outline", "set", stdin=json.dumps(with_material))


def test_modes_gate_the_tools(dt):
    dt.run("topic", "new", "S")
    dt.run("outline", "set", stdin=json.dumps(OUTLINE))
    out = dt.run("pose", stdin=choice(), expect_ok=False)
    assert out["error"] == "mode_required" and out["needs_mode"] == "study"
    dt.run("mode", "study")
    out = dt.run("outline", "set", stdin=json.dumps(OUTLINE), expect_ok=False)
    assert out["error"] == "mode_required" and out["needs_mode"] == "outline"
    dt.run("mode", "review")
    out = dt.run("pose", stdin=choice(), expect_ok=False)
    assert out["error"] == "review_requires_mastered"


def test_gate_holds_until_engine_says_mastered(studying):
    dt = studying
    results = []
    for _ in range(3):
        posed = dt.run("pose", stdin=choice())
        results.append(dt.run("grade", "--answer", correct_label(posed)))
    assert [r["mastered"] for r in results] == [False, False, True]
    assert results[0]["mastery"] == 0.5 and results[1]["mastery"] == 0.8
    assert results[2]["mastered_now"] is True and results[2]["next"]["kp_id"] == "steps"


def test_engine_grades_choice_and_refuses_model_credit(studying):
    dt = studying
    posed = dt.run("pose", stdin=choice())
    assert "expected" not in posed and "explanation" not in posed
    refused = dt.run("grade", "--answer", wrong_label(posed), "--credit", "1", "--rationale", "close", expect_ok=False)
    assert refused["error"] == "engine_graded_type"
    graded = dt.run("grade", "--answer", wrong_label(posed))
    assert graded["correct"] is False and graded["credit"] == 0.0
    assert graded["explanation"] == "Because the right thing is right."


def test_unknown_wording_asks_for_clarification_without_evidence(studying):
    dt = studying
    dt.run("pose", stdin=choice())
    out = dt.run("grade", "--answer", "hmm maybe the second-ish")
    assert out["needs_clarification"] is True
    assert dt.run("pending")["pending"] is not None
    assert dt.run("status")["next"]["mastery"] == 0.0


def test_choice_accepts_exact_option_text(studying):
    dt = studying
    dt.run("pose", stdin=choice())
    assert dt.run("grade", "--answer", "The Right Thing Here")["correct"] is True


def test_options_are_shuffled_and_relabelled(studying):
    dt = studying
    labels = set()
    for expected in "ABCD":
        posed = dt.run("pose", stdin=choice(expected="A", question=f"Which {expected}?"))
        labels.add(correct_label(posed))
        assert [o["label"] for o in posed["options"]] == list("ABCD")
        dt.run("skip")
    assert labels, "correct option present every time"


def test_question_design_rules_are_enforced(studying):
    dt = studying
    base = json.loads(choice())
    cases = {
        "recommended_marker": {"options": [{"label": "A", "body": "right (Recommended)"}, *base["options"][1:]]},
        "options_in_stem": {"question": "Pick: the right thing here or a plausible wrong one?"},
        "option_letter_in_explanation": {"explanation": "Option A is right."},
        "explanation_required": {"explanation": ""},
        "invalid_difficulty": {"difficulty": "brutal"},
        "four_options_required": {"options": base["options"][:3]},
        "expected_not_in_options": {"expected": "Z"},
    }
    for code, patch in cases.items():
        out = dt.run("pose", stdin=json.dumps({**base, **patch}), expect_ok=False)
        assert out["error"] == code, code
    blank = {"kp": "facts", "type": "fill_in_blank", "question": "No blank", "expected": "x", "explanation": "e", "difficulty": "easy"}
    assert dt.run("pose", stdin=json.dumps(blank), expect_ok=False)["error"] == "one_blank_required"
    tf = {"kp": "facts", "type": "true_false", "question": "It holds.", "expected": "maybe", "explanation": "e", "difficulty": "easy"}
    assert dt.run("pose", stdin=json.dumps(tf), expect_ok=False)["error"] == "true_false_expected"


def test_cannot_pose_unknown_or_qualitative_objective(studying):
    dt = studying
    assert dt.run("pose", stdin=choice(kp="invented"), expect_ok=False)["error"] == "unknown_objective"
    out = dt.run("pose", stdin=choice(kp="why"), expect_ok=False)
    assert out["error"] == "qualitative_gate" and "assess" in out["hint"]


def test_only_one_open_question(studying):
    dt = studying
    dt.run("pose", stdin=choice())
    assert dt.run("pose", stdin=choice(), expect_ok=False)["error"] == "question_pending"


def test_open_answer_needs_judgment_then_rationale(studying):
    dt = studying
    q = {"kp": "steps", "type": "short_answer", "question": "How?", "expected": "by doing the steps in order", "explanation": "Order matters.", "difficulty": "medium"}
    dt.run("pose", stdin=json.dumps(q))
    first = dt.run("grade", "--answer", "you do them in sequence")
    assert first["needs_judgment"] is True and first["expected"] == q["expected"]
    assert dt.run("grade", "--answer", "x", "--credit", "1", expect_ok=False)["error"] == "rationale_required"
    assert dt.run("grade", "--answer", "x", "--credit", "1.5", "--rationale", "r", expect_ok=False)["error"] == "credit_out_of_range"
    done = dt.run("grade", "--answer", "you do them in sequence", "--credit", "1", "--rationale", "Same idea")
    assert done["correct"] is True and done["mastery"] == 0.5


def test_fill_in_blank_is_fuzzy_then_defers_to_judgment(studying):
    dt = studying
    q = {"kp": "facts", "type": "fill_in_blank", "question": "The ____ one", "expected": "mitochondria", "explanation": "e", "difficulty": "easy"}
    dt.run("pose", stdin=json.dumps(q))
    assert dt.run("grade", "--answer", "mitochondrea")["correct"] is True
    dt.run("pose", stdin=json.dumps(q))
    assert dt.run("grade", "--answer", "ribosome")["needs_judgment"] is True


def test_assisted_answers_cannot_clear_the_gate(studying):
    dt = studying
    for _ in range(5):
        posed = dt.run("pose", stdin=choice())
        out = dt.run("grade", "--answer", correct_label(posed), "--hints", "1")
    assert out["credit"] == 0.5 and out["mastered"] is False and out["independent"] is False
    assert dt.run("status")["next"]["kp_id"] == "facts"


def test_assess_requires_real_evidence_and_records_the_gate(studying):
    dt = studying
    assert dt.run("assess", "--kp", "facts", "--passed", "--evidence", "long enough evidence quote here ok", expect_ok=False)["error"] == "quantitative_gate"
    assert dt.run("assess", "--kp", "why", "--passed", "--evidence", "yes", expect_ok=False)["error"] == "evidence_too_short"
    failed = dt.run("assess", "--kp", "why", "--failed", "--evidence", "it just works", "--gap", "No mechanism")
    assert failed["mastered"] is False and failed["gap"] == "No mechanism"
    passed = dt.run("assess", "--kp", "why", "--passed", "--evidence", "each step prepares the state the next one needs")
    assert passed["mastered"] is True


def test_skip_gives_no_credit_and_defer_never_masters(studying):
    dt = studying
    dt.run("pose", stdin=choice())
    dt.run("skip")
    assert dt.run("pending")["pending"] is None
    assert dt.run("status")["next"]["mastery"] == 0.0
    deferred = dt.run("defer", "--kp", "facts")
    assert deferred["next"]["kp_id"] == "steps"
    rows = dt.run("status", "--full")["map"]["modules"][0]["knowledge_points"]
    assert rows[0]["status"] != "mastered"


def test_repair_voids_or_regrades_a_bad_question(studying):
    dt = studying
    posed = dt.run("pose", stdin=choice())
    graded = dt.run("grade", "--answer", wrong_label(posed))
    qid = graded["question_id"]
    assert dt.run("status")["next"]["status"] == "learning"
    voided = dt.run("repair", "--question-id", qid, "--void")
    assert voided["mastery"] == 0.0
    posed = dt.run("pose", stdin=choice())
    wrong = wrong_label(posed)
    graded = dt.run("grade", "--answer", wrong)
    fixed = dt.run("repair", "--question-id", graded["question_id"], "--correct", wrong)
    assert fixed["mastery"] == 0.5


def test_override_requires_a_literal_quote_and_shows_provenance(studying):
    dt = studying
    assert dt.run("override", "--kp", "facts", "--quote", "", expect_ok=False)["error"] == "quote_required"
    out = dt.run("override", "--kp", "facts", "--quote", "I already know this, skip it")
    assert out["next"]["kp_id"] == "steps"
    row = dt.run("status", "--full")["map"]["modules"][0]["knowledge_points"][0]
    assert row["source"] == "learner"


def test_outline_edit_protects_mastered_and_resets_rewritten(studying):
    dt = studying
    for _ in range(3):
        dt.run("grade", "--answer", correct_label(dt.run("pose", stdin=choice())))
    dt.run("grade", "--answer", correct_label(dt.run("pose", stdin=choice(kp="steps"))))
    dt.run("mode", "outline")
    dropped = json.loads(json.dumps(OUTLINE))
    dropped["modules"][0]["knowledge_points"] = dropped["modules"][0]["knowledge_points"][1:]
    assert dt.run("outline", "set", stdin=json.dumps(dropped), expect_ok=False)["error"] == "mastered_objective_removed"
    renamed_mastered = json.loads(json.dumps(OUTLINE))
    renamed_mastered["modules"][0]["knowledge_points"][0]["name"] = "Other facts"
    assert dt.run("outline", "set", stdin=json.dumps(renamed_mastered), expect_ok=False)["error"] == "mastered_objective_rewritten"
    renamed = json.loads(json.dumps(OUTLINE))
    renamed["modules"][0]["knowledge_points"][1]["name"] = "Sharper procedure"
    preview = dt.run("outline", "set", "--dry-run", stdin=json.dumps(renamed))
    assert preview["dry_run"] is True and preview["diff"]["reset"] == ["steps"]
    assert dt.run("status", "--full")["map"]["modules"][0]["knowledge_points"][1]["name"] == "Basic procedure"
    dt.run("outline", "set", stdin=json.dumps(renamed))
    row = dt.run("status", "--full")["map"]["modules"][0]["knowledge_points"][1]
    assert row["name"] == "Sharper procedure" and row["status"] == "new"
    assert dt.run("status", "--full")["map"]["modules"][0]["knowledge_points"][0]["status"] == "mastered"


def test_review_cycle_across_days(studying):
    dt = studying
    for _ in range(3):
        dt.run("grade", "--answer", correct_label(dt.run("pose", stdin=choice())))
    assert dt.run("reviews")["due"] == []
    dt.now += 30 * DAY
    due = dt.run("reviews")["due"]
    assert [d["kp_id"] for d in due] == ["facts"] and "retrievability" in due[0]["reason"]
    assert dt.run("status")["next"]["action"] == "review"
    dt.run("mode", "review")
    dt.run("grade", "--answer", correct_label(dt.run("pose", stdin=choice())))
    assert dt.run("reviews")["due"] == []


def test_reviews_across_all_topics(studying):
    dt = studying
    for _ in range(3):
        dt.run("grade", "--answer", correct_label(dt.run("pose", stdin=choice())))
    dt.run("topic", "new", "Second")
    dt.now += 30 * DAY
    assert dt.run("reviews")["due"] == []
    everywhere = dt.run("reviews", "--all-topics")
    assert everywhere["count"] == 1 and everywhere["due"][0]["topic"] == "sample-subject"


def test_wrong_answers_build_error_records_and_clear_on_recovery(studying):
    dt = studying
    posed = dt.run("pose", stdin=choice())
    out = dt.run("grade", "--answer", wrong_label(posed), "--error-type", "deviation", "--remediation", "Contrast the two cases")
    assert out["error_record"]["error_type"] == "deviation"
    assert dt.run("status")["active_errors"][0]["remediation"] == "Contrast the two cases"
    assert dt.run("grade", "--answer", "x", expect_ok=False)["error"] == "no_pending_question"
    dt.run("grade", "--answer", correct_label(dt.run("pose", stdin=choice())))
    assert dt.run("status")["active_errors"] == []
    wrong = dt.run("pose", stdin=choice())
    bad = dt.run("grade", "--answer", wrong_label(wrong), "--error-type", "vibes", expect_ok=False)
    assert bad["error"] == "invalid_error_type"


def test_every_graded_answer_reaches_the_question_bank(studying):
    dt = studying
    posed = dt.run("pose", stdin=choice())
    dt.run("grade", "--answer", wrong_label(posed))
    rows = dt.run("bank", "list", "--wrong")["items"]
    assert len(rows) == 1 and rows[0]["explanation"] == "Because the right thing is right."
    assert rows[0]["topic"] == "sample-subject"


def test_handoff_and_explained_survive_into_status(studying):
    dt = studying
    dt.run("explained", "--kp", "facts", "--quote", "We covered the first half")
    dt.run("handoff", "--summary", "Did facts", "--next-focus", "Steps next")
    status = dt.run("status")
    assert status["handoff"]["next_focus"] == "Steps next"
    assert status["next"]["learning_stage"] == "partially_explained"


def test_observe_needs_a_quote_to_claim_an_outcome_and_shows_in_status(studying):
    dt = studying
    refused = dt.run("observe", "--kp", "facts", "--strategy", "diagram", "--result", "helped", expect_ok=False)
    assert refused["error"] == "evidence_required"
    dt.run("observe", "--kp", "facts", "--strategy", "diagram", "--result", "helped", "--evidence", "oh now I see")
    assert dt.run("status")["teaching_observations"][0]["strategy"] == "diagram"
