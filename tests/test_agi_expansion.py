"""
Vivy AI — AGI Expansion Engine Verification Suite
=================================================
Tests newly upgraded General Cognitive Architecture capabilities:
  1. Sandboxed Code Execution & Timeout Defense
  2. Workspace General File Management
"""

import os
import sys
import time
import shutil
import unittest
import tempfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from agi.code_executor import CodeExecutor, get_code_executor
from agi.file_manager import GeneralFileManager, get_file_manager
from agi.job_scheduler import JobScheduler, get_job_scheduler
from agi.self_evaluation_loop import SelfEvaluationLoop, get_self_evaluation_loop
from agi.model_adaptation_engine import ContinualModelAdaptationEngine, get_model_adaptation_engine
from agi.self_modification_engine import SelfModificationEngine, get_self_modification_engine
from agi.tool_router import AutonomousToolRouter, get_autonomous_tool_router
from agi.cognitive_core import get_cognitive_core

class TestAGIExpansionEngines(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.executor = CodeExecutor(sandbox_path=os.path.join(self.temp_dir.name, "sandbox"))
        self.file_mgr = GeneralFileManager(workspace_root=self.temp_dir.name)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_01_code_executor_success(self):
        code = "a = 5\nb = 7\nprint(f'Result: {a+b}')"
        res = self.executor.execute_python(code)
        self.assertTrue(res["success"], f"Execution failed with stderr: {res['stderr']}")
        self.assertIn("Result: 12", res["stdout"])
        self.assertEqual(res["returncode"], 0)

    def test_02_code_executor_error_diagnosis(self):
        code = "def foo():\n    return 1 / 0\nfoo()"
        res = self.executor.execute_python(code)
        self.assertFalse(res["success"])
        self.assertEqual(res["diagnosis"]["error_type"], "ZeroDivisionError")

    def test_03_code_executor_timeout_defense(self):
        code = "import time\nwhile True: time.sleep(0.1)"
        res = self.executor.execute_python(code, timeout=1.5)
        self.assertFalse(res["success"])
        self.assertTrue(res["timeout_triggered"])
        self.assertIn("TimeoutError", str(res["diagnosis"]["error_type"]))

    def test_04_file_manager_lifecycle(self):
        test_file = "test_data.txt"
        # Write content
        w_res = self.file_mgr.write_file_content(test_file, "Line 1: AGI\nLine 2: Vivy")
        self.assertTrue(w_res["success"])

        # Read content
        r_res = self.file_mgr.read_file_content(test_file)
        self.assertTrue(r_res["success"])
        self.assertIn("AGI", r_res["content"])

        # Copy file
        copy_dest = "backup/test_data_cpy.txt"
        c_res = self.file_mgr.copy_file(test_file, copy_dest)
        self.assertTrue(c_res["success"])
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir.name, copy_dest)))

        # List directory
        l_res = self.file_mgr.list_directory("")
        self.assertTrue(l_res["success"])
        self.assertGreaterEqual(l_res["count"], 1)

        # Search files
        s_res = self.file_mgr.search_files("Vivy", sub_path="", file_pattern="*.txt")
        self.assertTrue(s_res["success"])
        self.assertGreaterEqual(s_res["match_count"], 1)

    def test_05_job_scheduler_evaluations(self):
        sched_path = os.path.join(self.temp_dir.name, "scheduled_jobs.json")
        sched = JobScheduler(storage_path=sched_path)
        j_id = sched.schedule_once("Test Reminder", {"msg": "Hello"}, delay_seconds=0.1)
        self.assertIn(j_id, sched.jobs)
        time.sleep(0.2)
        due_list = sched.evaluate_due_jobs(current_time=time.time())
        self.assertTrue(len(due_list) > 0)
        self.assertEqual(due_list[0]["job_id"], j_id)
        self.assertEqual(sched.jobs[j_id]["status"], "completed")

    def test_06_self_evaluation_retry_loop(self):
        eval_loop = SelfEvaluationLoop(max_retries=3)
        # We test executing code with a ZeroDivisionError that the loop auto-corrects
        bad_code = "a = 10 / 0\nprint('Success')"
        res = eval_loop.evaluate_and_retry(
            task_name="division_test",
            execution_fn=self.executor.execute_python,
            initial_kwargs={"code_text": bad_code}
        )
        self.assertTrue(res["resolved"], f"Loop failed to resolve error: {res}")
        self.assertGreater(res["attempts_needed"], 1)
        self.assertIn("[Self-Correction", res["final_result"]["code"])

    def test_07_continual_model_adaptation(self):
        adapt_path = os.path.join(self.temp_dir.name, "model_adapt")
        eng = ContinualModelAdaptationEngine(storage_dir=adapt_path)
        eng.register_high_reward_experience("How does gravity work?", "Space-time geometry.", 0.9, ["physics"])
        self.assertEqual(len(eng.retention_buffer), 1)
        res = eng.execute_controlled_adaptation_cycle(force_run=True)
        self.assertTrue(res["success"])
        self.assertIn("lora_delta", res["adapter_file"])

    def test_08_self_modification_rollback_defense(self):
        # We test modifying a dummy file with a broken test command to verify automated rollback defense!
        dummy_file = "shared/dummy_evolve_test.txt"
        abs_dummy = os.path.join(BASE_DIR, dummy_file)
        with open(abs_dummy, "w", encoding="utf-8") as df:
            df.write("Original Version")
        
        mod_engine = SelfModificationEngine(staging_path=os.path.join(self.temp_dir.name, "staging"))
        # Force a broken verification test command to trigger rollback
        res = mod_engine.propose_and_evaluate_modification(
            target_relative_path=dummy_file,
            proposed_content_or_diff="Corrupt Upgrade Version",
            test_command=["python", "-c", "import sys; sys.exit(1)"]
        )
        self.assertTrue(res["rollback_executed"], "Atomic rollback was not executed upon test failure!")
        with open(abs_dummy, "r", encoding="utf-8") as rf:
            content = rf.read()
        self.assertEqual(content, "Original Version", "File was not correctly restored to original!")
        if os.path.exists(abs_dummy):
            try: os.remove(abs_dummy)
            except Exception: pass

    def test_09_autonomous_tool_router(self):
        router = get_autonomous_tool_router()
        # Test code execution routing
        res_code = router.evaluate_and_invoke("Please execute python code to calculate 50 * 20", {"code": "print('Ans:', 50 * 20)"})
        self.assertEqual(res_code["tool_selected"], "code_execution")
        self.assertTrue(res_code["success"])
        self.assertIn("1000", res_code["result"]["stdout"])

        # Test file listing routing
        res_file = router.evaluate_and_invoke("Please list directory contents in my workspace")
        self.assertEqual(res_file["tool_selected"], "file_management")
        self.assertTrue(res_file["success"])

    def test_10_cognitive_core_unified_turn(self):
        core = get_cognitive_core()
        plan = {"topic": "Coding", "tone": "helpful"}
        mem = {"long_term_facts": {"python": "interpreted language"}, "working_memory": []}
        # Execute pre-turn cognition with tool routing
        enh_plan = core.evaluate_pre_turn_cognition("Can you run code to verify if 7 is prime?", mem, None, plan)
        self.assertIn("tool_invocation_result", enh_plan)
        self.assertEqual(enh_plan["tool_invocation_result"]["tool_selected"], "code_execution")
        # Execute post-turn cognition
        core.evaluate_post_turn_cognition("Can you run code to verify if 7 is prime?", "Here is the code output.", enh_plan, mem, 0.95)

if __name__ == "__main__":
    unittest.main()
